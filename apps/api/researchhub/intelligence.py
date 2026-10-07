"""Owner-scoped, read-only research lineage, audit history and evidence queries."""

# FastAPI dependency declarations intentionally use call defaults.
# ruff: noqa: B008
import json
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import String, and_, cast, func, literal, or_, select, union
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.inspection import inspect

from . import models as m
from . import service as svc
from .workflow import filter_values, pagination, search_pattern

GROUP_MODELS = {
    "claims": m.Claim,
    "evidence": m.Evidence,
    "runs": m.ResearchRun,
    "artifacts": m.Artifact,
    "sources": m.Source,
    "parameters": m.Parameter,
    "metrics": m.Metric,
    "gates": m.Gate,
    "criteria": m.GateCriterion,
    "decisions": m.Decision,
}


def semantic_equal(left, right):
    """JSON equality matches PostgreSQL JSONB, including numeric and boolean types."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            semantic_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            semantic_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def sqlite_json_equal(left, right):
    def decoded(value):
        return (
            json.loads(value, parse_int=Decimal, parse_float=Decimal)
            if isinstance(value, (str, bytes))
            else value
        )

    return int(semantic_equal(decoded(left), decoded(right)))


def serialize_many(db, objects):
    """Load association collections per table, rather than once per record."""
    if not objects:
        return []
    cls = type(objects[0])
    records = {
        obj.id: {attr.key: getattr(obj, attr.key) for attr in inspect(cls).column_attrs}
        for obj in objects
    }
    for (table, key), link in m.LINKS.items():
        if table != cls.__tablename__:
            continue
        for data in records.values():
            data[key] = []
        statement = select(link.c.owner_id, link.c.target_id).where(
            link.c.owner_id.in_(records)
        )
        if key == "tag_ids":
            statement = statement.join(m.Tag, m.Tag.id == link.c.target_id).where(
                *svc.visible_records(m.Tag)
            )
        for owner_id, target_id in db.execute(statement):
            records[owner_id][key].append(target_id)
    if cls is m.Artifact:
        for data in records.values():
            data["metadata"] = data.pop("artifact_metadata")
    if cls is m.Gate:
        criteria = list(
            db.scalars(
                select(m.GateCriterion).where(
                    m.GateCriterion.gate_id.in_(records),
                    *svc.visible_records(m.GateCriterion),
                )
            )
        )
        for data in records.values():
            data["criteria"] = []
        for data in serialize_many(db, criteria):
            gate_id = data["gate_id"]
            data["id"] = data["criterion_id"]
            for key in (
                "criterion_id",
                "gate_id",
                "created_at",
                "updated_at",
                "archived_at",
                "trashed_at",
            ):
                data.pop(key, None)
            records[gate_id]["criteria"].append(data)
    return jsonable_encoder(list(records.values()))


def page(db, statement, cls, params):
    limit, offset = pagination(params)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    objects = list(
        db.scalars(
            statement.order_by(cls.created_at.desc(), cls.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return {
        "items": serialize_many(db, objects),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def run_values(db, actor, rid, kind, params, response=None):
    svc.resource(db, actor, m.ResearchRun, rid)
    cls = m.Parameter if kind == "parameters" else m.Metric
    statement = select(cls).where(cls.run_id == rid, *svc.visible_records(cls))
    if params.get("q"):
        statement = statement.where(
            cls.name.ilike(search_pattern(params["q"][:300]), escape="\\")
        )
    is_page = params.get("format") == "page"
    bounded_params = {"limit": "50" if is_page else "100", **params}
    result = page(db, statement, cls, bounded_params)
    if response is not None:
        response.headers["X-Total-Count"] = str(result["total"])
    return result if is_page else result["items"]


def history(db, actor, rid, kind, params):
    cls = m.Parameter if kind == "parameters" else m.Metric
    svc.resource(db, actor, cls, rid, include_trashed=True)
    statement = select(m.AuditLog).where(
        m.AuditLog.owner_id == actor.user.id,
        m.AuditLog.resource_type == cls.__tablename__,
        m.AuditLog.resource_id == rid,
    )
    limit, offset = pagination(params)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = serialize_many(
        db,
        list(
            db.scalars(
                statement.order_by(m.AuditLog.timestamp.desc(), m.AuditLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ),
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def diff_statement(db, current, parent, cls):
    # Duplicate historical names are ambiguous; require an explicit cleanup.
    duplicate = db.scalar(
        select(cls.name)
        .where(cls.run_id.in_([current, parent]), *svc.visible_records(cls))
        .group_by(cls.run_id, cls.name)
        .having(func.count() > 1)
        .limit(1)
    )
    if duplicate is not None:
        raise HTTPException(409, "重复名称无法自动比较，请先整理记录")
    left = select(cls).where(cls.run_id == parent, *svc.visible_records(cls)).subquery()
    right = (
        select(cls).where(cls.run_id == current, *svc.visible_records(cls)).subquery()
    )
    fields = [
        attr.key
        for attr in inspect(cls).column_attrs
        if attr.key
        not in {
            "id",
            "run_id",
            "name",
            "created_at",
            "updated_at",
            "archived_at",
            "trashed_at",
        }
    ]
    changes = [
        cast(left.c[key], String).is_distinct_from(cast(right.c[key], String))
        for key in fields
        if key != "value"
    ]
    if db.get_bind().dialect.name == "postgresql":
        changes.append(
            func.coalesce(
                cast(left.c.value, JSONB), cast(literal("null"), JSONB)
            ).is_distinct_from(
                func.coalesce(cast(right.c.value, JSONB), cast(literal("null"), JSONB))
            )
        )
    else:
        changes.append(func.researchhub_json_equal(left.c.value, right.c.value) == 0)
    if cls is m.Metric:
        link = m.LINKS[("metrics", "artifact_ids")]
        other = link.alias()
        # Association order is irrelevant; compare both set differences.
        changes.extend(
            [
                select(link.c.target_id)
                .where(
                    link.c.owner_id == left.c.id,
                    ~select(other.c.target_id)
                    .where(
                        other.c.owner_id == right.c.id,
                        other.c.target_id == link.c.target_id,
                    )
                    .correlate(left, right, link)
                    .exists(),
                )
                .correlate(left, right)
                .exists(),
                select(link.c.target_id)
                .where(
                    link.c.owner_id == right.c.id,
                    ~select(other.c.target_id)
                    .where(
                        other.c.owner_id == left.c.id,
                        other.c.target_id == link.c.target_id,
                    )
                    .correlate(left, right, link)
                    .exists(),
                )
                .correlate(left, right)
                .exists(),
            ]
        )
    existing = (
        select(
            left.c.id.label("parent_id"), right.c.id.label("current_id"), left.c.name
        )
        .select_from(left.outerjoin(right, left.c.name == right.c.name))
        .where(or_(right.c.id.is_(None), *changes))
    )
    added = (
        select(
            literal(None).label("parent_id"),
            right.c.id.label("current_id"),
            right.c.name,
        )
        .select_from(right.outerjoin(left, right.c.name == left.c.name))
        .where(left.c.id.is_(None))
    )
    return union(existing, added).subquery()


def run_diff(db, actor, rid, params):
    current = svc.resource(db, actor, m.ResearchRun, rid)
    parent_id = params.get("other_run_id") or current.parent_run_id
    kind = params.get("kind", "parameters")
    if kind not in {"parameters", "metrics"}:
        raise HTTPException(422, "比较类型必须是 parameters 或 metrics")
    limit, offset = pagination(params)
    if not parent_id:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "other_run_id": None,
        }
    parent = svc.resource(db, actor, m.ResearchRun, parent_id)
    if parent.project_id != current.project_id:
        raise HTTPException(422, "比较 Run 必须属于同一项目")
    cls = m.Parameter if kind == "parameters" else m.Metric
    statement = diff_statement(db, current.id, parent.id, cls)
    total = db.scalar(select(func.count()).select_from(statement))
    rows = db.execute(
        select(statement).order_by(statement.c.name).limit(limit).offset(offset)
    ).all()
    ids = {iid for row in rows for iid in (row.parent_id, row.current_id) if iid}
    records = {
        record["id"]: record
        for record in serialize_many(
            db, list(db.scalars(select(cls).where(cls.id.in_(ids))))
        )
    }
    ignored = {"id", "run_id", "created_at", "updated_at", "archived_at", "trashed_at"}
    items = []
    for row in rows:
        previous, present = records.get(row.parent_id), records.get(row.current_id)
        fields = {
            key: {
                "parent": (previous or {}).get(key),
                "current": (present or {}).get(key),
            }
            for key in set(previous or {}) | set(present or {})
            if key not in ignored
            and (
                set((previous or {}).get(key, [])) != set((present or {}).get(key, []))
                if key == "artifact_ids"
                else not semantic_equal(
                    (previous or {}).get(key), (present or {}).get(key)
                )
            )
        }
        items.append(
            {
                "name": row.name,
                "change_type": "added"
                if previous is None
                else "removed"
                if present is None
                else "changed",
                "fields": fields,
                "parent_record": previous,
                "current_record": present,
            }
        )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "other_run_id": parent.id,
    }


def project_lineage(db, actor, pid, params):
    svc.project_for(db, actor, pid)
    statement = select(m.ResearchRun).where(
        m.ResearchRun.project_id == pid, *svc.visible_records(m.ResearchRun)
    )
    result = page(db, statement, m.ResearchRun, params)
    for node in result["items"]:
        summary = {"names": [], "total": 0}
        if node["parent_run_id"]:
            parent = db.scalar(
                select(m.ResearchRun).where(
                    m.ResearchRun.id == node["parent_run_id"],
                    m.ResearchRun.project_id == pid,
                    *svc.visible_records(m.ResearchRun),
                )
            )
            if parent:
                try:
                    changes = diff_statement(db, node["id"], parent.id, m.Parameter)
                    summary["total"] = db.scalar(
                        select(func.count()).select_from(changes)
                    )
                    summary["names"] = list(
                        db.scalars(
                            select(changes.c.name).order_by(changes.c.name).limit(5)
                        )
                    )
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
                    summary["ambiguous"] = True
        node["parameter_change_summary"] = summary
    return {
        "nodes": result["items"],
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
        "truncated": result["total"] > len(result["items"]),
    }


def scoped_ids(cls, pid, condition):
    if cls in (m.Parameter, m.Metric):
        statement = (
            select(cls.id)
            .join(m.ResearchRun, m.ResearchRun.id == cls.run_id)
            .where(m.ResearchRun.project_id == pid, *svc.visible_records(m.ResearchRun))
        )
    elif cls is m.GateCriterion:
        statement = (
            select(cls.id)
            .join(m.Gate, m.Gate.id == cls.gate_id)
            .where(m.Gate.project_id == pid, *svc.visible_records(m.Gate))
        )
    else:
        statement = select(cls.id).where(cls.project_id == pid)
    scoped = statement.where(condition, *svc.visible_records(cls)).cte()
    return select(scoped.c.id)


def owners(table, key, ids):
    link = m.LINKS[(table, key)]
    return select(link.c.owner_id).where(link.c.target_id.in_(ids))


def targets(table, key, ids):
    link = m.LINKS[(table, key)]
    return select(link.c.target_id).where(link.c.owner_id.in_(ids))


def trace_ids(pid, kind, rid):
    empty = select(literal(None)).where(literal(False))
    seed = select(literal(rid))
    claims = scoped_ids(
        m.Claim, pid, m.Claim.id.in_(seed if kind == "claims" else empty)
    )
    starting_sources = scoped_ids(
        m.Source,
        pid,
        or_(
            m.Source.id.in_(seed if kind == "sources" else empty),
            m.Source.id.in_(targets("claims", "source_ids", claims)),
        ),
    )
    starting_artifacts = scoped_ids(
        m.Artifact,
        pid,
        or_(
            m.Artifact.id.in_(seed if kind == "artifacts" else empty),
            m.Artifact.id.in_(targets("claims", "artifact_ids", claims)),
        ),
    )
    starting_parameters = scoped_ids(
        m.Parameter,
        pid,
        or_(
            m.Parameter.id.in_(seed if kind == "parameters" else empty),
            m.Parameter.source_id.in_(starting_sources),
        ),
    )
    starting_metrics = scoped_ids(
        m.Metric,
        pid,
        or_(
            m.Metric.id.in_(seed if kind == "metrics" else empty),
            m.Metric.source_id.in_(starting_sources),
            m.Metric.id.in_(owners("metrics", "artifact_ids", starting_artifacts)),
        ),
    )
    starting_runs = scoped_ids(
        m.ResearchRun,
        pid,
        or_(
            m.ResearchRun.id.in_(seed if kind == "runs" else empty),
            m.ResearchRun.id.in_(targets("claims", "run_ids", claims)),
            m.ResearchRun.id.in_(
                select(m.Parameter.run_id).where(
                    m.Parameter.id.in_(starting_parameters)
                )
            ),
            m.ResearchRun.id.in_(
                select(m.Metric.run_id).where(m.Metric.id.in_(starting_metrics))
            ),
            m.ResearchRun.id.in_(
                select(m.Artifact.run_id).where(m.Artifact.id.in_(starting_artifacts))
            ),
            m.ResearchRun.id.in_(
                owners("research_runs", "artifact_ids", starting_artifacts)
            ),
        ),
    )
    evidence_condition = m.Evidence.id.in_(
        seed if kind == "evidence" else targets("claims", "evidence_ids", claims)
    )
    evidence_condition = or_(
        evidence_condition,
        m.Evidence.linked_run_id.in_(starting_runs),
        m.Evidence.linked_source_id.in_(starting_sources),
        m.Evidence.linked_artifact_id.in_(starting_artifacts),
    )
    if kind == "runs":
        evidence_condition = or_(evidence_condition, m.Evidence.linked_run_id == rid)
    if kind == "artifacts":
        run_artifacts = owners("research_runs", "artifact_ids", seed)
        artifact_runs = select(m.Artifact.run_id).where(m.Artifact.id == rid)
        evidence_condition = or_(
            evidence_condition,
            m.Evidence.linked_artifact_id == rid,
            m.Evidence.linked_run_id.in_(union(run_artifacts, artifact_runs)),
        )
    if kind == "sources":
        evidence_condition = or_(evidence_condition, m.Evidence.linked_source_id == rid)
    if kind in {"gates", "criteria", "decisions"}:
        table = GROUP_MODELS[kind].__tablename__
        evidence_condition = or_(
            evidence_condition, m.Evidence.id.in_(targets(table, "evidence_ids", seed))
        )
    evidence = scoped_ids(m.Evidence, pid, evidence_condition)
    run_condition = or_(
        m.ResearchRun.id.in_(starting_runs),
        m.ResearchRun.id.in_(seed if kind == "runs" else empty),
        m.ResearchRun.id.in_(targets("claims", "run_ids", claims)),
        m.ResearchRun.id.in_(
            select(m.Evidence.linked_run_id).where(m.Evidence.id.in_(evidence))
        ),
    )
    if kind == "artifacts":
        run_condition = or_(
            run_condition,
            m.ResearchRun.id.in_(owners("research_runs", "artifact_ids", seed)),
            m.ResearchRun.id.in_(select(m.Artifact.run_id).where(m.Artifact.id == rid)),
        )
    runs = scoped_ids(m.ResearchRun, pid, run_condition)
    # Runs reached through Evidence can themselves participate in other support.
    evidence = scoped_ids(
        m.Evidence,
        pid,
        or_(m.Evidence.id.in_(evidence), m.Evidence.linked_run_id.in_(runs)),
    )
    base_sources = scoped_ids(
        m.Source,
        pid,
        or_(
            m.Source.id.in_(starting_sources),
            m.Source.id.in_(
                select(m.Evidence.linked_source_id).where(m.Evidence.id.in_(evidence))
            ),
        ),
    )
    base_artifacts = scoped_ids(
        m.Artifact,
        pid,
        or_(
            m.Artifact.id.in_(starting_artifacts),
            m.Artifact.id.in_(
                select(m.Evidence.linked_artifact_id).where(m.Evidence.id.in_(evidence))
            ),
        ),
    )
    parameters = scoped_ids(
        m.Parameter,
        pid,
        or_(
            m.Parameter.run_id.in_(runs),
            m.Parameter.source_id.in_(base_sources),
            m.Parameter.id.in_(starting_parameters),
        ),
    )
    metrics = scoped_ids(
        m.Metric,
        pid,
        or_(
            m.Metric.run_id.in_(runs),
            m.Metric.source_id.in_(base_sources),
            m.Metric.id.in_(owners("metrics", "artifact_ids", base_artifacts)),
            m.Metric.id.in_(starting_metrics),
        ),
    )
    artifacts = scoped_ids(
        m.Artifact,
        pid,
        or_(
            m.Artifact.id.in_(seed if kind == "artifacts" else empty),
            m.Artifact.run_id.in_(runs),
            m.Artifact.id.in_(targets("research_runs", "artifact_ids", runs)),
            m.Artifact.id.in_(targets("claims", "artifact_ids", claims)),
            m.Artifact.id.in_(targets("metrics", "artifact_ids", metrics)),
            m.Artifact.id.in_(
                select(m.Evidence.linked_artifact_id).where(m.Evidence.id.in_(evidence))
            ),
        ),
    )
    sources = scoped_ids(
        m.Source,
        pid,
        or_(
            m.Source.id.in_(seed if kind == "sources" else empty),
            m.Source.id.in_(targets("claims", "source_ids", claims)),
            m.Source.id.in_(
                select(m.Parameter.source_id).where(m.Parameter.id.in_(parameters))
            ),
            m.Source.id.in_(select(m.Metric.source_id).where(m.Metric.id.in_(metrics))),
            m.Source.id.in_(
                select(m.Evidence.linked_source_id).where(m.Evidence.id.in_(evidence))
            ),
        ),
    )
    reverse_claims = scoped_ids(
        m.Claim,
        pid,
        or_(
            m.Claim.id.in_(claims),
            m.Claim.id.in_(owners("claims", "evidence_ids", evidence)),
            m.Claim.id.in_(owners("claims", "run_ids", runs)),
            m.Claim.id.in_(owners("claims", "artifact_ids", artifacts))
            if kind == "artifacts"
            else literal(False),
            m.Claim.id.in_(owners("claims", "source_ids", sources))
            if kind == "sources"
            else literal(False),
        ),
    )
    criteria = scoped_ids(
        m.GateCriterion,
        pid,
        or_(
            m.GateCriterion.id.in_(owners("gate_criteria", "evidence_ids", evidence)),
            m.GateCriterion.id.in_(seed if kind == "criteria" else empty),
            m.GateCriterion.gate_id.in_(seed if kind == "gates" else empty),
        ),
    )
    gates = scoped_ids(
        m.Gate,
        pid,
        or_(
            m.Gate.id.in_(owners("stage_gates", "evidence_ids", evidence)),
            m.Gate.id.in_(
                select(m.GateCriterion.gate_id).where(m.GateCriterion.id.in_(criteria))
            ),
            m.Gate.id.in_(seed if kind == "gates" else empty),
        ),
    )
    decisions = scoped_ids(
        m.Decision,
        pid,
        or_(
            m.Decision.id.in_(owners("decisions", "evidence_ids", evidence)),
            m.Decision.run_id.in_(runs),
            m.Decision.id.in_(seed if kind == "decisions" else empty),
        ),
    )
    return {
        "claims": reverse_claims,
        "evidence": evidence,
        "runs": runs,
        "artifacts": artifacts,
        "sources": sources,
        "parameters": parameters,
        "metrics": metrics,
        "gates": gates,
        "criteria": criteria,
        "decisions": decisions,
    }


def trace(db, actor, pid, kind, rid, params):
    svc.project_for(db, actor, pid)
    if kind not in GROUP_MODELS:
        raise HTTPException(422, "未知追踪类型")
    subject = svc.resource(db, actor, GROUP_MODELS[kind], rid)
    if isinstance(subject, (m.Parameter, m.Metric)):
        subject_pid = svc.resource(db, actor, m.ResearchRun, subject.run_id).project_id
    elif isinstance(subject, m.GateCriterion):
        subject_pid = svc.resource(db, actor, m.Gate, subject.gate_id).project_id
    else:
        subject_pid = subject.project_id
    if subject_pid != pid:
        raise HTTPException(404, "项目内资源不存在")
    ids = trace_ids(pid, kind, rid)
    groups = {
        key: page(db, select(cls).where(cls.id.in_(ids[key])), cls, params)
        for key, cls in GROUP_MODELS.items()
    }
    return {"subject": svc.serialize(db, subject), "groups": groups}


def evidence_impact(db, actor, rid, params):
    evidence = svc.resource(db, actor, m.Evidence, rid, include_trashed=True)
    pid = evidence.project_id
    # Impact must remain inspectable after trash. Links are queried directly.
    seed = select(literal(rid))
    criteria = scoped_ids(
        m.GateCriterion,
        pid,
        m.GateCriterion.id.in_(owners("gate_criteria", "evidence_ids", seed)),
    )
    conditions = {
        "claims": m.Claim.id.in_(owners("claims", "evidence_ids", seed)),
        "criteria": m.GateCriterion.id.in_(criteria),
        "gates": or_(
            m.Gate.id.in_(owners("stage_gates", "evidence_ids", seed)),
            m.Gate.id.in_(
                select(m.GateCriterion.gate_id).where(m.GateCriterion.id.in_(criteria))
            ),
        ),
        "decisions": m.Decision.id.in_(owners("decisions", "evidence_ids", seed)),
    }
    groups = {
        kind: page(
            db,
            select(GROUP_MODELS[kind]).where(
                GROUP_MODELS[kind].id.in_(
                    scoped_ids(GROUP_MODELS[kind], pid, condition)
                )
            ),
            GROUP_MODELS[kind],
            params,
        )
        for kind, condition in conditions.items()
    }
    return {"evidence": svc.serialize(db, evidence), "groups": groups}


def project_metrics(db, actor, pid, params):
    svc.project_for(db, actor, pid)
    statement = (
        select(m.Metric, m.ResearchRun)
        .join(m.ResearchRun, m.ResearchRun.id == m.Metric.run_id)
        .where(
            m.ResearchRun.project_id == pid,
            *svc.visible_records(m.ResearchRun),
            *svc.visible_records(m.Metric),
        )
    )
    for key, column in (
        ("run_types", m.ResearchRun.run_type),
        ("status", m.Metric.status),
        ("run_status", m.ResearchRun.status),
        ("scientific_outcome", m.ResearchRun.scientific_outcome),
    ):
        if params.get(key):
            statement = statement.where(column.in_(filter_values(params[key])))
    if params.get("metric_ids"):
        ids = filter_values(params["metric_ids"])
        statement = statement.where(
            or_(
                m.Metric.metric_schema_id.in_(ids),
                and_(m.Metric.metric_schema_id.is_(None), m.Metric.name.in_(ids)),
            )
        )
    if params.get("q"):
        statement = statement.where(
            m.Metric.name.ilike(search_pattern(params["q"][:300]), escape="\\")
        )
    if params.get("is_highlighted") is not None:
        if params["is_highlighted"] not in {"true", "false"}:
            raise HTTPException(422, "is_highlighted 必须是 true 或 false")
        statement = statement.where(
            m.ResearchRun.is_highlighted.is_(params["is_highlighted"] == "true")
        )
    limit, offset = pagination(params)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(
        statement.order_by(m.Metric.created_at.desc(), m.Metric.id)
        .limit(limit)
        .offset(offset)
    ).all()
    metrics = serialize_many(db, [row[0] for row in rows])
    for metric, (_, run) in zip(metrics, rows, strict=True):
        metric["run"] = {
            key: getattr(run, key)
            for key in (
                "id",
                "title",
                "run_type",
                "status",
                "scientific_outcome",
                "is_highlighted",
            )
        }
    return {"items": metrics, "total": total, "limit": limit, "offset": offset}


def install_intelligence(app, actor_dep, db_dep):
    @app.get("/api/parameters/{rid}/history")
    def parameter_history(
        rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return history(db, actor, str(rid), "parameters", dict(request.query_params))

    @app.get("/api/metrics/{rid}/history")
    def metric_history(
        rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return history(db, actor, str(rid), "metrics", dict(request.query_params))

    @app.get("/api/runs/{rid}/diff")
    def diff(rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)):
        return run_diff(db, actor, str(rid), dict(request.query_params))

    @app.get("/api/projects/{pid}/lineage")
    def lineage(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return project_lineage(db, actor, str(pid), dict(request.query_params))

    @app.get("/api/projects/{pid}/trace/{kind}/{rid}")
    def trace_route(
        pid: UUID,
        kind: str,
        rid: UUID,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        return trace(db, actor, str(pid), kind, str(rid), dict(request.query_params))

    @app.get("/api/evidence/{rid}/impact")
    def impact(
        rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return evidence_impact(db, actor, str(rid), dict(request.query_params))

    @app.get("/api/projects/{pid}/metrics/query")
    def metrics(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return project_metrics(db, actor, str(pid), dict(request.query_params))
