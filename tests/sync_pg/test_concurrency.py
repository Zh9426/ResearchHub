"""Separate PostgreSQL connections, visible row-lock waits and competing workers."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from researchhub.sync.kernel import apply_in_session, heads, lock_project
from researchhub.sync.models import Grant, Inbox, ObjectRevision, SyncTransaction
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_scientific import consent, divergence


def run_pair(world, transactions, contexts=None):
    barrier = Barrier(2)
    pids = []

    def worker(index):
        with Session(world.engine) as db, db.begin():
            pids.append(db.scalar(text("SELECT pg_backend_pid()")))
            barrier.wait(timeout=10)
            try:
                return apply_in_session(db, transactions[index],
                                        contexts[index] if contexts else world.context())
            except ProtocolError as exc:
                # A rejection must rollback its already flushed RECEIVING row.
                db.rollback()
                return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert len(set(pids)) == 2
    return results


def test_two_workers_same_transaction_duplicate(world):
    tx = world.make()
    outcomes = run_pair(world, [tx, tx])
    assert outcomes[0] == outcomes[1]
    with Session(world.engine) as db:
        assert len(list(db.scalars(select(ObjectRevision).where(ObjectRevision.project_id == world.project_id)))) == 1
        assert len(list(db.scalars(select(Inbox).where(Inbox.project_id == world.project_id)))) == 1
    with pytest.raises(IntegrityError), world.engine.begin() as db:
        db.execute(text("INSERT INTO sync_kernel_inbox SELECT * FROM sync_kernel_inbox WHERE transaction_id=:tid"),
                   {"tid": tx["transaction_id"]})


def test_two_workers_different_objects_both_accepted(world):
    outcomes = run_pair(world, [world.make(), world.make()])
    assert all(result["state"] == "ACCEPTED" for result in outcomes)
    assert {result["sequence"] for result in outcomes} == {1, 2}


def test_two_workers_same_base_preserve_both_heads(world):
    baseline = world.make()
    world.apply(baseline)
    change = baseline["changes"][0]
    transactions = [world.make(oid=change["object_id"], parents=[revision(change)], operation="update",
                               payload={"value": value, "value_type": "decimal"}) for value in ["1.600", "1.800"]]
    outcomes = run_pair(world, transactions)
    assert {r["state"] for r in outcomes} == {"ACCEPTED", "CANDIDATE"}
    with Session(world.engine) as db:
        assert heads(db, world.project_id, "Parameter", change["object_id"]) == sorted(revision(tx["changes"][0]) for tx in transactions)
        assert all(db.get(SyncTransaction, tx["transaction_id"]).state == "CANDIDATE" for tx in transactions)


def test_two_online_resolutions_one_accepts_other_rechecks_heads(world):
    baseline, branches = divergence(world)
    expected = sorted(revision(tx["changes"][0]) for tx in branches)
    transactions = [world.make(actor=actor, oid=baseline["object_id"], parents=expected, operation="resolve",
                               payload={"value": value, "value_type": "decimal"})
                    for actor, value in [("human", "1.700"), ("human_b", "1.900")]]
    contexts = [consent(world, tx, actor) for tx, actor in zip(transactions, ["human", "human_b"], strict=True)]
    outcomes = run_pair(world, transactions, contexts)
    assert sum(isinstance(result, dict) and result["state"] == "ACCEPTED" for result in outcomes) == 1
    assert "CONFLICT_CHANGED" in outcomes
    with Session(world.engine) as db:
        assert len(heads(db, world.project_id, "Parameter", baseline["object_id"])) == 1
        loser = next(index for index, result in enumerate(outcomes) if result == "CONFLICT_CHANGED")
        assert db.get(SyncTransaction, transactions[loser]["transaction_id"]) is None
        assert db.get(Grant, contexts[loser].grant_id).consumed is False


def test_two_offline_resolutions_preserve_new_fork(world):
    baseline, branches = divergence(world)
    expected = sorted(revision(tx["changes"][0]) for tx in branches)
    transactions = [world.make(actor=actor, oid=baseline["object_id"], parents=expected, operation="resolve",
                               payload={"value": value, "value_type": "decimal"})
                    for actor, value in [("human", "1.700"), ("human_b", "1.900")]]
    outcomes = run_pair(world, transactions, [world.context(actor, mode="offline_proposal")
                                            for actor in ["human", "human_b"]])
    assert all(result["state"] == "CANDIDATE" for result in outcomes)
    with Session(world.engine) as db:
        assert heads(db, world.project_id, "Parameter", baseline["object_id"]) == sorted(
            revision(tx["changes"][0]) for tx in transactions)


def test_late_fork_races_with_dependent_apply(world):
    base = world.make()
    world.apply(base)
    change = base["changes"][0]
    a = world.make(oid=change["object_id"], parents=[revision(change)], operation="update",
                   payload={"value": "1.600", "value_type": "decimal"})
    world.apply(a)
    fork = world.make(oid=change["object_id"], parents=[revision(change)], operation="update",
                      payload={"value": "1.800", "value_type": "decimal"})
    dependent = world.make(kind="Note", payload={"content": "SYNTHETIC derived"},
                           dependencies=[a["transaction_id"]])
    run_pair(world, [fork, dependent])
    with Session(world.engine) as db:
        assert all(db.get(SyncTransaction, tx["transaction_id"]).state == "CANDIDATE"
                   for tx in [a, fork, dependent])


def test_postgresql_lock_wait_and_independent_project_continues(world, world_factory):
    other = world_factory()
    locked, release, started = Event(), Event(), Event()
    waiter_pid = []

    def holder():
        with Session(world.engine) as db, db.begin():
            lock_project(db, world.project_id)
            locked.set()
            assert release.wait(timeout=10)

    def waiter():
        with Session(world.engine) as db, db.begin():
            waiter_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            started.set()
            return apply_in_session(db, world.make(), world.context())

    with ThreadPoolExecutor(max_workers=3) as pool:
        hold = pool.submit(holder)
        assert locked.wait(timeout=5)
        wait = pool.submit(waiter)
        try:
            assert started.wait(timeout=5)
            observed = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with world.engine.connect() as db:
                    observed = db.scalar(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),
                                         {"pid": waiter_pid[0]})
                if observed:
                    break
                time.sleep(0.02)
            assert observed is True, "PostgreSQL must visibly block the second same-project writer"
            assert pool.submit(other.apply, other.make()).result(timeout=5)["state"] == "ACCEPTED"
            assert not wait.done()
        finally:
            release.set()
        hold.result(timeout=5)
        assert wait.result(timeout=5)["state"] == "ACCEPTED"
