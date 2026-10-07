"""Strict versioned semantic protocol, independent from transport and authority."""
import re
from datetime import datetime

from .canonical import canonical_bytes, digest, validate_decimal, validate_integer


class ProtocolError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


CHANGE_FIELDS = {"change_id", "audit_id", "transaction_id", "project_id", "device_id", "actor_id", "actor_type", "object_type", "object_id", "operation", "parents", "payload", "schema_version", "module_snapshot_hash", "created_at"}
TRANSACTION_FIELDS = {"transaction_id", "idempotency_key", "project_id", "device_id", "actor_id", "actor_type", "protocol_version", "schema_version", "created_at", "ordered_change_ids", "changes", "dependencies"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z\Z")
ACTORS = {"human", "codex", "chatgpt", "system"}
OPERATIONS = {"create", "update", "archive", "trash", "restore", "resolve"}
PAYLOAD_FIELDS = {
    "Project": "name description module_id status current_stage current_objective enabled_capabilities repository module_version module_snapshot module_snapshot_hash",
    "ResearchRun": "title run_type parent_run_id objective hypothesis status scientific_outcome protocol observation ai_analysis human_conclusion next_step environment software_version code_revision repository branch commit_sha issue_url pull_request_url changes_from_parent started_at completed_at context_data artifact_ids tag_ids",
    "Parameter": "name value value_type unit source_kind source_id source_location uncertainty valid_conditions is_confirmed run_id status",
    "Metric": "name value value_type unit metric_schema_id status source_kind source_id source_location derivation uncertainty valid_conditions artifact_ids run_id is_confirmed",
    "Artifact": "run_id file_id filename mime_type category checksum sha256 size metadata sync_policy origin_device availability key_epoch blob_locator artifact_ids",
    "Note": "title content run_id tag_ids",
    "Task": "title description milestone_id status priority due_date tag_ids",
    "Evidence": "title description evidence_type status linked_run_id linked_artifact_id linked_source_id limitations tag_ids",
    "Claim": "title statement status limitations evidence_ids run_ids artifact_ids source_ids",
    "Decision": "title run_id context decision reason alternatives status evidence_ids tag_ids",
    "Gate": "gate_id stage_id name description status criteria evidence_ids blocking_reason",
    "GateCriterion": "id description provenance status evidence_ids gate_id",
    "HumanConclusion": "run_id content conclusion status evidence_ids",
    "ModuleUpgrade": "module_id from_version to_version module_version module_snapshot module_snapshot_hash expected_version expected_target_digest",
}
PAYLOAD_FIELDS = {key: set(value.split()) for key, value in PAYLOAD_FIELDS.items()}
EVIDENCE_STATES = {"proposed", "unknown", "hypothesis", "assumed", "synthetic", "simulated", "measured", "calibrated", "validated", "reproduced", "rejected"}
ENUMS = {
    "source_kind": {"unknown", "synthetic", "assumed", "literature", "manufacturer", "measured", "calibrated", "derived"},
    "scientific_outcome": {"unknown", "positive_result", "negative_result", "inconclusive", "candidate_rejected"},
    "priority": {"low", "medium", "high", "critical"},
    "availability": {"pending", "verified_reference", "unavailable"},
    "sync_policy": {"local_only", "metadata_only", "encrypted_sync", "on_demand"},
    "value_type": {"decimal", "integer", "number", "string", "boolean", "object", "array"},
}
STATUS = {
    "Project": {"active", "paused", "completed", "archived", "blocked"},
    "ResearchRun": {"planned", "running", "completed", "failed", "cancelled", "blocked"},
    "Parameter": EVIDENCE_STATES, "Metric": EVIDENCE_STATES, "Evidence": EVIDENCE_STATES,
    "Task": {"todo", "doing", "blocked", "done"},
    "Claim": {"draft", "supported", "rejected", "inconclusive"},
    "Decision": {"proposed", "accepted", "superseded", "rejected"},
    "Gate": {"not_started", "in_progress", "passed", "failed", "blocked"},
    "GateCriterion": {"not_started", "in_progress", "passed", "failed", "blocked"},
    "HumanConclusion": {"draft", "proposed", "final"},
}
NULLABLE = {"unit", "source_id", "source_location", "uncertainty", "valid_conditions", "repository", "current_stage", "parent_run_id", "branch", "commit_sha", "issue_url", "pull_request_url", "started_at", "completed_at", "milestone_id", "due_date", "run_id", "linked_run_id", "linked_artifact_id", "linked_source_id", "enabled_capabilities", "metric_schema_id", "derivation"}
OBJECT_FIELDS = {"metadata", "context_data", "module_snapshot"}
ARRAY_FIELDS = {"artifact_ids", "tag_ids", "evidence_ids", "run_ids", "source_ids", "enabled_capabilities", "criteria"}


def _reject(message, code="INVALID_WIRE"):
    raise ProtocolError(code, message)


def _fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        _reject("unknown or missing semantic fields")


def _uuid(value):
    if type(value) is not str or not UUID.fullmatch(value) or value == "00000000-0000-0000-0000-000000000000":
        _reject("invalid canonical UUID")


def _hash(value):
    if type(value) is not str or not HASH.fullmatch(value):
        _reject("invalid digest")


def _stamp(value):
    if type(value) is not str or not STAMP.fullmatch(value):
        _reject("invalid UTC millisecond datetime")
    try:
        datetime.fromisoformat(value[:-1])
    except ValueError:
        _reject("invalid calendar datetime")


def _version(value):
    if type(value) is not int or value != 1:
        _reject("unsupported protocol/schema version", "UPGRADE_REQUIRED")


def _enum(value, allowed):
    if type(value) is not str or value not in allowed:
        _reject("unknown enum value")


def _set_list(value, validator):
    if type(value) is not list:
        _reject("set must be an array")
    for entry in value:
        validator(entry)
    if value != sorted(set(value)):
        _reject("set must be sorted and unique")


def _payload(kind, payload):
    if type(payload) is not dict or not set(payload) <= PAYLOAD_FIELDS[kind]:
        _reject("unknown business payload fields")
    for key, value in payload.items():
        if key == "value":
            continue
        if value is None and key in NULLABLE:
            continue
        if key in ENUMS:
            _enum(value, ENUMS[key])
        elif key == "status":
            _enum(value, STATUS.get(kind, set()))
        elif key in OBJECT_FIELDS:
            if type(value) is not dict:
                _reject("payload object type mismatch")
        elif key in ARRAY_FIELDS:
            if type(value) is not list:
                _reject("payload array type mismatch")
            if key.endswith("_ids"):
                for item in value:
                    _uuid(item)
            elif key == "enabled_capabilities" and any(type(item) is not str for item in value):
                _reject("capability must be string")
            elif key == "criteria":
                for item in value:
                    _payload("GateCriterion", item)
        elif key == "is_confirmed":
            if type(value) is not bool:
                _reject("confirmation must be boolean")
        elif key in {"size", "key_epoch"}:
            if type(value) is not int or value < 0:
                _reject("count must be a nonnegative integer")
        elif key in {"checksum", "sha256", "module_snapshot_hash", "expected_target_digest"}:
            _hash(value)
        elif key in {"started_at", "completed_at", "due_date"}:
            _stamp(value)
        elif key == "origin_device" or (key.endswith("_id") and key not in {"module_id", "metric_schema_id", "gate_id", "stage_id"}):
            _uuid(value)
        elif type(value) is not str:
            _reject("payload string type mismatch")
    if "value" in payload and payload["value"] is not None:
        value = payload["value"]
        kind = payload.get("value_type")
        try:
            if kind == "decimal":
                validate_decimal(value)
            elif kind == "integer":
                validate_integer(value)
            elif kind == "number":
                _reject("scientific number requires tagged decimal/integer")
            elif kind in {"string", "boolean", "object", "array"}:
                expected = {"string":str,"boolean":bool,"object":dict,"array":list}[kind]
                if type(value) is not expected:
                    _reject("value_type mismatch")
            elif type(value) not in {str, bool}:
                _reject("numeric values require explicit tagged value_type")
        except ValueError as exc:
            _reject(str(exc))
    canonical_bytes(payload)


def validate_change(change):
    _fields(change, CHANGE_FIELDS)
    for key in ("change_id", "audit_id", "transaction_id", "project_id", "device_id", "actor_id", "object_id"):
        _uuid(change[key])
    _version(change["schema_version"])
    _enum(change["actor_type"], ACTORS)
    _enum(change["operation"], OPERATIONS)
    _enum(change["object_type"], PAYLOAD_FIELDS)
    _hash(change["module_snapshot_hash"])
    _stamp(change["created_at"])
    _set_list(change["parents"], _hash)
    count = len(change["parents"])
    operation = change["operation"]
    if (operation == "create" and count != 0) or (operation == "resolve" and count < 1) or (operation not in {"create", "resolve"} and count != 1):
        _reject("invalid parent count for operation")
    _payload(change["object_type"], change["payload"])
    return change


def revision(change):
    return digest(validate_change(change))


def validate_transaction(tx, context=None):
    _fields(tx, TRANSACTION_FIELDS)
    for key in ("transaction_id", "idempotency_key", "project_id", "device_id", "actor_id"):
        _uuid(tx[key])
    if tx["transaction_id"] != tx["idempotency_key"]:
        _reject("idempotency key must equal transaction id")
    _version(tx["protocol_version"])
    _version(tx["schema_version"])
    _enum(tx["actor_type"], ACTORS)
    _stamp(tx["created_at"])
    _set_list(tx["dependencies"], _uuid)
    if tx["transaction_id"] in tx["dependencies"]:
        _reject("self dependency")
    if type(tx["changes"]) is not list or not tx["changes"] or type(tx["ordered_change_ids"]) is not list:
        _reject("transaction requires ordered nonempty changes")
    objects, changes, audits = set(), set(), set()
    for change in tx["changes"]:
        validate_change(change)
        for key in ("transaction_id", "project_id", "device_id", "actor_id", "actor_type", "schema_version"):
            if tx[key] != change[key]:
                _reject("transaction member identity mismatch")
        obj = (change["object_type"], change["object_id"])
        if obj in objects or change["change_id"] in changes or change["audit_id"] in audits:
            _reject("duplicate object/change/audit member")
        objects.add(obj)
        changes.add(change["change_id"])
        audits.add(change["audit_id"])
    if tx["ordered_change_ids"] != [c["change_id"] for c in tx["changes"]]:
        _reject("ordered change ids do not match members")
    if context is not None:
        for key in ("project_id", "device_id", "actor_id", "actor_type"):
            if key in context and tx[key] != context[key]:
                _reject("wire identity differs from trusted context", "ACTOR_CONTEXT_MISMATCH")
    canonical_bytes(tx)
    return tx


def transaction_digest(tx):
    return digest(validate_transaction(tx))
