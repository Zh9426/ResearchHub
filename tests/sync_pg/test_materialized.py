"""Full scientific documents and nested evidence dependencies are validated."""

from uuid import uuid4

import pytest
from researchhub.sync.models import SyncTransaction
from researchhub.sync.projection import object_view
from researchhub.sync.protocol import ProtocolError, revision
from sqlalchemy.orm import Session
from test_scientific import consent, divergence


@pytest.mark.parametrize("patch", [{"value": "not-a-decimal"}, {"value_type": "integer"}])
def test_inherited_decimal_type_validates_full_document(world, patch):
    base = world.make()
    world.apply(base)
    change = base["changes"][0]
    invalid = world.make(oid=change["object_id"], operation="update",
                         parents=[revision(change)], payload=patch)
    with pytest.raises(ProtocolError):
        world.apply(invalid)
    with Session(world.engine) as db:
        assert db.get(SyncTransaction, invalid["transaction_id"]) is None
        assert object_view(db, world.project_id, "Parameter", change["object_id"])["accepted"]["value"] == "1.400"


def test_resolution_validates_inherited_type(world):
    base, branches = divergence(world)
    tx = world.make(oid=base["object_id"], operation="resolve",
                    parents=sorted(revision(t["changes"][0]) for t in branches),
                    payload={"value": "invalid"})
    with pytest.raises(ProtocolError):
        world.apply(tx, context=consent(world, tx))


def test_nested_criterion_dependency_pauses_passed_gate(world):
    base = world.make(kind="Evidence", payload={"title": "SYNTHETIC base", "status": "proposed"})
    world.apply(base)
    change = base["changes"][0]
    branch = world.make(kind="Evidence", oid=change["object_id"], operation="update",
                        parents=[revision(change)], payload={"title": "SYNTHETIC A"})
    world.apply(branch)
    gate = world.make(kind="Gate", payload={"name": "SYNTHETIC Gate", "status": "passed",
                      "criteria": [{"id": str(uuid4()), "status": "passed", "evidence_ids": [change["object_id"]]}]})
    world.apply(gate, context=consent(world, gate))
    fork = world.make(kind="Evidence", oid=change["object_id"], operation="update",
                      parents=[revision(change)], payload={"title": "SYNTHETIC B"})
    world.apply(fork)
    with Session(world.engine) as db:
        assert db.get(SyncTransaction, gate["transaction_id"]).state == "CANDIDATE"
        assert object_view(db, world.project_id, "Gate", gate["changes"][0]["object_id"])["accepted"] is None


@pytest.mark.parametrize("endpoint", ["missing", "cross_project"])
def test_nested_criterion_invalid_endpoint_rejected(world, world_factory, endpoint):
    oid = str(uuid4())
    if endpoint == "cross_project":
        other = world_factory()
        other.apply(other.make(kind="Evidence", oid=oid, payload={"title": "SYNTHETIC"}))
    gate = world.make(kind="Gate", payload={"name": "SYNTHETIC", "criteria": [{"evidence_ids": [oid]}]})
    with pytest.raises(ProtocolError):
        world.apply(gate)


def test_ai_old_draft_cannot_withdraw_final_conclusion(world):
    base = world.make(kind="HumanConclusion", payload={"content": "SYNTHETIC draft", "status": "draft"})
    world.apply(base)
    change = base["changes"][0]
    final = world.make(kind="HumanConclusion", oid=change["object_id"], operation="update",
                       parents=[revision(change)], payload={"content": "SYNTHETIC approved", "status": "final"})
    world.apply(final, context=consent(world, final))
    attack = world.make(actor="codex", kind="HumanConclusion", oid=change["object_id"], operation="update",
                        parents=[revision(change)], payload={"content": "SYNTHETIC AI old draft"})
    with pytest.raises(ProtocolError):
        world.apply(attack, actor="codex")
    with Session(world.engine) as db:
        assert object_view(db, world.project_id, "HumanConclusion", change["object_id"])["accepted"]["status"] == "final"
