"""Real PostgreSQL authority, scientific visibility and crash invariants."""

import copy
from datetime import datetime, timedelta, timezone

import pytest
from researchhub.sync.authority import issue_grant
from researchhub.sync.kernel import CRASH_POINTS, heads
from researchhub.sync.models import (
    Audit,
    Inbox,
    ObjectRevision,
    Outbox,
    SyncTransaction,
)
from researchhub.sync.projection import object_view, project_status
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def count(db, model, project_id):
    return db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id))


def test_duplicate_and_identity_collision(world):
    tx = world.make()
    first = world.apply(tx)
    assert world.apply(copy.deepcopy(tx)) == first
    altered = copy.deepcopy(tx)
    altered["changes"][0]["payload"]["value"] = "1.800"
    with pytest.raises(ProtocolError, match="different content"):
        world.apply(altered)
    with Session(world.engine) as db:
        assert count(db, ObjectRevision, world.project_id) == 1
        assert count(db, Audit, world.project_id) == 1
        assert count(db, Inbox, world.project_id) == 1


@pytest.mark.parametrize("actor", ["codex", "chatgpt", "system"])
@pytest.mark.parametrize("kind,status", [("Evidence", "measured"), ("Decision", "rejected")])
def test_ai_inherits_existing_domain_authority(world, actor, kind, status):
    tx = world.make(actor=actor, kind=kind, payload={"title": "SYNTHETIC", "status": status})
    with pytest.raises(ProtocolError, match="Human"):
        world.apply(tx, actor=actor)


def test_human_consent_cannot_be_long_lived(world):
    tx = world.make(payload={"name": "SYNTHETIC", "is_confirmed": True})
    with Session(world.engine) as db, db.begin(), pytest.raises(ProtocolError, match="fresh"):
        issue_grant(db, world.context(), tx,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1))


def test_late_conflict_replay_reports_current_state(world):
    base = world.make()
    world.apply(base)
    oid = base["changes"][0]["object_id"]
    parent = revision(base["changes"][0])
    a = world.make(oid=oid, parents=[parent], operation="update",
                   payload={"value_type": "decimal", "value": "1.600"})
    b = world.make(oid=oid, parents=[parent], operation="update",
                   payload={"value_type": "decimal", "value": "1.800"})
    assert world.apply(a)["state"] == "ACCEPTED"
    assert world.apply(b)["state"] == "CANDIDATE"
    replay = world.apply(a)
    assert replay["state"] == "CANDIDATE"
    assert replay["receipt_state"] == "ACCEPTED"


@pytest.mark.parametrize("point", CRASH_POINTS)
def test_six_crash_points_rollback_and_retry(world, point):
    base = world.make()
    world.apply(base)
    parent = revision(base["changes"][0])
    oid = base["changes"][0]["object_id"]
    a = world.make(oid=oid, parents=[parent], operation="update", payload={"value": "1.600", "value_type": "decimal"})
    b = world.make(oid=oid, parents=[parent], operation="update", payload={"value": "1.800", "value_type": "decimal"})
    world.apply(a)
    with Session(world.engine) as db:
        old_audit = count(db, Audit, world.project_id)
    with pytest.raises(RuntimeError, match="injected crash"):
        world.apply(b, fault=point, local_outbox=True)
    with Session(world.engine) as db:
        assert heads(db, world.project_id, "Parameter", oid) == [revision(a["changes"][0])]
        assert count(db, ObjectRevision, world.project_id) == 2
        assert count(db, Audit, world.project_id) == old_audit
        assert count(db, Outbox, world.project_id) == 0
        assert db.get(SyncTransaction, a["transaction_id"]).state == "ACCEPTED"
        assert db.get(SyncTransaction, b["transaction_id"]) is None
        assert project_status(db, world.project_id)["received_cursor"] == 2
        assert object_view(db, world.project_id, "Parameter", oid)["accepted"]["value"] == "1.600"
    assert world.apply(b, local_outbox=True)["state"] == "CANDIDATE"


def test_caller_mutation_cannot_change_snapshot_between_flushes(world):
    tx = world.make()
    original = copy.deepcopy(tx)

    def mutate_caller(point):
        if point == "after_revision_insert":
            tx["changes"][0]["payload"]["value"] = "9.999"

    world.apply(tx, fault=mutate_caller, local_outbox=True)
    with Session(world.engine) as db:
        assert db.get(Outbox, original["transaction_id"]).envelope["transaction"] == original
        assert db.get(SyncTransaction, original["transaction_id"]).raw == original
