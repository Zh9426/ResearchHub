"""Shared fixtures exercised on PG with fresh identity namespaces per run."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from researchhub.sync.canonical import digest, strict_loads
from researchhub.sync.protocol import ProtocolError

CASES = json.loads((Path(__file__).resolve().parents[2] / "fixtures/sync/v1/kernel_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_transcript_kernel_states(world, case):
    identities, revisions = {}, {}

    def fresh(value):
        if value not in identities:
            identities[value] = str(uuid4())
        return identities[value]

    for step in case["steps"]:
        tx = strict_loads(step["raw"])
        person = world.people[step["actor"]]
        tx["transaction_id"] = tx["idempotency_key"] = fresh(tx["transaction_id"])
        tx["project_id"], tx["device_id"], tx["actor_id"] = world.project_id, person["device_id"], person["actor_id"]
        old_revisions = step["revisions"]
        for old_revision, c in zip(old_revisions, tx["changes"], strict=True):
            c["change_id"], c["audit_id"], c["object_id"] = fresh(c["change_id"]), fresh(c["audit_id"]), fresh(c["object_id"])
            c["project_id"], c["transaction_id"] = tx["project_id"], tx["transaction_id"]
            c["device_id"], c["actor_id"] = tx["device_id"], tx["actor_id"]
            c["parents"] = sorted(revisions[parent] for parent in c["parents"])
            revisions[old_revision] = digest(c)
        tx["ordered_change_ids"] = [c["change_id"] for c in tx["changes"]]
        context = world.context(step["actor"], mode=step["mode"])
        if step["expected_kernel"] in {"ACCEPTED", "CANDIDATE", "QUARANTINED"}:
            assert world.apply(tx, context=context)["state"] == step["expected_kernel"]
        else:
            with pytest.raises(ProtocolError) as caught:
                world.apply(tx, context=context)
            assert caught.value.code == step["expected_kernel"]
