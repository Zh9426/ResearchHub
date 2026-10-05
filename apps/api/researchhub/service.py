"""Shared application service; web and scoped MCP clients use the same rules."""

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.inspection import inspect

from . import models as m
from .schemas import SCHEMAS

INSUFFICIENT_EVIDENCE_STATUSES = {"unknown", "hypothesis", "assumed", "rejected"}


def serialize(db, obj):
    data = {
        attr.key: getattr(obj, attr.key) for attr in inspect(type(obj)).column_attrs
    }
    if isinstance(obj, m.Artifact):
        data["metadata"] = data.pop("artifact_metadata")
    for (table, key), link in m.LINKS.items():
        if table == obj.__tablename__:
            data[key] = list(
                db.scalars(select(link.c.target_id).where(link.c.owner_id == obj.id))
            )
    if isinstance(obj, m.Gate):
        data["criteria"] = [
            {**serialize(db, c), "id": c.criterion_id}
            for c in db.scalars(
                select(m.GateCriterion).where(m.GateCriterion.gate_id == obj.id)
            )
        ]
        for c in data["criteria"]:
            for key in ("criterion_id", "gate_id", "created_at", "updated_at"):
                c.pop(key, None)
    return jsonable_encoder(data)


def project_for(db, actor, pid):
    p = db.get(m.Project, str(pid))
    if not p or p.owner_id != actor.user.id:
        raise HTTPException(404, "Project not found")
    return p


def resource(db, actor, cls, rid):
    obj = db.get(cls, str(rid))
    if not obj:
        raise HTTPException(404, "Resource not found")
    if isinstance(obj, m.Project):
        project_for(db, actor, obj.id)
    elif isinstance(obj, (m.Parameter, m.Metric)):
        resource(db, actor, m.ResearchRun, obj.run_id)
    else:
        project_for(db, actor, obj.project_id)
    return obj


def reference(db, cls, rid, pid):
    if not rid:
        return None
    obj = db.get(cls, str(rid))
    if not obj or obj.project_id != pid:
        raise HTTPException(422, "Reference must belong to the same project")
    return obj


def validate_links(db, obj, data, modules):
    pid = (
        obj.project_id
        if hasattr(obj, "project_id")
        else db.get(m.ResearchRun, obj.run_id).project_id
    )
    for field, cls in {
        "parent_run_id": m.ResearchRun,
        "run_id": m.ResearchRun,
        "linked_run_id": m.ResearchRun,
        "linked_artifact_id": m.Artifact,
        "linked_source_id": m.Source,
        "research_question_id": m.ResearchQuestion,
        "milestone_id": m.Milestone,
        "source_id": m.Source,
    }.items():
        if field in data:
            reference(db, cls, data[field], pid)
    for key, cls in {
        "evidence_ids": m.Evidence,
        "run_ids": m.ResearchRun,
        "artifact_ids": m.Artifact,
        "source_ids": m.Source,
    }.items():
        for rid in data.get(key, []):
            reference(db, cls, rid, pid)
    if isinstance(obj, m.ResearchRun):
        parent = data.get("parent_run_id")
        visited = {obj.id}
        while parent:
            if parent in visited:
                raise HTTPException(422, "Parent run cycle is not allowed")
            visited.add(parent)
            parent = reference(db, m.ResearchRun, parent, pid).parent_run_id
        module = modules[db.get(m.Project, pid).module_id]
        if data["run_type"] not in {r["id"] for r in module["run_types"]}:
            raise HTTPException(422, "Run type is not defined by this module")
    if isinstance(obj, m.Metric) and data.get("metric_schema_id"):
        module = modules[db.get(m.Project, pid).module_id]
        if data["metric_schema_id"] not in {r["id"] for r in module["metric_schemas"]}:
            raise HTTPException(422, "Unknown module metric schema")
    if isinstance(obj, m.Gate):
        module = modules[db.get(m.Project, pid).module_id]
        if data["stage_id"] not in {s["id"] for s in module["research_stages"]}:
            raise HTTPException(422, "Unknown stage")
        criteria = data.get("criteria", [])
        if len({c["id"] for c in criteria}) != len(criteria):
            raise HTTPException(422, "Duplicate gate criterion")
        original = (
            list(
                db.scalars(
                    select(m.GateCriterion).where(m.GateCriterion.gate_id == obj.id)
                )
            )
            if obj.id
            else []
        )
        if original and {c.criterion_id for c in original} != {
            c["id"] for c in criteria
        }:
            raise HTTPException(
                422, "Existing gate criteria cannot be removed or replaced"
            )
        for c in criteria:
            for eid in c["evidence_ids"]:
                reference(db, m.Evidence, eid, pid)
            if c["status"] == "passed" and not c["evidence_ids"]:
                raise HTTPException(422, "Passed criteria require linked evidence")
            if c["status"] == "passed" and any(
                reference(db, m.Evidence, eid, pid).status
                in INSUFFICIENT_EVIDENCE_STATUSES
                for eid in c["evidence_ids"]
            ):
                raise HTTPException(422, "Criterion evidence status is insufficient")
        if data["status"] == "passed":
            if (
                not criteria
                or any(c["status"] != "passed" for c in criteria)
                or not data.get("evidence_ids")
            ):
                raise HTTPException(
                    422, "Passed gates require all criteria passed and linked evidence"
                )
            evidence = [
                reference(db, m.Evidence, eid, pid) for eid in data["evidence_ids"]
            ]
            if any(
                e.status in INSUFFICIENT_EVIDENCE_STATUSES
                for e in evidence
            ):
                raise HTTPException(
                    422, "Evidence status is insufficient for gate passage"
                )
        if data["status"] == "blocked" and not data["blocking_reason"].strip():
            raise HTTPException(422, "Blocked gate requires a reason")


def parsed(kind, payload):
    try:
        return SCHEMAS[kind].model_validate(payload).model_dump(mode="json")
    except ValidationError as e:
        raise HTTPException(
            422, jsonable_encoder(e.errors(), custom_encoder={ValueError: str})
        )


def apply_data(db, obj, data):
    for key, value in data.items():
        if (obj.__tablename__, key) in m.LINKS:
            table = m.LINKS[(obj.__tablename__, key)]
            db.execute(delete(table).where(table.c.owner_id == obj.id))
            for rid in set(value):
                db.execute(table.insert().values(owner_id=obj.id, target_id=rid))
        elif key == "criteria" and isinstance(obj, m.Gate):
            current = {
                c.criterion_id: c
                for c in db.scalars(
                    select(m.GateCriterion).where(m.GateCriterion.gate_id == obj.id)
                )
            }
            for item in value:
                c = current.get(item["id"])
                if c is None:
                    c = m.GateCriterion(
                        gate_id=obj.id,
                        criterion_id=item["id"],
                        description=item["description"],
                    )
                    db.add(c)
                    db.flush()
                apply_data(db, c, {k: v for k, v in item.items() if k != "id"})
        else:
            if key.endswith(("_at", "_date")) and isinstance(value, str):
                from datetime import datetime

                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            setattr(obj, key, value)
    db.flush()


def audit(db, actor, request, action, obj, before=None):
    pid = getattr(obj, "project_id", None)
    if isinstance(obj, m.Project):
        pid = obj.id
    if isinstance(obj, (m.Parameter, m.Metric)):
        pid = db.get(m.ResearchRun, obj.run_id).project_id
    if isinstance(obj, m.GateCriterion):
        pid = db.get(m.Gate, obj.gate_id).project_id
    db.add(
        m.AuditLog(
            owner_id=actor.user.id,
            project_id=pid,
            actor=actor.user.email,
            actor_type=actor.actor_type,
            action=action,
            resource_type=obj.__tablename__,
            resource_id=obj.id,
            before=before,
            after=serialize(db, obj),
            source="mcp" if actor.token else "web",
            request_id=request.state.request_id,
        )
    )


def evidence_dependents(db, evidence):
    """Snapshot linked gates before an evidence mutation removes its support."""
    gate_links = m.LINKS[("stage_gates", "evidence_ids")]
    criterion_links = m.LINKS[("gate_criteria", "evidence_ids")]
    direct = select(gate_links.c.owner_id).where(
        gate_links.c.target_id == evidence.id
    )
    via_criteria = (
        select(m.GateCriterion.gate_id)
        .join(criterion_links, criterion_links.c.owner_id == m.GateCriterion.id)
        .where(criterion_links.c.target_id == evidence.id)
    )
    gates = db.scalars(
        select(m.Gate).where(
            m.Gate.project_id == evidence.project_id,
            or_(m.Gate.id.in_(direct), m.Gate.id.in_(via_criteria)),
        )
    )
    return [
        (
            gate,
            serialize(db, gate),
            [
                (criterion, serialize(db, criterion))
                for criterion in db.scalars(
                    select(m.GateCriterion).where(m.GateCriterion.gate_id == gate.id)
                )
            ],
        )
        for gate in gates
    ]


def evidence_support_sufficient(db, evidence_ids):
    """Match the gate passage rule: nonempty support, with every status sufficient."""
    statuses = list(
        db.scalars(select(m.Evidence.status).where(m.Evidence.id.in_(evidence_ids)))
    )
    return bool(evidence_ids) and len(statuses) == len(set(evidence_ids)) and not any(
        status in INSUFFICIENT_EVIDENCE_STATUSES for status in statuses
    )


def reconcile_evidence_dependents(db, actor, request, dependents, evidence_id, reason):
    """Reopen unsupported passage in the same transaction as the evidence write."""
    for gate, before_gate, criteria in dependents:
        for criterion, before_criterion in criteria:
            if criterion.status == "passed" and not evidence_support_sufficient(
                db, serialize(db, criterion)["evidence_ids"]
            ):
                criterion.status = "in_progress"
                db.flush()
                audit(
                    db, actor, request, "reopen_gate_criterion", criterion,
                    before_criterion,
                )
        if gate.status == "passed" and (
            not criteria
            or any(criterion.status != "passed" for criterion, _ in criteria)
            or not evidence_support_sufficient(db, serialize(db, gate)["evidence_ids"])
        ):
            gate.status = "blocked"
            gate.blocking_reason = f"证据 {evidence_id} {reason}；请重新核验关联证据与 Gate 判据。"
            db.flush()
            audit(db, actor, request, "invalidate_gate_evidence", gate, before_gate)


def create_record(db, actor, request, kind, pid, payload, modules, run_id=None):
    cls = m.COLLECTIONS.get(
        kind, {"parameters": m.Parameter, "metrics": m.Metric}.get(kind)
    )
    data = parsed(kind, payload)
    obj = cls(id=m.uid(), **({"run_id": run_id} if run_id else {"project_id": pid}))
    if isinstance(obj, m.ResearchRun):
        obj.created_by = actor.user.id
    validate_links(db, obj, data, modules)
    # Set scalar required fields before INSERT; relation rows follow once id exists.
    relation_keys = {k for (t, k) in m.LINKS if t == obj.__tablename__} | {"criteria"}
    for key, value in data.items():
        if key not in relation_keys:
            if isinstance(value, str) and key.endswith(("_at", "_date")):
                from datetime import datetime

                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            setattr(obj, key, value)
    db.add(obj)
    db.flush()
    apply_data(db, obj, {k: v for k, v in data.items() if k in relation_keys})
    audit(db, actor, request, "create_" + kind, obj)
    return obj


def project_context(db, actor, pid, modules):
    p = project_for(db, actor, pid)
    return {
        "project": serialize(db, p),
        "module": modules[p.module_id],
        **{
            key: [
                serialize(db, o)
                for o in db.scalars(
                    select(cls).where(cls.project_id == pid).order_by(cls.created_at)
                )
            ]
            for key, cls in m.COLLECTIONS.items()
        },
        "artifacts": [
            serialize(db, o)
            for o in db.scalars(select(m.Artifact).where(m.Artifact.project_id == pid))
        ],
        "activity": [
            serialize(db, o)
            for o in db.scalars(
                select(m.AuditLog)
                .where(
                    m.AuditLog.project_id == pid, m.AuditLog.owner_id == actor.user.id
                )
                .order_by(m.AuditLog.timestamp.desc())
                .limit(100)
            )
        ],
    }


def run_context(db, actor, rid):
    r = resource(db, actor, m.ResearchRun, rid)
    parent = db.get(m.ResearchRun, r.parent_run_id) if r.parent_run_id else None
    parameters = [
        serialize(db, p)
        for p in db.scalars(select(m.Parameter).where(m.Parameter.run_id == rid))
    ]
    differences = []
    if parent:
        old = {
            p.name: serialize(db, p)
            for p in db.scalars(
                select(m.Parameter).where(m.Parameter.run_id == parent.id)
            )
        }
        current = {p["name"]: p for p in parameters}
        tracked = (
            "value",
            "value_type",
            "unit",
            "source_kind",
            "source_id",
            "source_location",
            "uncertainty",
            "valid_conditions",
            "is_confirmed",
        )
        for name in sorted(old.keys() | current.keys()):
            previous = old.get(name)
            present = current.get(name)
            fields = {
                key: {
                    "parent": previous[key] if previous else None,
                    "current": present[key] if present else None,
                }
                for key in tracked
                if previous is None or present is None or previous[key] != present[key]
            }
            if fields:
                differences.append(
                    {
                        "name": name,
                        "parent": previous["value"] if previous else None,
                        "current": present["value"] if present else None,
                        "change_type": "added"
                        if previous is None
                        else "removed"
                        if present is None
                        else "changed",
                        "fields": fields,
                        "parent_parameter": previous,
                        "current_parameter": present,
                    }
                )
    return {
        "run": serialize(db, r),
        "parent": serialize(db, parent) if parent else None,
        "children": [
            serialize(db, o)
            for o in db.scalars(
                select(m.ResearchRun).where(m.ResearchRun.parent_run_id == rid)
            )
        ],
        "parameters": parameters,
        "metrics": [
            serialize(db, o)
            for o in db.scalars(select(m.Metric).where(m.Metric.run_id == rid))
        ],
        "artifacts": [
            serialize(db, o)
            for o in db.scalars(select(m.Artifact).where(m.Artifact.run_id == rid))
        ],
        "evidence": [
            serialize(db, o)
            for o in db.scalars(
                select(m.Evidence).where(m.Evidence.linked_run_id == rid)
            )
        ],
        "changes_from_parent": {
            "description": r.changes_from_parent,
            "parameters": differences,
        },
    }
