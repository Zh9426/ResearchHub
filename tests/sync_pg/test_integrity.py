"""Immutable SQL storage, parent scope, quarantine, Audit and artifact references."""

from hashlib import sha256
from uuid import uuid4

import pytest
from researchhub.sync.artifacts import register_verified_reference
from researchhub.sync.kernel import append_audit
from researchhub.sync.models import (
    Audit,
    ObjectRevision,
    SyncTransaction,
    VerifiedArtifact,
)
from researchhub.sync.projection import object_view, project_status
from researchhub.sync.protocol import ProtocolError, revision, transaction_digest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def test_pg_parent_edges_reject_self_or_retroactive_cycle(world):
    tx = world.make()
    world.apply(tx)
    change = tx["changes"][0]
    first = revision(change)
    second = world.make(oid=change["object_id"], parents=[first], operation="update",
                        payload={"value": "1.600", "value_type": "decimal"})
    world.apply(second)
    for parent in [first, revision(second["changes"][0])]:
        with world.engine.connect() as db:
            attempt = db.begin()
            try:
                with pytest.raises(DBAPIError):
                    db.execute(text("INSERT INTO sync_kernel_revision_parents (revision,parent,project_id,object_type,object_id) "
                                    "VALUES (:revision,:parent,:pid,'Parameter',:oid)"),
                               {"revision": first, "parent": parent, "pid": world.project_id, "oid": change["object_id"]})
            finally:
                attempt.rollback()


@pytest.mark.parametrize("model_sql", [
    "UPDATE sync_kernel_revisions SET document='{}' WHERE project_id=:pid",
    "DELETE FROM sync_kernel_revisions WHERE project_id=:pid",
    "UPDATE sync_kernel_audits SET action='tamper' WHERE project_id=:pid",
    "DELETE FROM sync_kernel_audits WHERE project_id=:pid",
])
def test_pg_history_and_audit_append_only(world, model_sql):
    tx = world.make()
    world.apply(tx)
    with pytest.raises(DBAPIError), world.engine.begin() as db:
        db.execute(text(model_sql), {"pid": world.project_id})
    with Session(world.engine) as db:
        assert db.get(ObjectRevision, revision(tx["changes"][0])).semantic == tx["changes"][0]


def test_audit_same_id_same_content_and_collision(world):
    tx = world.make()
    world.apply(tx)
    with Session(world.engine) as db, db.begin():
        row = db.get(Audit, tx["changes"][0]["audit_id"])
        assert append_audit(db, audit_id=row.audit_id, project_id=row.project_id,
                            transaction_id=row.transaction_id, action=row.action, content=row.content) is row
    colliding = world.make()
    colliding["changes"][0]["audit_id"] = tx["changes"][0]["audit_id"]
    with pytest.raises(ProtocolError, match="audit id"):
        world.apply(colliding)
    with Session(world.engine) as db:
        assert db.get(SyncTransaction, colliding["transaction_id"]) is None
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.project_id == world.project_id)) == 1


@pytest.mark.parametrize("mismatch", ["module", "schema", "protocol"])
def test_quarantine_advances_only_received_cursor(world, mismatch):
    tx = world.make()
    if mismatch == "module":
        tx["changes"][0]["module_snapshot_hash"] = "b" * 64
    elif mismatch == "schema":
        tx["schema_version"] = tx["changes"][0]["schema_version"] = 2
    else:
        tx["protocol_version"] = 2
    assert world.apply(tx)["state"] == "QUARANTINED"
    with Session(world.engine) as db:
        status = project_status(db, world.project_id)
        assert status["received_cursor"] == 1 and status["accepted_watermark"] == 0
        assert status["fully_synced"] is False
        assert db.get(SyncTransaction, tx["transaction_id"]).raw == tx
        assert db.scalar(select(func.count()).select_from(ObjectRevision).where(ObjectRevision.project_id == world.project_id)) == 0


def test_envelope_reencryption_mock_preserves_identity_and_commit_integrity(world):
    tx = world.make()
    envelope = {"transaction": tx, "digest": transaction_digest(tx), "commit_marker": "COMMIT",
                "signature": "SYNTHETIC-not-authentication", "key_epoch": 1,
                "nonce": "SYNTHETIC-a", "ciphertext_metadata": {"algorithm": "MOCK"}}
    result = world.apply(envelope)
    envelope["nonce"] = "SYNTHETIC-b"
    envelope["key_epoch"] = 2
    assert world.apply(envelope) == result
    envelope["commit_marker"] = "PARTIAL"
    with pytest.raises(ProtocolError, match="COMMIT"):
        world.apply(envelope)


def test_missing_parent_cross_project_type_and_object_rejected(world, world_factory):
    baseline = world.make()
    world.apply(baseline)
    parent = revision(baseline["changes"][0])
    other = world_factory()
    cross_project = other.make(oid=baseline["changes"][0]["object_id"], parents=[parent], operation="update")
    with pytest.raises(ProtocolError, match="same project/object/type"):
        other.apply(cross_project)
    wrong_object = world.make(parents=[parent], operation="update")
    with pytest.raises(ProtocolError, match="same project/object/type"):
        world.apply(wrong_object)
    wrong_type = world.make(kind="Metric", oid=baseline["changes"][0]["object_id"], parents=[parent], operation="update")
    with pytest.raises(ProtocolError, match="same project/object/type"):
        world.apply(wrong_type)
    missing = world.make(parents=["c" * 64], operation="update")
    with pytest.raises(ProtocolError, match="missing immutable parent"):
        world.apply(missing)


def test_parent_run_cycle_and_transaction_self_dependency_rejected(world):
    a, b = str(uuid4()), str(uuid4())
    tx = world.make(items=[{"object_type": "ResearchRun", "object_id": oid,
                           "payload": {"title": "SYNTHETIC cycle", "run_type": "simulation", "parent_run_id": parent}}
                          for oid, parent in [(a, b), (b, a)]])
    with pytest.raises(ProtocolError, match="cycle"):
        world.apply(tx)
    self_dep = world.make()
    self_dep["dependencies"] = [self_dep["transaction_id"]]
    with pytest.raises(ProtocolError, match="self dependency"):
        world.apply(self_dep)


def test_artifact_separate_metadata_project_epoch_dedup_and_checksum(world, world_factory):
    raw = b"SYNTHETIC QA bytes; not research data"
    checksum = sha256(raw).hexdigest()
    with Session(world.engine) as db, db.begin():
        for _ in range(2):
            register_verified_reference(db, world.project_id, 1, raw, checksum=checksum, size=len(raw))
        register_verified_reference(db, world.project_id, 2, raw)
    metadata = {"filename": "SYNTHETIC.csv", "size": len(raw), "checksum": checksum,
                "key_epoch": 1, "availability": "verified_reference", "sync_policy": "on_demand"}
    entries = [world.make(kind="Artifact", payload={**metadata, "metadata": {"description": label}})
               for label in ["separate A", "separate B"]]
    for tx in entries:
        assert world.apply(tx)["state"] == "ACCEPTED"
    with Session(world.engine) as db:
        assert db.scalar(select(func.count()).select_from(VerifiedArtifact).where(VerifiedArtifact.project_id == world.project_id)) == 2
        for tx in entries:
            assert object_view(db, world.project_id, "Artifact", tx["changes"][0]["object_id"])["accepted"]
    other = world_factory()
    with pytest.raises(ProtocolError, match="verified QA receipt"):
        other.apply(other.make(kind="Artifact", payload=metadata))
    wrong_epoch = world.make(kind="Artifact", payload={**metadata, "key_epoch": 3})
    with pytest.raises(ProtocolError, match="verified QA receipt"):
        world.apply(wrong_epoch)
    with pytest.raises(ProtocolError, match="verification failed"), Session(world.engine) as db, db.begin():
        register_verified_reference(db, world.project_id, 1, raw, checksum="c" * 64)
    wrong_hash = world.make(kind="Artifact", payload={**metadata, "sha256": "c" * 64})
    with pytest.raises(ProtocolError, match="conflicting artifact hashes"):
        world.apply(wrong_hash)
    for policy in ["local_only", "metadata_only", "encrypted_sync", "on_demand"]:
        assert world.apply(world.make(kind="Artifact", payload={**metadata, "sync_policy": policy,
                          "availability": "pending", "key_epoch": 3}))["state"] == "ACCEPTED"
