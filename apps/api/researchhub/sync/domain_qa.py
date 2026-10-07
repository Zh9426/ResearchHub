"""Explicit QA-only Domain adapter; never imported by the production app."""

import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from .. import models as domain
from .. import service
from ..modules import load_modules
from .authority import resolve_principal
from .canonical import canonical_bytes, digest, validate_decimal, validate_integer
from .kernel import apply_in_session, lock_project
from .models import Outbox
from .protocol import ProtocolError
from .qa import assert_qa_bind


def parameter_payload(payload):
    """Map wire data to the v0.2 Parameter carrier without losing precision."""
    canonical_bytes(payload)
    mapped = copy.deepcopy(payload)
    mapped.pop("run_id", None)
    if "status" in mapped:
        raise ProtocolError("DOMAIN_MAPPING_REQUIRED", "v0.2 Parameter has no status carrier")
    kind = mapped.get("value_type")
    if kind in {"decimal", "integer"}:
        value = mapped.get("value")
        if value is not None:
            (validate_decimal if kind == "decimal" else validate_integer)(value)
            mapped["value"] = {"value_type": kind, "value": value}
        mapped["value_type"] = "object"
    return mapped


def create_run_batch(db, context, project_id, *, run, parameters, metrics, artifacts=(),
                     transaction_id=None, fault=None):
    """Draft QA Domain action + Audit + Outbox in caller's DB transaction.

    Pending metadata placeholders never claim that bytes exist. The accepted
    scientific view is the kernel projection, not unrestricted v0.2 row queries.
    """
    assert_qa_bind(db.get_bind())
    command = copy.deepcopy({"run": run, "parameters": list(parameters),
                             "metrics": list(metrics), "artifacts": list(artifacts)})
    action_digest = digest(command)
    run, parameters, metrics, artifacts = (command[name] for name in ("run", "parameters", "metrics", "artifacts"))
    project_state = lock_project(db, project_id)
    principal = resolve_principal(db, context, project_id)
    transaction_id = transaction_id or str(uuid4())
    previous = db.get(Outbox, transaction_id)
    if previous:
        if previous.project_id != project_id or previous.action_digest != action_digest:
            raise ProtocolError("IDENTITY_COLLISION", "transaction id has different Domain command")
        return apply_in_session(db, previous.envelope, context, local_outbox=True)
    user = db.get(domain.User, principal.user_id)
    if user is None:
        raise ProtocolError("DOMAIN_USER_REQUIRED", "QA registered Domain user is missing")
    actor = SimpleNamespace(user=user, actor_type=principal.actor_type,
                            token=None if principal.actor_type == "human" else True)
    request = SimpleNamespace(state=SimpleNamespace(request_id="SYNTHETIC-sync-" + transaction_id))
    project = service.project_for(db, actor, project_id, write=True)
    if digest(project.module_snapshot) != project_state.module_snapshot_hash:
        raise ProtocolError("MODULE_FROZEN", "Domain snapshot and kernel binding differ")
    registry = load_modules()
    run_record = service.create_record(db, actor, request, "runs", project_id, run, registry)
    semantic_items = [("ResearchRun", run_record.id, copy.deepcopy(run))]
    for payload in parameters:
        record = service.create_record(db, actor, request, "parameters", project_id,
                                       parameter_payload(payload), registry, run_id=run_record.id)
        semantic_items.append(("Parameter", record.id, {**copy.deepcopy(payload), "run_id": run_record.id}))
    for payload in metrics:
        canonical_bytes(payload)
        mapped = copy.deepcopy(payload)
        kind = mapped.pop("value_type", None)
        if mapped.get("value") is not None and kind in {"decimal", "integer"}:
            (validate_decimal if kind == "decimal" else validate_integer)(mapped["value"])
        record = service.create_record(db, actor, request, "metrics", project_id,
                                       mapped, registry, run_id=run_record.id)
        semantic_items.append(("Metric", record.id, {**copy.deepcopy(payload), "run_id": run_record.id}))
    for payload in artifacts:
        canonical_bytes(payload)
        if payload.get("availability", "pending") != "pending":
            raise ProtocolError("ARTIFACT_PENDING_REQUIRED", "Domain QA adapter creates pending metadata only")
        object_id = str(uuid4())
        record = domain.Artifact(
            id=object_id, project_id=project_id, run_id=run_record.id, created_by=user.id,
            filename=payload["filename"], mime_type=payload.get("mime_type", "application/octet-stream"),
            size=payload["size"], checksum=payload["checksum"], category=payload.get("category", "data"),
            object_key="qa-sync-placeholder/" + object_id,
            artifact_metadata={**payload.get("metadata", {}), "qa_availability": "pending",
                               "sync_policy": payload.get("sync_policy", "metadata_only")},
        )
        db.add(record)
        db.flush()
        service.audit(db, actor, request, "create_pending_artifact_metadata", record)
        semantic_items.append(("Artifact", object_id, {**copy.deepcopy(payload), "run_id": run_record.id,
                                                       "availability": "pending"}))
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    changes = [{
        "change_id": str(uuid4()), "audit_id": str(uuid4()), "transaction_id": transaction_id,
        "project_id": project_id, "device_id": principal.device_id, "actor_id": principal.actor_id,
        "actor_type": principal.actor_type, "object_type": kind, "object_id": oid,
        "operation": "create", "parents": [], "payload": payload, "schema_version": 1,
        "module_snapshot_hash": project_state.module_snapshot_hash, "created_at": stamp,
    } for kind, oid, payload in semantic_items]
    tx = {"transaction_id": transaction_id, "idempotency_key": transaction_id,
          "project_id": project_id, "device_id": principal.device_id, "actor_id": principal.actor_id,
          "actor_type": principal.actor_type, "protocol_version": 1, "schema_version": 1,
          "created_at": stamp, "ordered_change_ids": [c["change_id"] for c in changes],
          "changes": changes, "dependencies": []}
    return apply_in_session(db, tx, context, local_outbox=True, fault=fault,
                            domain_action_digest=action_digest)
