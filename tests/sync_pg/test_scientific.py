"""Whole-batch visibility, N-head review, lifecycle and scientific provenance."""

import copy
from dataclasses import replace

import pytest
from researchhub.sync.authority import issue_grant
from researchhub.sync.kernel import heads
from researchhub.sync.models import Audit, SyncConflict, SyncTransaction
from researchhub.sync.projection import object_view, project_status
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy import select
from sqlalchemy.orm import Session


def item(kind, oid, payload, parent=None, operation="create"):
    return {"object_type": kind, "object_id": oid, "payload": payload,
            "parents": [parent] if parent else [], "operation": operation}


def consent(world, tx, actor="human"):
    with Session(world.engine) as db, db.begin():
        grant = issue_grant(db, world.context(actor), tx)
    return replace(world.context(actor), grant_id=grant)


def divergence(world):
    base = world.make()
    world.apply(base)
    c = base["changes"][0]
    branches = [world.make(oid=c["object_id"], parents=[revision(c)], operation="update",
                          payload={"value_type": "decimal", "value": value})
                for value in ["1.600", "1.800"]]
    for tx in branches:
        world.apply(tx)
    return c, branches


def test_whole_batch_late_divergence_dependencies_and_independent(world):
    from uuid import uuid4
    run, parameter, metric = [str(uuid4()) for _ in range(3)]
    base = world.make(items=[
        item("ResearchRun", run, {"title": "SYNTHETIC baseline", "run_type": "simulation"}),
        item("Parameter", parameter, {"name": "pressure", "value": "1.400", "value_type": "decimal", "run_id": run}),
        item("Metric", metric, {"name": "IoU", "value": "0.400", "value_type": "decimal", "run_id": run}),
    ])
    world.apply(base)
    a = world.make(items=[
        item("ResearchRun", run, {"observation": "SYNTHETIC A"}, revision(base["changes"][0]), "update"),
        item("Parameter", parameter, {"value": "1.600", "value_type": "decimal"}, revision(base["changes"][1]), "update"),
        item("Metric", metric, {"value": "0.600", "value_type": "decimal"}, revision(base["changes"][2]), "update"),
    ])
    assert world.apply(a)["state"] == "ACCEPTED"
    dependent = world.make(kind="Metric", payload={"name": "SYNTHETIC derived", "value": "0.800", "value_type": "decimal", "run_id": run})
    assert world.apply(dependent)["state"] == "ACCEPTED"
    descendant = world.make(kind="Note", payload={"title": "SYNTHETIC dependent"}, dependencies=[dependent["transaction_id"]])
    world.apply(descendant)
    independent = world.make(kind="Note", payload={"title": "SYNTHETIC independent"})
    world.apply(independent)
    b = world.make(oid=parameter, parents=[revision(base["changes"][1])], operation="update",
                   payload={"value": "1.800", "value_type": "decimal"})
    assert world.apply(b)["state"] == "CANDIDATE"
    with Session(world.engine) as db:
        for tx in [a, b, dependent, descendant]:
            assert db.get(SyncTransaction, tx["transaction_id"]).state == "CANDIDATE"
        assert db.get(SyncTransaction, independent["transaction_id"]).state == "ACCEPTED"
        for kind, oid in [("ResearchRun", run), ("Parameter", parameter), ("Metric", metric)]:
            assert object_view(db, world.project_id, kind, oid)["accepted"] is None
        view = object_view(db, world.project_id, "Parameter", parameter)
        assert view["base"]["value"] == "1.400"
        assert {c["document"]["value"] for c in view["candidates"]} == {"1.600", "1.800"}
        assert db.scalar(select(Audit).where(Audit.transaction_id == a["transaction_id"], Audit.action == "invalidate_sync_projection"))
        assert project_status(db, world.project_id)["fully_synced"] is False
    partial = world.make(oid=parameter, parents=sorted([revision(a["changes"][1]), revision(b["changes"][0])]),
                         operation="resolve", payload={"value": "1.700", "value_type": "decimal"})
    with pytest.raises(ProtocolError, match="every affected batch"):
        world.apply(partial, context=consent(world, partial))
    full = world.make(items=[
        item("ResearchRun", run, {"observation": "SYNTHETIC reviewed"}, revision(a["changes"][0]), "resolve"),
        {"object_type": "Parameter", "object_id": parameter, "operation": "resolve",
         "parents": partial["changes"][0]["parents"], "payload": {"value": "1.700", "value_type": "decimal"}},
        item("Metric", metric, {"value": "0.700", "value_type": "decimal"}, revision(a["changes"][2]), "resolve"),
    ])
    assert world.apply(full, context=consent(world, full))["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        assert object_view(db, world.project_id, "Parameter", parameter)["accepted"]["value"] == "1.700"
        assert db.get(SyncTransaction, dependent["transaction_id"]).state == "CANDIDATE"


def test_n_heads_and_stale_exact_resolution(world):
    base, branches = divergence(world)
    old_heads = sorted(revision(tx["changes"][0]) for tx in branches)
    resolve = world.make(oid=base["object_id"], operation="resolve", parents=old_heads,
                         payload={"value": "1.700", "value_type": "decimal"})
    context = consent(world, resolve)
    third = world.make(oid=base["object_id"], operation="update", parents=[revision(base)],
                       payload={"value": "2.000", "value_type": "decimal"})
    world.apply(third)
    with pytest.raises(ProtocolError, match="actual heads changed"):
        world.apply(resolve, context=context)
    with Session(world.engine) as db:
        view = object_view(db, world.project_id, "Parameter", base["object_id"])
        assert view["candidate_count"] == 3
        assert db.get(SyncTransaction, resolve["transaction_id"]) is None


def test_offline_resolution_proposals_fork_then_fresh_review(world):
    base, branches = divergence(world)
    original_heads = sorted(revision(tx["changes"][0]) for tx in branches)
    proposals = [world.make(actor=actor, oid=base["object_id"], operation="resolve", parents=original_heads,
                            payload={"value": value, "value_type": "decimal"})
                 for actor, value in [("human", "1.700"), ("human_b", "1.900")]]
    for actor, tx in zip(["human", "human_b"], proposals, strict=True):
        assert world.apply(tx, context=world.context(actor, mode="offline_proposal"))["state"] == "CANDIDATE"
    with Session(world.engine) as db:
        actual = heads(db, world.project_id, "Parameter", base["object_id"])
        assert actual == sorted(revision(tx["changes"][0]) for tx in proposals)
        assert object_view(db, world.project_id, "Parameter", base["object_id"])["accepted"] is None
    final = world.make(oid=base["object_id"], operation="resolve", parents=actual,
                       payload={"value": "1.800", "value_type": "decimal"})
    assert world.apply(final, context=consent(world, final))["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        conflict = db.scalar(select(SyncConflict).where(SyncConflict.project_id == world.project_id,
                             SyncConflict.head_set == actual))
        assert conflict.status == "resolved"
        assert conflict.resolution_revision == revision(final["changes"][0])
        assert project_status(db, world.project_id)["fully_synced"] is True


def test_trash_old_edit_no_resurrection_explicit_review_then_restore(world):
    base = world.make(kind="ResearchRun", payload={"title": "SYNTHETIC", "run_type": "simulation"})
    world.apply(base)
    c = base["changes"][0]
    trash = world.make(kind="ResearchRun", oid=c["object_id"], operation="trash", parents=[revision(c)], payload={})
    edit = world.make(kind="ResearchRun", oid=c["object_id"], operation="update", parents=[revision(c)], payload={"observation": "offline"})
    world.apply(trash)
    world.apply(edit)
    with Session(world.engine) as db:
        view = object_view(db, world.project_id, "ResearchRun", c["object_id"])
        assert view["lifecycle"] == "trashed" and view["visible"] is False
        current = view["heads"]
    review = world.make(kind="ResearchRun", oid=c["object_id"], operation="resolve", parents=current, payload={"observation": "reviewed offline"})
    world.apply(review, context=consent(world, review))
    restore = world.make(kind="ResearchRun", oid=c["object_id"], operation="restore", parents=[revision(review["changes"][0])], payload={})
    with pytest.raises(ProtocolError, match="consent"):
        world.apply(restore)
    assert world.apply(restore, context=consent(world, restore))["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        assert object_view(db, world.project_id, "ResearchRun", c["object_id"])["visible"] is True
    purge = copy.deepcopy(restore)
    purge["changes"][0]["operation"] = "purge"
    with pytest.raises(ProtocolError):
        world.apply(purge)


def test_closed_run_cannot_accept_new_scientific_child_or_update(world):
    base = world.make(kind="ResearchRun", payload={"title": "SYNTHETIC", "run_type": "simulation"})
    world.apply(base)
    c = base["changes"][0]
    trash = world.make(kind="ResearchRun", oid=c["object_id"], operation="trash", parents=[revision(c)], payload={})
    world.apply(trash)
    child = world.make(payload={"name": "SYNTHETIC", "run_id": c["object_id"]})
    assert world.apply(child)["state"] == "CANDIDATE"
    update = world.make(kind="ResearchRun", oid=c["object_id"], operation="update",
                        parents=[revision(trash["changes"][0])], payload={"observation": "SYNTHETIC"})
    assert world.apply(update)["state"] == "CANDIDATE"
