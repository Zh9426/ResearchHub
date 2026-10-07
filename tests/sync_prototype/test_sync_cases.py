"""Synthetic protocol cases use temporary SQLite files, never production services."""

from dataclasses import replace
from hashlib import sha256
from uuid import uuid4

import pytest

from prototypes.sync_sprint0.model import ChangeSet, ProtocolError
from prototypes.sync_sprint0.relay import Relay
from prototypes.sync_sprint0.replica import Replica


@pytest.fixture
def nodes(tmp_path):
    project = str(uuid4())
    relay = Relay(tmp_path / "relay.sqlite")
    a = Replica(tmp_path / "a.sqlite", project)
    b = Replica(tmp_path / "b.sqlite", project)
    relay.register_device(a.device_id, "human")
    relay.register_device(b.device_id, "human")
    return project, relay, a, b


def seed(nodes, kind="Parameter", payload=None):
    _, relay, a, b = nodes
    change = a.create(kind, payload or {"name": "pressure", "value": 1.4})
    a.push_pending(relay)
    b.pull(relay)
    return change.object_id


def converge(relay, a, b):
    a.push_pending(relay)
    b.push_pending(relay)
    a.pull(relay)
    b.pull(relay)


def test_case01_offline_run_creation_survives_on_b(nodes):
    _, relay, a, b = nodes
    change = a.create("ResearchRun", {"title": "synthetic run"})
    assert b.state(change.object_id) is None
    a.push_pending(relay)
    b.pull(relay)
    assert b.state(change.object_id)["projection"]["title"] == "synthetic run"


def test_case02_independent_offline_runs_both_survive(nodes):
    _, relay, a, b = nodes
    x = a.create("ResearchRun", {"title": "A"})
    y = b.create("ResearchRun", {"title": "B"})
    converge(relay, a, b)
    assert x.object_id != y.object_id
    for replica in (a, b):
        assert replica.state(x.object_id)["projection"]["title"] == "A"
        assert replica.state(y.object_id)["projection"]["title"] == "B"


def test_case03_parameter_fork_preserves_both_values(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes)
    a.update(obj, {"value": 1.6})
    b.update(obj, {"value": 1.8})
    converge(relay, a, b)
    assert a.state(obj) == b.state(obj)
    state = a.state(obj)
    assert state["conflict"]
    assert state["projection"]["value"] == 1.4
    assert {c["document"]["value"] for c in state["candidates"]} == {1.6, 1.8}


def test_case04_duplicate_push_returns_original_receipt(nodes):
    _, relay, a, _ = nodes
    change = a.create("ResearchRun", {"title": "A"})
    tx = str(uuid4())
    receipt = relay.push([change], tx, a.device_id)
    assert relay.push([change], tx, a.device_id) == receipt
    assert len(relay.pull(a.project_id, 0)) == 1


def test_case05_duplicate_pull_is_idempotent(nodes):
    _, relay, a, b = nodes
    change = a.create("ResearchRun", {"title": "A"})
    a.push_pending(relay)
    batch = relay.pull(a.project_id, 0)[0]
    b.apply_batch(batch)
    before = b.state(change.object_id), b.audit_count(), b.cursor
    b.apply_batch(batch)
    assert (b.state(change.object_id), b.audit_count(), b.cursor) == before


def test_case06_push_halfway_crash_has_no_visible_partial_batch(nodes):
    _, relay, a, b = nodes
    x = a.create("ResearchRun", {"title": "A"})
    y = a.create("Parameter", {"name": "pressure", "value": 1.4})
    tx = str(uuid4())
    with pytest.raises(RuntimeError, match="injected"):
        relay.push([x, y], tx, a.device_id, crash_after=1)
    assert relay.pull(a.project_id, 0) == []
    relay.push([x, y], tx, a.device_id)
    b.pull(relay)
    assert b.state(x.object_id) and b.state(y.object_id)


def test_case07_same_sha_keeps_metadata_ids_and_deduplicates_bytes(nodes):
    _, relay, a, b = nodes
    data = b"synthetic PNG bytes"
    digest = sha256(data).hexdigest()
    payload = {"filename": "a.png", "sha256": digest, "size": len(data),
               "key_epoch": 1, "content_hex": data.hex()}
    x = a.create("Artifact", payload)
    y = b.create("Artifact", {**payload, "filename": "b.png"})
    converge(relay, a, b)
    assert x.object_id != y.object_id
    assert a.blob_count() == b.blob_count() == relay.blob_count() == 1
    assert a.state(x.object_id) and a.state(y.object_id)


def test_case08_trash_and_offline_edit_conflict_without_resurrection(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes, "ResearchRun", {"title": "base"})
    a.trash(obj)
    b.update(obj, {"title": "offline"})
    converge(relay, a, b)
    state = a.state(obj)
    assert state["conflict"] and state["lifecycle"] == "trashed"
    with pytest.raises(ProtocolError, match="conflict"):
        b.update(obj, {"title": "resurrection"})


def test_case09_human_conclusion_never_auto_merges(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes, "HumanConclusion", {"text": "base"})
    a.update(obj, {"text": "conclusion A"})
    b.update(obj, {"text": "conclusion B"})
    converge(relay, a, b)
    assert a.state(obj)["conflict"]
    assert {c["document"]["text"] for c in a.state(obj)["candidates"]} == {
        "conclusion A", "conclusion B"}


def test_case10_competing_audits_both_retained_without_duplicates(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes)
    a.update(obj, {"value": 1.6})
    b.update(obj, {"value": 1.8})
    converge(relay, a, b)
    assert a.audit_count() == b.audit_count() == 3
    for batch in relay.pull(a.project_id, 0):
        a.apply_batch(batch)
        b.apply_batch(batch)
    assert a.audit_count() == b.audit_count() == 3


def test_transaction_and_change_identity_collisions_reject(nodes):
    _, relay, a, _ = nodes
    change = a.create("ResearchRun", {"title": "A"})
    tx = str(uuid4())
    relay.push([change], tx, a.device_id)
    collision = replace(change, payload={"title": "tampered"})
    with pytest.raises(ProtocolError, match="collision"):
        relay.push([collision], tx, a.device_id)
    with pytest.raises(ProtocolError, match="collision"):
        relay.push([collision], str(uuid4()), a.device_id)


def test_failed_pull_rolls_back_inbox_domain_audit_and_cursor(nodes):
    _, relay, a, b = nodes
    changes = [a.create("ResearchRun", {"title": title}) for title in ("A", "B")]
    relay.push(changes, str(uuid4()), a.device_id)
    batch = relay.pull(a.project_id, 0)[0]
    with pytest.raises(RuntimeError, match="injected"):
        b.apply_batch(batch, crash_after=1)
    assert b.cursor == 0 and b.audit_count() == 0 and b.inbox_count() == 0
    assert all(b.state(c.object_id) is None for c in changes)
    b.apply_batch(batch)
    assert b.cursor == 1 and b.audit_count() == 2


def test_corrupt_artifact_rejects_before_acceptance(nodes):
    _, relay, a, _ = nodes
    data = b"synthetic"
    change = a.create("Artifact", {"filename": "a", "sha256": sha256(data).hexdigest(),
                                  "size": len(data), "key_epoch": 1,
                                  "content_hex": data.hex()})
    corrupt = replace(change, payload={**change.payload, "content_hex": b"bad".hex()})
    with pytest.raises(ProtocolError, match="checksum"):
        relay.push([corrupt], str(uuid4()), a.device_id)
    assert relay.pull(a.project_id, 0) == []


@pytest.mark.parametrize("field,value", [("schema_version", 999), ("object_type", "Unknown"),
                                         ("operation", "purge")])
def test_unknown_schema_type_and_purge_reject(nodes, field, value):
    _, relay, a, _ = nodes
    change = a.create("ResearchRun", {"title": "A"})
    with pytest.raises(ProtocolError):
        relay.push([replace(change, **{field: value})], str(uuid4()), a.device_id)


def test_ai_cannot_bypass_human_authority_with_actor_claim(nodes, tmp_path):
    project, relay, a, _ = nodes
    ai = Replica(tmp_path / "ai.sqlite", project, principal_type="ai")
    relay.register_device(ai.device_id, "ai")
    human_change = a.create("HumanConclusion", {"text": "human"})
    forged = replace(human_change, device_id=ai.device_id, actor_type="human")
    with pytest.raises(ProtocolError, match="actor claim.*principal"):
        relay.push([forged], str(uuid4()), ai.device_id)
    with pytest.raises(ProtocolError, match="human-only"):
        relay.push([replace(forged, actor_type="ai")], str(uuid4()), ai.device_id)
    note = ai.create("Note", {"text": "observation"})
    forged_note = replace(note, payload={"text": "x", "human_conclusion": "approved"},
                          actor_type="human")
    with pytest.raises(ProtocolError, match="actor claim.*principal"):
        relay.push([forged_note], str(uuid4()), ai.device_id)
    with pytest.raises(ProtocolError, match="human-only"):
        relay.push([replace(forged_note, actor_type="ai")], str(uuid4()), ai.device_id)


def test_concurrent_resolutions_form_new_conflict(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes)
    a.update(obj, {"value": 1.6})
    b.update(obj, {"value": 1.8})
    converge(relay, a, b)
    heads = a.state(obj)["heads"]
    with pytest.raises(ProtocolError, match="head set"):
        a.resolve(obj, heads[:1], {"name": "pressure", "value": 1.7})
    a.resolve(obj, heads, {"name": "pressure", "value": 1.7})
    b.resolve(obj, heads, {"name": "pressure", "value": 1.9})
    converge(relay, a, b)
    assert a.state(obj) == b.state(obj) and a.state(obj)["conflict"]
    assert {c["document"]["value"] for c in a.state(obj)["candidates"]} == {1.7, 1.9}
    a.resolve(obj, a.state(obj)["heads"], {"name": "pressure", "value": 1.75})
    converge(relay, a, b)
    assert not b.state(obj)["conflict"] and b.state(obj)["projection"]["value"] == 1.75
    assert a.audit_count() == b.audit_count() == 6


def test_missing_dependency_quarantines_and_retries_without_replacement(nodes):
    _, relay, a, b = nodes
    first = a.create("ResearchRun", {"title": "base"})
    second = a.update(first.object_id, {"title": "second"})
    relay.push([first], str(uuid4()), a.device_id)
    relay.push([second], str(uuid4()), a.device_id)
    batches = relay.pull(a.project_id, 0)
    assert b.apply_batch(batches[1]) is False
    assert b.cursor == 0 and b.state(first.object_id) is None
    assert b.quarantine_count() == 1
    b.apply_batch(batches[0])
    b.apply_batch(batches[1])
    assert b.cursor == 2 and b.quarantine_count() == 0
    assert b.state(first.object_id)["projection"]["title"] == "second"


def test_device_uuid_is_durable(nodes):
    _, _, a, _ = nodes
    reopened = Replica(a.path, a.project_id)
    assert reopened.device_id == a.device_id


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_scientific_numbers_reject(nodes, value):
    _, _, a, _ = nodes
    with pytest.raises(ProtocolError):
        a.create("Parameter", {"name": "pressure", "value": value})


def test_dedup_never_crosses_project_or_key_epoch(nodes, tmp_path):
    _, relay, a, _ = nodes
    other = Replica(tmp_path / "other.sqlite", str(uuid4()))
    relay.register_device(other.device_id, "human")
    data = b"same synthetic bytes"
    payload = {"filename": "x", "sha256": sha256(data).hexdigest(), "size": len(data),
               "key_epoch": 1, "content_hex": data.hex()}
    a.create("Artifact", payload)
    a.create("Artifact", {**payload, "key_epoch": 2})
    other.create("Artifact", payload)
    a.push_pending(relay)
    other.push_pending(relay)
    assert relay.blob_count() == 3


def test_changeset_hash_is_canonical_and_strict(nodes):
    _, _, a, _ = nodes
    c = a.create("ResearchRun", {"title": "x", "description": "y"})
    assert c.revision == replace(c, payload={"description": "y", "title": "x"}).revision
    assert ChangeSet.from_json(c.to_json()) == c
    with pytest.raises(ProtocolError):
        ChangeSet.from_json(c.to_json().replace('"schema_version":1', '"schema_version":NaN'))


def test_restore_is_explicit_and_stale_create_cannot_reuse_object_identity(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes, "ResearchRun", {"title": "base"})
    a.trash(obj)
    with pytest.raises(ProtocolError, match="restore"):
        a.update(obj, {"title": "not allowed"})
    a.restore(obj)
    converge(relay, a, b)
    assert b.state(obj)["lifecycle"] == "active"
    forged = replace(a.create("ResearchRun", {"title": "x"}), object_id=obj)
    with pytest.raises(ProtocolError, match="identity"):
        relay.push([forged], str(uuid4()), a.device_id)


def test_restart_preserves_outbox_and_receipt_and_cursor(nodes):
    project, relay, a, b = nodes
    change = a.create("ResearchRun", {"title": "durable"})
    reopened_a = Replica(a.path, project)
    receipt = reopened_a.push_pending(relay)[0]
    reopened_relay = Relay(relay.path)
    reopened_b = Replica(b.path, project)
    reopened_b.pull(reopened_relay, limit=1)
    again = Replica(b.path, project)
    assert again.cursor == 1 and again.audit_count() == 1
    assert again.state(change.object_id)["projection"]["title"] == "durable"
    assert reopened_relay.push([change], receipt["transaction_id"], a.device_id) == receipt
    assert reopened_a.push_pending(reopened_relay) == []


def test_out_of_order_sibling_delivery_eventually_converges(nodes):
    _, relay, a, b = nodes
    obj = seed(nodes)
    a.update(obj, {"value": 1.6})
    b.update(obj, {"value": 1.8})
    a.push_pending(relay)
    b.push_pending(relay)
    batches = relay.pull(a.project_id, 1, limit=2)
    assert len(batches) == 2 and batches[0]["sequence"] < batches[1]["sequence"]
    assert b.apply_batch(batches[1]) is False
    b.apply_batch(batches[0])
    b.apply_batch(batches[1])
    a.pull(relay)
    assert a.state(obj) == b.state(obj) and a.state(obj)["conflict"]


def test_missing_base_rejects_push_without_partial_batch(nodes):
    _, relay, a, _ = nodes
    change = a.create("ResearchRun", {"title": "A"})
    dependency = replace(change, change_id=str(uuid4()), audit_id=str(uuid4()),
                         object_id=str(uuid4()), operation="update", base_revision="a" * 64)
    with pytest.raises(ProtocolError, match="dependency"):
        relay.push([change, dependency], str(uuid4()), a.device_id)
    assert relay.pull(a.project_id, 0) == [] and relay.audit_count() == 0


@pytest.mark.parametrize("payload", [{"text": {"table": "raw_row_dump"}},
                                      {"text": "ok", "run_id": "not-a-uuid"}])
def test_business_field_types_reject_row_dump_and_invalid_reference(nodes, payload):
    _, _, a, _ = nodes
    with pytest.raises(ProtocolError):
        a.create("Note", payload)


def test_caller_payload_mutation_does_not_change_local_revision(nodes):
    _, _, a, _ = nodes
    payload = {"title": "original"}
    change = a.create("ResearchRun", payload)
    revision = change.revision
    payload["title"] = "caller mutation"
    assert change.revision == revision
    assert a.state(change.object_id)["projection"]["title"] == "original"


def test_registered_human_cannot_push_ai_claimed_human_conclusion(nodes):
    _, relay, a, b = nodes
    ordinary = a.create("ResearchRun", {"title": "batch companion"})
    conclusion = a.create("HumanConclusion", {"text": "synthetic human conclusion"})
    mismatched = replace(conclusion, actor_type="ai")
    with pytest.raises(ProtocolError, match="actor claim.*principal"):
        relay.push([ordinary, mismatched], str(uuid4()), a.device_id)
    assert relay.pull(a.project_id, 0) == [] and relay.audit_count() == 0
    assert relay.state(ordinary.object_id) is None
    assert relay.state(conclusion.object_id) is None
    b.pull(relay)
    assert b.cursor == 0 and b.audit_count() == 0
    # Corrected input remains replayable after the failed atomic batch.
    relay.push([ordinary, conclusion], str(uuid4()), a.device_id)
    b.pull(relay)
    assert b.cursor == 1 and b.state(conclusion.object_id)["projection"]["text"] == (
        "synthetic human conclusion")


def test_registered_ai_cannot_claim_human_for_ordinary_note(nodes, tmp_path):
    project, relay, _, _ = nodes
    ai = Replica(tmp_path / "ai-claim.sqlite", project, principal_type="ai")
    relay.register_device(ai.device_id, "ai")
    note = ai.create("Note", {"text": "synthetic observation"})
    with pytest.raises(ProtocolError, match="actor claim.*principal"):
        relay.push([replace(note, actor_type="human")], str(uuid4()), ai.device_id)
    assert relay.pull(project, 0) == [] and relay.audit_count() == 0
