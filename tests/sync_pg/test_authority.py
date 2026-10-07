"""Trusted identity and fresh exact scientific consent, independently of payload."""

import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from researchhub.sync.authority import TrustedContext
from researchhub.sync.models import Grant, Principal, SyncTransaction
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy.orm import Session
from test_scientific import consent

PROTECTED = [
    ("ResearchRun", {"title": "SYNTHETIC", "run_type": "simulation", "human_conclusion": "final"}),
    ("HumanConclusion", {"content": "SYNTHETIC final", "status": "final"}),
    ("Parameter", {"name": "SYNTHETIC", "is_confirmed": True}),
    ("Metric", {"name": "SYNTHETIC", "status": "validated"}),
    ("Evidence", {"title": "SYNTHETIC", "status": "reproduced"}),
    ("Gate", {"status": "passed"}),
    ("Gate", {"criteria": [{"status": "passed", "description": "SYNTHETIC"}]}),
    ("GateCriterion", {"status": "passed"}),
    ("Decision", {"title": "SYNTHETIC", "status": "accepted"}),
    ("Claim", {"title": "SYNTHETIC", "status": "supported"}),
    ("ModuleUpgrade", {"module_id": "SYNTHETIC", "to_version": "0.3"}),
]


@pytest.mark.parametrize("actor", ["codex", "chatgpt", "system"])
@pytest.mark.parametrize("kind,payload", PROTECTED)
def test_ai_every_final_scientific_boundary(world, actor, kind, payload):
    tx = world.make(actor=actor, kind=kind, payload=payload)
    with pytest.raises(ProtocolError, match="Human"):
        world.apply(tx, actor=actor)
    with Session(world.engine) as db:
        assert db.get(SyncTransaction, tx["transaction_id"]) is None


def test_ai_cannot_upgrade_project_module_via_generic_update(world):
    tx = world.make(actor="codex", kind="Project", oid=world.project_id,
                    payload={"name": "SYNTHETIC", "module_version": "0.3-unreviewed"})
    with pytest.raises(ProtocolError, match="Human"):
        world.apply(tx, actor="codex")


def test_ai_payload_human_spoof_and_unregistered_revoked_principal(world):
    spoof = world.make(actor="codex")
    spoof["actor_type"] = spoof["changes"][0]["actor_type"] = "human"
    with pytest.raises(ProtocolError, match="registered principal"):
        world.apply(spoof, actor="codex")
    tx = world.make()
    with pytest.raises(ProtocolError, match="unregistered"):
        world.apply(tx, context=TrustedContext("11111111-1111-4111-8111-111111111111"))
    world.apply(tx)
    with Session(world.engine) as db, db.begin():
        db.get(Principal, world.context().principal_id).active = False
    with pytest.raises(ProtocolError, match="revoked"):
        world.apply(tx)


def test_human_session_not_final_consent_and_offline_final_not_supported(world):
    tx = world.make(payload={"name": "SYNTHETIC", "is_confirmed": True})
    with pytest.raises(ProtocolError, match="consent"):
        world.apply(tx)
    context = consent(world, tx)
    with pytest.raises(ProtocolError, match="Human"):
        world.apply(tx, context=world.context(grant_id=context.grant_id, mode="offline_proposal"))
    assert world.apply(tx, context=context)["state"] == "ACCEPTED"
    with Session(world.engine) as db, db.begin():
        grant = db.get(Grant, context.grant_id)
        assert grant.consumed is True
        grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert world.apply(tx, context=context)["state"] == "ACCEPTED"


@pytest.mark.parametrize("binding", ["user", "device", "session", "project", "object", "operation", "heads", "digest", "transaction", "expiry"])
def test_grant_exact_scope_and_expiry(world, binding):
    tx = world.make(payload={"name": "SYNTHETIC", "is_confirmed": True})
    context = consent(world, tx)
    with Session(world.engine) as db, db.begin():
        grant = db.get(Grant, context.grant_id)
        value = copy.deepcopy(grant.bindings)
        if binding in {"user", "device", "session", "project"}:
            value[binding + "_id"] = "11111111-1111-4111-8111-111111111111"
        elif binding in {"object", "operation", "heads"}:
            key = {"object": "object_id", "operation": "operation", "heads": "expected_heads"}[binding]
            value["objects"][0][key] = ["c" * 64] if binding == "heads" else "invalid-binding"
        elif binding == "digest":
            grant.digest = "c" * 64
        elif binding == "transaction":
            grant.transaction_id = str(uuid4())
        else:
            grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        grant.bindings = value
    with pytest.raises(ProtocolError, match="scoped consent"):
        world.apply(tx, context=context)


def test_ai_cannot_modify_existing_final_human_conclusion(world):
    final = world.make(kind="HumanConclusion", payload={"content": "SYNTHETIC approved", "status": "final"})
    world.apply(final, context=consent(world, final))
    change = final["changes"][0]
    attack = world.make(actor="codex", kind="HumanConclusion", oid=change["object_id"],
                        operation="update", parents=[revision(change)], payload={"content": "AI changed", "status": "draft"})
    with pytest.raises(ProtocolError, match="Human"):
        world.apply(attack, actor="codex")
