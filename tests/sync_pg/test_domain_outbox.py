"""QA mapping and real PostgreSQL Domain/Audit/Outbox atomicity."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))

from researchhub import models as domain
from researchhub.modules import load_modules
from researchhub.sync.canonical import digest
from researchhub.sync.domain_qa import create_run_batch, parameter_payload
from researchhub.sync.kernel import CRASH_POINTS
from researchhub.sync.models import (
    Audit,
    Inbox,
    ObjectRevision,
    Outbox,
    SyncTransaction,
)
from researchhub.sync.projection import object_view
from researchhub.sync.protocol import ProtocolError


def test_decimal_domain_carrier_preserves_raw_precision():
    mapped = parameter_payload({
        "name": "SYNTHETIC pressure", "value_type": "decimal", "value": "1.600",
        "unit": "MPa", "is_confirmed": False,
    })
    assert mapped.get("value") == {"value_type": "decimal", "value": "1.600"}
    assert mapped["value_type"] == "object"
    assert mapped["unit"] == "MPa"


@pytest.fixture
def domain_world(world_factory, engine):
    manifest = load_modules()["generic"]
    world = world_factory(module_hash=digest(manifest))
    with engine.begin() as db:
        domain.Base.metadata.create_all(db)
        db.execute(text("DROP TRIGGER IF EXISTS sync_qa_immutable ON audit_logs"))
        db.execute(text("CREATE TRIGGER sync_qa_immutable BEFORE UPDATE OR DELETE ON audit_logs "
                        "FOR EACH ROW EXECUTE FUNCTION sync_kernel_immutable()"))
    with Session(engine) as db, db.begin():
        user = domain.User(id=world.people["human"]["user_id"],
                           email=str(uuid4()) + "@example.invalid", display_name="SYNTHETIC QA",
                           password_hash="SYNTHETIC-NO-LOGIN")
        db.add(user)
        db.flush()
        db.add(domain.Project(id=world.project_id, owner_id=user.id, name="SYNTHETIC Sync QA",
                              module_id="generic", module_version=manifest["version"],
                              module_snapshot=manifest))
    return world


def action():
    return {
        "run": {"title": "SYNTHETIC Run", "run_type": "simulation", "observation": "QA only"},
        "parameters": [{"name": f"SYNTHETIC p{i}", "value_type": "decimal",
                        "value": "1.600" if i else "0.000", "unit": "MPa"} for i in range(6)],
        "metrics": [{"name": f"SYNTHETIC m{i}", "value_type": "decimal",
                     "value": "0.600", "status": "unknown", "unit": None} for i in range(3)],
        "artifacts": [{"filename": f"SYNTHETIC a{i}.csv", "size": 0, "checksum": "b" * 64,
                       "sync_policy": "metadata_only", "availability": "pending", "key_epoch": 1} for i in range(2)],
    }


def counts(db, world):
    result = {}
    for model in [domain.ResearchRun, domain.Artifact, domain.AuditLog, Audit, Inbox, Outbox, ObjectRevision]:
        result[model.__tablename__] = db.scalar(select(func.count()).select_from(model).where(model.project_id == world.project_id))
    for model in [domain.Parameter, domain.Metric]:
        result[model.__tablename__] = db.scalar(select(func.count()).select_from(model).join(
            domain.ResearchRun, model.run_id == domain.ResearchRun.id).where(domain.ResearchRun.project_id == world.project_id))
    return result


def test_real_domain_run_six_parameters_three_metrics_two_metadata_atomic(domain_world):
    world = domain_world
    tid = str(uuid4())
    with Session(world.engine) as db, db.begin():
        receipt = create_run_batch(db, world.context(), world.project_id, transaction_id=tid, **action())
        assert receipt["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        actual = counts(db, world)
        assert actual == {"research_runs": 1, "parameters": 6, "metrics": 3, "artifacts": 2,
                          "audit_logs": 12, "sync_kernel_audits": 12, "sync_kernel_inbox": 1,
                          "sync_kernel_outbox": 1, "sync_kernel_revisions": 12}
        outbox = db.get(Outbox, tid)
        changes = outbox.envelope["transaction"]["changes"]
        assert len(changes) == 12
        assert db.scalar(select(domain.Parameter).where(domain.Parameter.run_id == changes[0]["object_id"],
                         domain.Parameter.name == "SYNTHETIC p1")).value == {"value_type": "decimal", "value": "1.600"}
        assert db.scalar(select(domain.Metric).where(domain.Metric.run_id == changes[0]["object_id"])).value == "0.600"
        assert all(object_view(db, world.project_id, c["object_type"], c["object_id"])["accepted"] is not None for c in changes)
    with Session(world.engine) as db, db.begin():
        assert create_run_batch(db, world.context(), world.project_id, transaction_id=tid, **action()) == receipt
        assert counts(db, world) == actual


@pytest.mark.parametrize("field", ["run", "parameters", "metrics", "artifacts"])
def test_domain_replay_rejects_changed_action(domain_world, field):
    world = domain_world
    tid = str(uuid4())
    with Session(world.engine) as db, db.begin():
        create_run_batch(db, world.context(), world.project_id, transaction_id=tid, **action())
        original = counts(db, world)
    changed = action()
    if field == "run":
        changed[field]["title"] = "SYNTHETIC changed retry"
    else:
        changed[field] = changed[field][:-1]
    with pytest.raises(ProtocolError) as rejected, Session(world.engine) as db, db.begin():
        create_run_batch(db, world.context(), world.project_id, transaction_id=tid, **changed)
    assert rejected.value.code == "IDENTITY_COLLISION"
    with Session(world.engine) as db:
        assert counts(db, world) == original


@pytest.mark.parametrize("point", CRASH_POINTS)
def test_domain_audit_outbox_all_rollback(domain_world, point):
    world = domain_world
    with pytest.raises(RuntimeError, match="injected crash"), Session(world.engine) as db, db.begin():
        create_run_batch(db, world.context(), world.project_id, fault=point, **action())
    with Session(world.engine) as db:
        assert all(value == 0 for value in counts(db, world).values())
    with Session(world.engine) as db, db.begin():
        assert create_run_batch(db, world.context(), world.project_id, **action())["state"] == "ACCEPTED"


@pytest.mark.parametrize("sql", ["UPDATE audit_logs SET action='tamper' WHERE project_id=:pid",
                                 "DELETE FROM audit_logs WHERE project_id=:pid"])
def test_actual_pg_domain_audit_append_only(domain_world, sql):
    world = domain_world
    with Session(world.engine) as db, db.begin():
        create_run_batch(db, world.context(), world.project_id, **action())
    with pytest.raises(DBAPIError), world.engine.begin() as db:
        db.execute(text(sql), {"pid": world.project_id})
    with Session(world.engine) as db:
        assert counts(db, world)["audit_logs"] == 12


def test_one_parameter_create_collision_withdraws_entire_twelve_member_domain_projection(domain_world):
    world = domain_world
    with Session(world.engine) as db, db.begin():
        first = create_run_batch(db, world.context(), world.project_id, **action())
        changes = db.get(Outbox, first["transaction_id"]).envelope["transaction"]["changes"]
    dependent = world.make(kind="Metric", payload={"name": "SYNTHETIC derived",
                           "value": "0.800", "value_type": "decimal", "run_id": changes[0]["object_id"]})
    world.apply(dependent)
    collision = world.make(oid=changes[1]["object_id"], payload={"name": "SYNTHETIC p0", "value": "2.000",
                           "value_type": "decimal", "run_id": changes[0]["object_id"]})
    assert world.apply(collision)["state"] == "CANDIDATE"
    with Session(world.engine) as db:
        assert db.get(SyncTransaction, first["transaction_id"]).state == "CANDIDATE"
        assert db.get(SyncTransaction, dependent["transaction_id"]).state == "CANDIDATE"
        assert all(object_view(db, world.project_id, c["object_type"], c["object_id"])["accepted"] is None for c in changes)
        assert counts(db, world)["audit_logs"] == 12  # Origin history retained, never erased.
