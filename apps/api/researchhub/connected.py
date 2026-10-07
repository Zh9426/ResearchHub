"""Bounded semantic views and safe artifact references shared by API/MCP."""

# ruff: noqa: B008
import copy
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, insert, literal, select, union_all

from . import models as m
from . import service as svc
from .intelligence import page, run_diff, trace
from .schemas import ArtifactRegisterInput
from .workflow import collection_query, pagination


def active_project(db, actor, pid):
    project = svc.project_for(db, actor, pid)
    if project.archived_at or project.status == "archived":
        raise HTTPException(404, "活动项目不存在")
    return project


def active_resource(db, actor, cls, rid):
    obj = svc.resource(db, actor, cls, rid)
    if isinstance(obj, (m.Parameter, m.Metric)):
        parent = active_resource(db, actor, m.ResearchRun, obj.run_id)
        pid = parent.project_id
    elif isinstance(obj, m.GateCriterion):
        pid = active_resource(db, actor, m.Gate, obj.gate_id).project_id
    else:
        pid = obj.project_id
    active_project(db, actor, pid)
    if obj.archived_at or obj.trashed_at:
        raise HTTPException(404, "活动资源不存在")
    return obj


def summary_page(db, actor, pid, params):
    project = active_project(db, actor, pid)
    pagination(params)
    sections = {
        "recent_runs": ("runs", {}),
        "highlighted_runs": ("runs", {"is_highlighted": "true"}),
        "current_tasks": ("tasks", {}),
        "current_gates": ("gates", {}),
        "current_risks": ("risks", {"status": "open"}),
        "current_decisions": ("decisions", {}),
    }
    groups = {}
    for name, (kind, filters) in sections.items():
        if name == "current_tasks":
            groups[name] = page(
                db,
                select(m.Task).where(
                    m.Task.project_id == pid,
                    m.Task.status != "done",
                    *svc.visible_records(m.Task),
                ),
                m.Task,
                params,
            )
        else:
            groups[name] = collection_query(db, actor, pid, kind, {**params, **filters})
    from .workflow import QUERY_COLLECTIONS

    counts = {
        kind: db.scalar(
            select(func.count())
            .select_from(cls)
            .where(cls.project_id == pid, *svc.visible_records(cls))
        )
        for kind, cls in QUERY_COLLECTIONS.items()
    }
    evidence_summary = dict(
        db.execute(
            select(m.Evidence.status, func.count())
            .where(m.Evidence.project_id == pid, *svc.visible_records(m.Evidence))
            .group_by(m.Evidence.status)
        ).all()
    )
    return {
        "project": svc.serialize(db, project),
        "module": copy.deepcopy(svc.module_for(project)),
        "counts": counts,
        "evidence_summary": evidence_summary,
        "groups": groups,
    }


def run_page(db, actor, rid, params):
    run = active_resource(db, actor, m.ResearchRun, rid)
    link = m.LINKS[("research_runs", "artifact_ids")]
    definitions = {
        "parameters": (m.Parameter, m.Parameter.run_id == rid),
        "metrics": (m.Metric, m.Metric.run_id == rid),
        "artifacts": (m.Artifact, m.Artifact.run_id == rid),
        "referenced_artifacts": (
            m.Artifact,
            m.Artifact.id.in_(select(link.c.target_id).where(link.c.owner_id == rid)),
        ),
        "evidence": (m.Evidence, m.Evidence.linked_run_id == rid),
        "notes": (m.Note, m.Note.run_id == rid),
        "children": (m.ResearchRun, m.ResearchRun.parent_run_id == rid),
    }
    groups = {}
    for kind, (cls, condition) in definitions.items():
        statement = select(cls).where(condition, *svc.visible_records(cls))
        if hasattr(cls, "project_id"):
            statement = statement.where(cls.project_id == run.project_id)
        groups[kind] = page(db, statement, cls, params)
    parent = (
        db.scalar(
            select(m.ResearchRun).where(
                m.ResearchRun.id == run.parent_run_id,
                m.ResearchRun.project_id == run.project_id,
                *svc.visible_records(m.ResearchRun),
            )
        )
        if run.parent_run_id
        else None
    )
    return {
        "run": svc.serialize(db, run),
        "parent": svc.serialize(db, parent) if parent else None,
        "groups": groups,
    }


def current_blockers(db, actor, pid, params):
    active_project(db, actor, pid)
    definitions = (
        (
            "runs",
            m.ResearchRun,
            m.ResearchRun.status == "blocked",
            m.ResearchRun.title,
            m.ResearchRun.next_step,
        ),
        ("tasks", m.Task, m.Task.status == "blocked", m.Task.title, m.Task.description),
        (
            "milestones",
            m.Milestone,
            m.Milestone.status == "blocked",
            m.Milestone.title,
            m.Milestone.description,
        ),
        (
            "gates",
            m.Gate,
            m.Gate.status.in_(["blocked", "failed"]),
            m.Gate.name,
            m.Gate.blocking_reason,
        ),
        ("risks", m.Risk, m.Risk.status == "open", m.Risk.title, m.Risk.mitigation),
    )
    statements = [
        select(
            literal(kind).label("kind"),
            cls.id.label("id"),
            cls.project_id.label("project_id"),
            title.label("title"),
            cls.status.label("status"),
            detail.label("detail"),
            cls.created_at.label("created_at"),
        ).where(cls.project_id == pid, condition, *svc.visible_records(cls))
        for kind, cls, condition, title, detail in definitions
    ]
    combined = union_all(*statements).subquery()
    limit, offset = pagination(params)
    total = db.scalar(select(func.count()).select_from(combined))
    items = [
        dict(row)
        for row in db.execute(
            select(combined)
            .order_by(combined.c.created_at.desc(), combined.c.id)
            .limit(limit)
            .offset(offset)
        ).mappings()
    ]
    return jsonable_encoder(
        {"items": items, "total": total, "limit": limit, "offset": offset}
    )


def register_artifact(db, actor, request, rid, payload):
    run = svc.resource(db, actor, m.ResearchRun, rid, write=True)
    artifact = svc.resource(db, actor, m.Artifact, str(payload.file_id))
    if artifact.project_id != run.project_id:
        raise HTTPException(422, "附件必须属于 Run 所在项目")
    svc.assert_writable(artifact)
    if artifact.run_id:
        svc.assert_writable(svc.resource(db, actor, m.ResearchRun, artifact.run_id))
    link = m.LINKS[("research_runs", "artifact_ids")]
    exists = db.scalar(
        select(link.c.target_id).where(
            link.c.owner_id == rid, link.c.target_id == artifact.id
        )
    )
    if not exists:
        before = svc.serialize(db, run)
        db.execute(insert(link).values(owner_id=rid, target_id=artifact.id))
        run.updated_at = m.now()
        db.flush()
        svc.audit(db, actor, request, "register_artifact", run, before)
    return {
        "run_id": rid,
        "artifact": svc.serialize(db, artifact),
        "already_linked": bool(exists),
    }


def install_connected(app, actor_dep, db_dep):
    @app.get("/api/runs/{rid}/compare")
    def compare(
        rid: UUID,
        other_run_id: UUID,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        current = active_resource(db, actor, m.ResearchRun, str(rid))
        other = active_resource(db, actor, m.ResearchRun, str(other_run_id))
        if current.project_id != other.project_id:
            raise HTTPException(422, "比较 Run 必须属于同一项目")
        params = dict(request.query_params)
        return {
            "current": svc.serialize(db, current),
            "other": svc.serialize(db, other),
            "groups": {
                kind: run_diff(db, actor, str(rid), {**params, "kind": kind})
                for kind in ("parameters", "metrics")
            },
        }

    @app.get("/api/projects/{pid}/blockers")
    def blockers(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return current_blockers(db, actor, str(pid), dict(request.query_params))

    @app.get("/api/projects/{pid}/evidence-trace/{kind}/{rid}")
    def evidence_trace(
        pid: UUID,
        kind: str,
        rid: UUID,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        from .intelligence import GROUP_MODELS

        if kind not in GROUP_MODELS:
            raise HTTPException(422, "未知追踪类型")
        active_project(db, actor, str(pid))
        active_resource(db, actor, GROUP_MODELS[kind], str(rid))
        return trace(db, actor, str(pid), kind, str(rid), dict(request.query_params))

    @app.post("/api/runs/{rid}/artifacts/register")
    def register(
        rid: UUID,
        payload: ArtifactRegisterInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        result = register_artifact(db, actor, request, str(rid), payload)
        db.commit()
        return result
