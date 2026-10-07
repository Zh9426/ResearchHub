"""Shared application service; web and scoped MCP clients use the same rules."""

import copy
import hashlib
import json
from datetime import timedelta, timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.attributes import flag_modified

from . import models as m
from .schemas import SCHEMAS

INSUFFICIENT_EVIDENCE_STATUSES = {
    "unknown",
    "proposed",
    "hypothesis",
    "assumed",
    "rejected",
}
LIFECYCLE_COLLECTIONS = {
    "projects": m.Project,
    **m.COLLECTIONS,
    "parameters": m.Parameter,
    "metrics": m.Metric,
    "artifacts": m.Artifact,
}
TRASH_RETENTION_DAYS = 30


def require_human(actor):
    if actor.token or actor.actor_type != "human":
        raise HTTPException(
            403,
            "Human session required for scientific confirmation or lifecycle administration",
        )


def scientific_authority(actor, kind, data, existing=None, creating=False):
    """Enforce semantics in the shared service, independently of HTTP token scopes."""
    if not actor.token:
        return
    denied = (
        kind == "runs"
        and "human_conclusion" in data
        and (not creating or bool(data["human_conclusion"]))
        or kind == "parameters"
        and (
            data.get("is_confirmed") is True or bool(existing and existing.is_confirmed)
        )
        or kind == "evidence"
        and (
            data.get("status", "proposed") != "proposed"
            or bool(existing and existing.status != "proposed")
        )
        or kind == "metrics"
        and (
            data.get("status") in {"validated", "reproduced"}
            or bool(existing and existing.status in {"validated", "reproduced"})
        )
        or kind == "gates"
        and (
            data.get("status") == "passed"
            or any(c.get("status") == "passed" for c in data.get("criteria", []))
            or bool(existing and existing.status == "passed")
        )
        or kind == "decisions"
        and (
            data.get("status", "proposed") != "proposed"
            or bool(existing and existing.status != "proposed")
        )
        or kind == "claims"
        and data.get("status") == "supported"
        or kind == "hypotheses"
        and (
            data.get("status") == "supported"
            or data.get("evidence_status") in {"validated", "reproduced"}
        )
    )
    if denied:
        require_human(actor)


def module_for(project):
    """Never reinterpret a project from mutable installation manifests."""
    return project.module_snapshot


def assert_writable(obj):
    if (
        obj.archived_at
        or obj.trashed_at
        or isinstance(obj, m.Project)
        and obj.status == "archived"
    ):
        raise HTTPException(
            409, "Archived or trashed resources cannot be modified; restore first"
        )


def visible_records(cls):
    """Default collections omit trash/archive, including records inside hidden runs."""
    clauses = [cls.trashed_at.is_(None), cls.archived_at.is_(None)]
    if hasattr(cls, "run_id"):
        visible_runs = select(m.ResearchRun.id).where(
            m.ResearchRun.trashed_at.is_(None), m.ResearchRun.archived_at.is_(None)
        )
        clauses.append(or_(cls.run_id.is_(None), cls.run_id.in_(visible_runs)))
    return clauses


def serialize(db, obj):
    data = {
        attr.key: getattr(obj, attr.key) for attr in inspect(type(obj)).column_attrs
    }
    if isinstance(obj, m.Artifact):
        data["metadata"] = data.pop("artifact_metadata")
    for (table, key), link in m.LINKS.items():
        if table == obj.__tablename__:
            query = select(link.c.target_id).where(link.c.owner_id == obj.id)
            if key == "tag_ids":
                query = query.join(m.Tag, m.Tag.id == link.c.target_id).where(
                    *visible_records(m.Tag)
                )
            data[key] = list(db.scalars(query))
    if isinstance(obj, m.Gate):
        data["criteria"] = [
            {**serialize(db, c), "id": c.criterion_id}
            for c in db.scalars(
                select(m.GateCriterion).where(m.GateCriterion.gate_id == obj.id)
            )
        ]
        for c in data["criteria"]:
            for key in (
                "criterion_id",
                "gate_id",
                "created_at",
                "updated_at",
                "archived_at",
                "trashed_at",
            ):
                c.pop(key, None)
    return jsonable_encoder(data)


def project_for(db, actor, pid, include_trashed=False, write=False, lock=False):
    if write or lock:
        # Every project mutation takes this lock first, including module upgrades.
        # populate_existing discards stale identity-map state after waiting for a lock.
        p = db.scalar(
            select(m.Project)
            .where(m.Project.id == str(pid), m.Project.owner_id == actor.user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        p = db.get(m.Project, str(pid))
    if not p or p.owner_id != actor.user.id or p.trashed_at and not include_trashed:
        raise HTTPException(404, "Project not found")
    if write:
        assert_writable(p)
    return p


def resource(db, actor, cls, rid, include_trashed=False, write=False, lock=False):
    obj = db.get(cls, str(rid))
    locked = write or lock
    if not obj:
        raise HTTPException(404, "Resource not found")
    if isinstance(obj, m.Project):
        return project_for(db, actor, obj.id, include_trashed, write, lock)
    elif isinstance(obj, (m.Parameter, m.Metric)):
        resource(db, actor, m.ResearchRun, obj.run_id, include_trashed, write, lock)
    elif isinstance(obj, m.GateCriterion):
        resource(db, actor, m.Gate, obj.gate_id, include_trashed, write, lock)
    else:
        project_for(db, actor, obj.project_id, include_trashed, write, lock)
        if locked:
            # Refresh mutable parent run bindings under the project lock before
            # locking Run -> Resource, never Resource -> Run.
            obj = db.scalar(
                select(cls)
                .where(cls.id == str(rid))
                .execution_options(populate_existing=True)
            )
            if obj is None:
                raise HTTPException(404, "Resource not found")
        if getattr(obj, "run_id", None):
            resource(db, actor, m.ResearchRun, obj.run_id, include_trashed, write, lock)
    if locked:
        obj = db.scalar(
            select(cls)
            .where(cls.id == str(rid))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if not obj or getattr(obj, "trashed_at", None) and not include_trashed:
        raise HTTPException(404, "Resource not found")
    if write:
        assert_writable(obj)
    return obj


def reference(db, cls, rid, pid):
    if not rid:
        return None
    obj = db.get(cls, str(rid))
    if not obj or obj.project_id != pid or obj.trashed_at:
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
            if field == "run_id" and data[field]:
                assert_writable(db.get(m.ResearchRun, data[field]))
    for key, cls in {
        "evidence_ids": m.Evidence,
        "run_ids": m.ResearchRun,
        "artifact_ids": m.Artifact,
        "source_ids": m.Source,
        "tag_ids": m.Tag,
    }.items():
        for rid in data.get(key, []):
            linked = reference(db, cls, rid, pid)
            if key == "tag_ids" and linked.archived_at:
                raise HTTPException(422, "Archived tags cannot be assigned")
    if isinstance(obj, m.ResearchRun):
        parent = data.get("parent_run_id")
        visited = {obj.id}
        while parent:
            if parent in visited:
                raise HTTPException(422, "Parent run cycle is not allowed")
            visited.add(parent)
            parent = reference(db, m.ResearchRun, parent, pid).parent_run_id
        module = module_for(db.get(m.Project, pid))
        if data["run_type"] not in {r["id"] for r in module["run_types"]}:
            raise HTTPException(422, "Run type is not defined by this module")
        from .workflow import validate_context

        validate_context(
            module,
            data["run_type"],
            data.get("context_data", {}),
            data.get("status", "planned"),
        )
    if isinstance(obj, m.Metric) and data.get("metric_schema_id"):
        module = module_for(db.get(m.Project, pid))
        if data["metric_schema_id"] not in {r["id"] for r in module["metric_schemas"]}:
            raise HTTPException(422, "Unknown module metric schema")
    if isinstance(obj, m.Gate):
        module = module_for(db.get(m.Project, pid))
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
            if c["status"] == "passed" and not evidence_support_sufficient(
                db, c["evidence_ids"]
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
            if not evidence_support_sufficient(db, data["evidence_ids"]):
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
            if (
                key == "value"
                and isinstance(obj, (m.Parameter, m.Metric))
                and inspect(obj).persistent
            ):
                # Python considers True == 1, including inside dictionaries. JSON
                # scientific values preserve this distinction even when the ORM's
                # default equality would incorrectly suppress the UPDATE.
                flag_modified(obj, key)
    db.flush()


def audit(db, actor, request, action, obj, before=None):
    pid = getattr(obj, "project_id", None)
    if isinstance(obj, m.Project):
        pid = obj.id
    if isinstance(obj, m.ActivityPreference):
        pid = obj.scope or None
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
            after=None if action.startswith("purge_") else serialize(db, obj),
            source="mcp" if actor.token else "web",
            request_id=request.state.request_id,
        )
    )


def evidence_dependents(db, evidence):
    """Snapshot linked gates before an evidence mutation removes its support."""
    gate_links = m.LINKS[("stage_gates", "evidence_ids")]
    criterion_links = m.LINKS[("gate_criteria", "evidence_ids")]
    direct = select(gate_links.c.owner_id).where(gate_links.c.target_id == evidence.id)
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
    evidence = list(
        db.scalars(
            select(m.Evidence).where(
                m.Evidence.id.in_(evidence_ids), m.Evidence.trashed_at.is_(None)
            )
        )
    )
    if not evidence_ids or len(evidence) != len(set(evidence_ids)):
        return False
    for item in evidence:
        if item.status in INSUFFICIENT_EVIDENCE_STATUSES:
            return False
        for field, cls in (
            ("linked_run_id", m.ResearchRun),
            ("linked_artifact_id", m.Artifact),
            ("linked_source_id", m.Source),
        ):
            rid = getattr(item, field)
            if rid:
                linked = db.get(cls, rid)
                if linked is None or linked.trashed_at:
                    return False
    return True


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
                    db,
                    actor,
                    request,
                    "reopen_gate_criterion",
                    criterion,
                    before_criterion,
                )
        if gate.status == "passed" and (
            not criteria
            or any(criterion.status != "passed" for criterion, _ in criteria)
            or not evidence_support_sufficient(db, serialize(db, gate)["evidence_ids"])
        ):
            gate.status = "blocked"
            gate.blocking_reason = (
                f"证据 {evidence_id} {reason}；请重新核验关联证据与 Gate 判据。"
            )
            db.flush()
            audit(db, actor, request, "invalidate_gate_evidence", gate, before_gate)


def create_record(db, actor, request, kind, pid, payload, modules, run_id=None):
    cls = m.COLLECTIONS.get(
        kind, {"parameters": m.Parameter, "metrics": m.Metric}.get(kind)
    )
    if actor.token and kind in {"evidence", "decisions"}:
        payload = {"status": "proposed", **payload}
    data = parsed(kind, payload)
    project_for(db, actor, pid, write=True)
    if run_id:
        resource(db, actor, m.ResearchRun, run_id, write=True)
    scientific_authority(actor, kind, data, creating=True)
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


def project_context(db, actor, pid, modules, collections=None, limit=100):
    from .workflow import audit_query

    p = project_for(db, actor, pid)
    return {
        "project": serialize(db, p),
        "module": copy.deepcopy(module_for(p)),
        **{
            key: [
                serialize(db, o)
                for o in db.scalars(
                    select(cls)
                    .where(
                        cls.project_id == pid,
                        *visible_records(cls),
                    )
                    .order_by(cls.created_at)
                    .limit(limit)
                )
            ]
            if collections is None or key in collections
            else []
            for key, cls in m.COLLECTIONS.items()
        },
        "artifacts": [
            serialize(db, o)
            for o in db.scalars(
                select(m.Artifact)
                .where(
                    m.Artifact.project_id == pid,
                    *visible_records(m.Artifact),
                )
                .limit(limit)
            )
        ]
        if collections is None or "artifacts" in collections
        else [],
        "activity": audit_query(
            db, actor, {"project_id": pid, "limit": str(min(limit, 50))}, activity=True
        )["items"]
        if collections is None or "activity" in collections
        else [],
    }


def run_context(db, actor, rid):
    r = resource(db, actor, m.ResearchRun, rid)
    project = project_for(db, actor, r.project_id)
    module = module_for(project)

    def worksheet_values(cls, schemas):
        # Form values must be queried by schema names, independent of the custom-value page.
        rows = list(
            db.scalars(
                select(cls)
                .where(
                    cls.run_id == rid,
                    cls.name.in_([s["id"] for s in schemas]),
                    *visible_records(cls),
                )
                .order_by(cls.created_at, cls.id)
                .limit(101)
            )
        )
        return [serialize(db, row) for row in rows[:100]], len(rows) > 100

    worksheet_parameters, parameters_incomplete = worksheet_values(
        m.Parameter, module["parameter_schemas"]
    )
    worksheet_metrics, metrics_incomplete = worksheet_values(
        m.Metric, module["metric_schemas"]
    )
    parameters_total = db.scalar(
        select(func.count())
        .select_from(m.Parameter)
        .where(m.Parameter.run_id == rid, *visible_records(m.Parameter))
    )
    metrics_total = db.scalar(
        select(func.count())
        .select_from(m.Metric)
        .where(m.Metric.run_id == rid, *visible_records(m.Metric))
    )
    parent = db.get(m.ResearchRun, r.parent_run_id) if r.parent_run_id else None
    if parent and parent.trashed_at:
        parent = None
    parameters = [
        serialize(db, p)
        for p in db.scalars(
            select(m.Parameter)
            .where(
                m.Parameter.run_id == rid,
                m.Parameter.trashed_at.is_(None),
                m.Parameter.archived_at.is_(None),
            )
            .limit(100)
        )
    ]
    differences = []
    if parent:
        old = {
            p.name: serialize(db, p)
            for p in db.scalars(
                select(m.Parameter)
                .where(
                    m.Parameter.run_id == parent.id,
                    m.Parameter.trashed_at.is_(None),
                    m.Parameter.archived_at.is_(None),
                )
                .limit(100)
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
                select(m.ResearchRun)
                .where(
                    m.ResearchRun.parent_run_id == rid,
                    m.ResearchRun.trashed_at.is_(None),
                    m.ResearchRun.archived_at.is_(None),
                )
                .limit(100)
            )
        ],
        "parameters": parameters,
        "parameters_total": parameters_total,
        "metrics_total": metrics_total,
        "worksheet_parameters": worksheet_parameters,
        "worksheet_metrics": worksheet_metrics,
        "worksheet_parameters_incomplete": parameters_incomplete,
        "worksheet_metrics_incomplete": metrics_incomplete,
        "parameter_diff_incomplete": parameters_total > 100
        or bool(
            parent
            and db.scalar(
                select(func.count())
                .select_from(m.Parameter)
                .where(m.Parameter.run_id == parent.id, *visible_records(m.Parameter))
            )
            > 100
        ),
        "metrics": [
            serialize(db, o)
            for o in db.scalars(
                select(m.Metric)
                .where(
                    m.Metric.run_id == rid,
                    m.Metric.trashed_at.is_(None),
                    m.Metric.archived_at.is_(None),
                )
                .limit(100)
            )
        ],
        "artifacts": [
            serialize(db, o)
            for o in db.scalars(
                select(m.Artifact)
                .where(
                    m.Artifact.run_id == rid,
                    m.Artifact.trashed_at.is_(None),
                    m.Artifact.archived_at.is_(None),
                )
                .limit(100)
            )
        ],
        "referenced_artifacts": [
            serialize(db, obj)
            for obj in db.scalars(
                select(m.Artifact)
                .where(
                    m.Artifact.project_id == r.project_id,
                    m.Artifact.id.in_(
                        select(
                            m.LINKS[("research_runs", "artifact_ids")].c.target_id
                        ).where(
                            m.LINKS[("research_runs", "artifact_ids")].c.owner_id == rid
                        )
                    ),
                    *visible_records(m.Artifact),
                )
                .limit(100)
            )
        ],
        "evidence": [
            serialize(db, o)
            for o in db.scalars(
                select(m.Evidence)
                .where(
                    m.Evidence.linked_run_id == rid,
                    m.Evidence.trashed_at.is_(None),
                    m.Evidence.archived_at.is_(None),
                )
                .limit(100)
            )
        ],
        "changes_from_parent": {
            "description": r.changes_from_parent,
            "parameters": differences,
        },
    }


def lifecycle(db, actor, request, kind, rid, action):
    require_human(actor)
    cls = LIFECYCLE_COLLECTIONS.get(kind)
    if cls is None:
        raise HTTPException(404, "Lifecycle resource type not found")
    obj = resource(db, actor, cls, rid, include_trashed=True, lock=True)
    before = serialize(db, obj)
    dependents = []
    if action == "trash":
        if isinstance(obj, m.Evidence):
            dependents = evidence_dependents(db, obj)
        else:
            field = {
                m.ResearchRun: m.Evidence.linked_run_id,
                m.Artifact: m.Evidence.linked_artifact_id,
                m.Source: m.Evidence.linked_source_id,
            }.get(type(obj))
            if field is not None:
                unique = {}
                for evidence in db.scalars(
                    select(m.Evidence).where(
                        field == obj.id, m.Evidence.trashed_at.is_(None)
                    )
                ):
                    for dependency in evidence_dependents(db, evidence):
                        unique[dependency[0].id] = dependency
                dependents = list(unique.values())
    if action == "trash":
        if obj.trashed_at is None:
            obj.trashed_at = m.now()
    elif action == "archive":
        if obj.trashed_at:
            raise HTTPException(409, "Restore from trash before archiving")
        if obj.archived_at is None:
            obj.archived_at = m.now()
    elif action == "restore":
        if not isinstance(obj, m.Project):
            # A child cannot restore itself through a deleted/archived container.
            if isinstance(obj, (m.Parameter, m.Metric)):
                resource(db, actor, m.ResearchRun, obj.run_id, write=True)
            else:
                project_for(db, actor, obj.project_id, write=True)
        obj.trashed_at = None
        obj.archived_at = None
        if isinstance(obj, m.Project) and obj.status == "archived":
            obj.status = "active"
    else:
        raise HTTPException(422, "Unknown lifecycle action")
    db.flush()
    audit(db, actor, request, action + "_" + kind, obj, before)
    if dependents:
        reconcile_evidence_dependents(
            db, actor, request, dependents, obj.id, "已移入回收站"
        )
    return obj


def purge(db, actor, request, kind, rid):
    require_human(actor)
    cls = LIFECYCLE_COLLECTIONS.get(kind)
    if cls is None:
        raise HTTPException(404, "Lifecycle resource type not found")
    obj = resource(db, actor, cls, rid, include_trashed=True, lock=True)
    stamp = obj.trashed_at
    if stamp is None or (
        stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    ) > m.now() - timedelta(days=TRASH_RETENTION_DAYS):
        raise HTTPException(409, "Permanent deletion requires 30 days in trash")
    artifacts = (
        list(db.scalars(select(m.Artifact).where(m.Artifact.project_id == obj.id)))
        if isinstance(obj, m.Project)
        else [obj]
        if isinstance(obj, m.Artifact)
        else []
    )
    for artifact in artifacts:
        enqueue_object_deletion(
            db, actor.user.id, artifact.project_id, artifact.object_key
        )
    audit(db, actor, request, "purge_" + kind, obj, serialize(db, obj))
    db.flush()
    db.delete(obj)
    db.flush()


def enqueue_object_deletion(db, owner_id, project_id, object_key):
    prefix = f"{owner_id}/{project_id}/"
    if not object_key.startswith(prefix) or "/" in object_key[len(prefix) :]:
        raise HTTPException(422, "Object key does not match its owner and project")
    item = db.scalar(
        select(m.ObjectDeletion).where(m.ObjectDeletion.object_key == object_key)
    )
    if item is None:
        item = m.ObjectDeletion(
            owner_id=owner_id, project_id=project_id, object_key=object_key
        )
        db.add(item)
        db.flush()
    return item


def module_upgrade_preview(project, latest):
    changes = {}
    for field in (
        "run_types",
        "parameter_schemas",
        "metric_schemas",
        "research_stages",
        "stage_gates",
        "custom_views",
        "navigation",
        "artifact_categories",
        "dashboard_widgets",
        "default_capabilities",
        "context_fields",
        "run_forms",
    ):

        def keyed(items):
            return (
                {
                    str(item.get("id", item.get("run_type"))): item
                    for item in items
                    if isinstance(item, dict)
                }
                if items and isinstance(items[0], dict)
                else {str(item): item for item in items}
            )

        old = keyed(project.module_snapshot.get(field, []))
        new = keyed(latest.get(field, []))
        changes[field] = {
            "added": [new[key] for key in sorted(new.keys() - old.keys())],
            "removed": [old[key] for key in sorted(old.keys() - new.keys())],
            "modified": [
                {"id": key, "before": old[key], "after": new[key]}
                for key in sorted(old.keys() & new.keys())
                if old[key] != new[key]
            ],
        }
    return {
        "project_id": project.id,
        "current_version": project.module_version,
        "target_version": latest["version"],
        "target_digest": module_digest(latest),
        "changes": changes,
        "diff": changes,
        "requires_human_confirmation": True,
    }


def module_digest(manifest):
    return hashlib.sha256(
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def upgrade_module(
    db,
    actor,
    request,
    project,
    latest,
    expected_version,
    expected_target_digest,
    modules,
):
    require_human(actor)
    assert_writable(project)
    if project.module_version != expected_version:
        raise HTTPException(409, "Project module version changed; preview again")
    if module_digest(latest) != expected_target_digest:
        raise HTTPException(409, "Target module definition changed; preview again")
    if (
        project.module_version == latest["version"]
        and project.module_snapshot != latest
    ):
        raise HTTPException(409, "Changed module definition requires a new version")
    types = {r["id"] for r in latest["run_types"]}
    metrics = {r["id"] for r in latest["metric_schemas"]}
    stages = {r["id"] for r in latest["research_stages"]}
    gates = {r["id"] for r in latest["stage_gates"]}
    incompatible = (
        db.scalar(
            select(m.ResearchRun.id)
            .where(
                m.ResearchRun.project_id == project.id,
                m.ResearchRun.run_type.not_in(types),
            )
            .limit(1)
        )
        or db.scalar(
            select(m.Metric.id)
            .join(m.ResearchRun)
            .where(
                m.ResearchRun.project_id == project.id,
                m.Metric.metric_schema_id.is_not(None),
                m.Metric.metric_schema_id.not_in(metrics),
            )
            .limit(1)
        )
        or db.scalar(
            select(m.Gate.id)
            .where(
                m.Gate.project_id == project.id,
                or_(m.Gate.stage_id.not_in(stages), m.Gate.gate_id.not_in(gates)),
            )
            .limit(1)
        )
        or project.current_stage
        and project.current_stage not in stages
    )
    if incompatible:
        raise HTTPException(
            422,
            "Module upgrade would invalidate existing research records; keep the frozen definition",
        )
    before = serialize(db, project)
    project.module_version = latest["version"]
    project.module_snapshot = copy.deepcopy(latest)
    existing = set(
        db.scalars(select(m.Gate.gate_id).where(m.Gate.project_id == project.id))
    )
    for gate in latest["stage_gates"]:
        if gate["id"] not in existing:
            create_record(
                db,
                actor,
                request,
                "gates",
                project.id,
                {
                    "gate_id": gate["id"],
                    "stage_id": gate["stage_id"],
                    "name": gate["name"],
                    "description": gate["description"],
                    "criteria": [
                        {**criterion, "status": "not_started", "evidence_ids": []}
                        for criterion in gate["criteria"]
                    ],
                },
                modules,
            )
    db.flush()
    audit(db, actor, request, "upgrade_project_module", project, before)
    return project
