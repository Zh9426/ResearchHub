"""Fixed transcript author. Explicit ASCII field orders, NEVER imports codecs."""

import copy
import hashlib
import json
from pathlib import Path

FIELDS = ["actor_id", "actor_type", "audit_id", "change_id", "created_at", "device_id",
          "module_snapshot_hash", "object_id", "object_type", "operation", "parents",
          "payload", "project_id", "schema_version", "transaction_id"]
TX_FIELDS = ["actor_id", "actor_type", "changes", "created_at", "dependencies", "device_id",
             "idempotency_key", "ordered_change_ids", "project_id", "protocol_version",
             "schema_version", "transaction_id"]
PAYLOAD_FIELDS = ["content", "is_confirmed", "name", "observation", "run_type", "status",
                  "title", "unit", "value", "value_type"]


def uid(number):
    return f"00000000-0000-4000-8000-{number:012x}"


def literal(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def change_anchor(change):
    payload = "{" + ",".join(literal(k) + ":" + literal(change["payload"][k])
                             for k in PAYLOAD_FIELDS if k in change["payload"]) + "}"
    assert set(change["payload"]) <= set(PAYLOAD_FIELDS)
    return "{" + ",".join(literal(k) + ":" + (payload if k == "payload" else literal(change[k]))
                          for k in FIELDS) + "}"


def tx_anchor(tx):
    changes = "[" + ",".join(change_anchor(c) for c in tx["changes"]) + "]"
    return "{" + ",".join(literal(k) + ":" + (changes if k == "changes" else literal(tx[k]))
                          for k in TX_FIELDS) + "}"


def checksum(anchor):
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()


def transaction(number, *, oid=None, kind="Parameter", payload=None, operation="create", parents=(), actor="human"):
    person = 2 if actor == "human_b" else 3 if actor == "codex" else 1
    actor_type = "codex" if actor == "codex" else "human"
    txid = uid(number)
    change = {"change_id": uid(number + 10000), "audit_id": uid(number + 20000),
              "transaction_id": txid, "project_id": uid(9000), "device_id": uid(100 + person),
              "actor_id": uid(200 + person), "actor_type": actor_type, "object_type": kind,
              "object_id": oid or uid(number + 30000), "operation": operation, "parents": sorted(parents),
              "payload": payload if payload is not None else {"name": "SYNTHETIC pressure", "value": "1.400", "value_type": "decimal"},
              "schema_version": 1, "module_snapshot_hash": "a" * 64, "created_at": "2026-10-07T01:02:03.004Z"}
    return {"transaction_id": txid, "idempotency_key": txid, "project_id": uid(9000),
            "device_id": change["device_id"], "actor_id": change["actor_id"], "actor_type": actor_type,
            "protocol_version": 1, "schema_version": 1, "created_at": change["created_at"],
            "ordered_change_ids": [change["change_id"]], "changes": [change], "dependencies": []}


def step(tx, expected, *, actor="human", mode="online", wire_error=None, context=None):
    anchor = tx_anchor(tx)
    result = {"raw": literal(tx), "canonical_hex": anchor.encode().hex(), "digest": checksum(anchor),
              "revisions": [checksum(change_anchor(c)) for c in tx["changes"]],
              "wire_valid": wire_error is None, "actor": actor, "mode": mode, "expected_kernel": expected}
    if wire_error:
        result["wire_error"] = wire_error
    if context:
        result["context"] = context
    return result


def build():
    cases = []
    base = transaction(10)
    oid = base["changes"][0]["object_id"]
    base_revision = checksum(change_anchor(base["changes"][0]))
    a, b = [transaction(n, oid=oid, operation="update", parents=[base_revision],
                         payload={"value_type": "decimal", "value": value}) for n, value in [(11, "1.600"), (12, "1.800")]]
    cases.append({"name": "scientific_conflict", "steps": [step(base, "ACCEPTED"), step(a, "ACCEPTED"), step(b, "CANDIDATE")]})
    corrupted = copy.deepcopy(base)
    corrupted["changes"][0]["payload"]["value"] = "1.800"
    cases.append({"name": "identity_collision", "steps": [step(base, "ACCEPTED"), step(corrupted, "IDENTITY_COLLISION")]})
    unknown = transaction(20)
    unknown["schema_version"] = unknown["changes"][0]["schema_version"] = 2
    cases.append({"name": "schema_mismatch", "steps": [step(unknown, "QUARANTINED", wire_error="UPGRADE_REQUIRED")]})
    module = transaction(21)
    module["changes"][0]["module_snapshot_hash"] = "b" * 64
    cases.append({"name": "module_mismatch", "steps": [step(module, "QUARANTINED")]})
    ai = transaction(22, actor="codex", payload={"name": "SYNTHETIC", "is_confirmed": True})
    cases.append({"name": "ai_authority_violation", "steps": [step(ai, "HUMAN_REQUIRED", actor="codex")]})
    spoof = transaction(23)
    context = {"actor_type": "codex"}
    cases.append({"name": "ai_identity_spoof", "steps": [step(spoof, "ACTOR_CONTEXT_MISMATCH", actor="codex",
                    wire_error="ACTOR_CONTEXT_MISMATCH", context=context)]})
    run = transaction(30, kind="ResearchRun", payload={"title": "SYNTHETIC", "run_type": "simulation"})
    roid, parent = run["changes"][0]["object_id"], checksum(change_anchor(run["changes"][0]))
    trash = transaction(31, oid=roid, kind="ResearchRun", operation="trash", parents=[parent], payload={})
    edit = transaction(32, oid=roid, kind="ResearchRun", operation="update", parents=[parent], payload={"observation": "离线观察😀"})
    cases.append({"name": "trash_offline_edit", "steps": [step(run, "ACCEPTED"), step(trash, "ACCEPTED"), step(edit, "CANDIDATE")]})
    expected_heads = sorted(checksum(change_anchor(tx["changes"][0])) for tx in [a, b])
    ra, rb = [transaction(n, oid=oid, operation="resolve", parents=expected_heads, actor=actor,
                          payload={"value_type": "decimal", "value": value})
              for n, actor, value in [(40, "human", "1.700"), (41, "human_b", "1.900")]]
    cases.append({"name": "offline_resolution_race", "steps": [step(base, "ACCEPTED"), step(a, "ACCEPTED"), step(b, "CANDIDATE"),
                    step(ra, "CANDIDATE", mode="offline_proposal"), step(rb, "CANDIDATE", actor="human_b", mode="offline_proposal")]})
    unicode = transaction(50, payload={"name": "压力😀é", "value_type": "decimal", "value": "1.600", "unit": "MPa"})
    cases.append({"name": "unicode_decimal_precision", "steps": [step(unicode, "ACCEPTED")]})
    collision = transaction(51, kind="Note", payload={"title": "SYNTHETIC"})
    collision["changes"][0]["audit_id"] = base["changes"][0]["audit_id"]
    cases.append({"name": "audit_collision", "steps": [step(base, "ACCEPTED"), step(collision, "IDENTITY_COLLISION")]})
    return cases


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[2] / "fixtures/sync/v1/kernel_cases.json"
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
