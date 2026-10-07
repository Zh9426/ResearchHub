"""Hypothesis-generated schedules and graphs on the actual dedicated PostgreSQL."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from researchhub.sync.kernel import CRASH_POINTS, heads
from researchhub.sync.models import Audit, SyncTransaction
from researchhub.sync.projection import object_view
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_scientific import consent

QA_PROPERTY = settings(max_examples=20, deadline=None,
                       suppress_health_check=[HealthCheck.function_scoped_fixture])
# Fixture only supplies a factory. Every generated example creates a new project,
# preventing previous examples from satisfying assertions by accumulated state.


@QA_PROPERTY
@given(st.lists(st.sampled_from([*CRASH_POINTS, "success"]), min_size=1, max_size=8))
def test_random_retry_crash_schedule_is_atomic_idempotent(world_factory, schedule):
    world = world_factory()
    tx = world.make()
    for point in schedule:
        try:
            world.apply(tx, fault=None if point == "success" else point)
        except RuntimeError as exc:
            assert "injected crash" in str(exc)
            with Session(world.engine) as db:
                assert db.get(SyncTransaction, tx["transaction_id"]) is None
    world.apply(tx)
    world.apply(tx)
    with Session(world.engine) as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.project_id == world.project_id)) == 1


@QA_PROPERTY
@given(st.integers(-1000, 1000), st.integers(-1000, 1000))
def test_same_base_scientific_branches_always_preserved(world_factory, left, right):
    world = world_factory()
    base = world.make()
    world.apply(base)
    c = base["changes"][0]
    transactions = [world.make(oid=c["object_id"], operation="update", parents=[revision(c)],
                               payload={"value_type": "decimal", "value": str(value) + ".00"}) for value in [left, right]]
    for tx in transactions:
        world.apply(tx)
    with Session(world.engine) as db:
        assert heads(db, world.project_id, "Parameter", c["object_id"]) == sorted(revision(tx["changes"][0]) for tx in transactions)
        assert object_view(db, world.project_id, "Parameter", c["object_id"])["accepted"] is None


@QA_PROPERTY
@given(st.permutations([0, 1, 2]))
def test_independent_transaction_permutations_equivalent(world_factory, order):
    world = world_factory()
    transactions = [world.make(kind="Note", payload={"title": f"SYNTHETIC {i}"}) for i in range(3)]
    for index in order:
        assert world.apply(transactions[index])["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        assert {object_view(db, world.project_id, "Note", tx["changes"][0]["object_id"])["accepted"]["title"]
                for tx in transactions} == {f"SYNTHETIC {i}" for i in range(3)}


@QA_PROPERTY
@given(st.integers(2, 4))
def test_resolution_consumes_exact_generated_head_set(world_factory, head_count):
    world = world_factory()
    base = world.make()
    world.apply(base)
    c = base["changes"][0]
    branches = [world.make(oid=c["object_id"], operation="update", parents=[revision(c)],
                           payload={"value_type": "decimal", "value": str(index + 1) + ".00"}) for index in range(head_count)]
    for tx in branches:
        world.apply(tx)
    expected = sorted(revision(tx["changes"][0]) for tx in branches)
    resolved = world.make(oid=c["object_id"], operation="resolve", parents=expected,
                          payload={"value_type": "decimal", "value": "0.00"})
    world.apply(resolved, context=consent(world, resolved))
    with Session(world.engine) as db:
        assert heads(db, world.project_id, "Parameter", c["object_id"]) == [revision(resolved["changes"][0])]


@QA_PROPERTY
@given(st.integers(2, 5))
def test_run_cycle_generated_chain_rejected(world_factory, depth):
    world = world_factory()
    initial = world.make(kind="ResearchRun", payload={"title": "SYNTHETIC root", "run_type": "simulation"})
    world.apply(initial)
    current = initial["changes"][0]["object_id"]
    for index in range(depth):
        child = world.make(kind="ResearchRun", payload={"title": f"SYNTHETIC {index}", "run_type": "simulation", "parent_run_id": current})
        world.apply(child)
        current = child["changes"][0]["object_id"]
    cycle = world.make(kind="ResearchRun", oid=initial["changes"][0]["object_id"], operation="update",
                       parents=[revision(initial["changes"][0])], payload={"parent_run_id": current})
    with pytest.raises(ProtocolError, match="cycle"):
        world.apply(cycle)
