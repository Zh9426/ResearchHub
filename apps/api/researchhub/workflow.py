"""Human research workflow. All writes share project locking and scientific authority."""

# FastAPI dependency declarations intentionally use call defaults.
# ruff: noqa: B008
import copy
import json
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import func, literal, or_, select, union_all

from . import models as m
from . import service as svc
from .modules import CAPABILITIES
from .schemas import (
    SCHEMAS,
    ActivityClearInput,
    CloneInput,
    HighlightInput,
    ParametersBatch,
    TaggedInput,
)

QUERY_COLLECTIONS = {**m.COLLECTIONS, "artifacts": m.Artifact}


def validate_context(module, run_type, context, status="planned"):
    if len(json.dumps(context, ensure_ascii=False)) > 65536:
        raise HTTPException(422, "工作上下文不能超过 64 KiB")
    fields = {f["id"]: f for f in module.get("context_fields", [])}
    if any(key not in fields for key in context):
        raise HTTPException(422, "工作上下文字段未在项目冻结模块中定义")
    forms = [f for f in module.get("run_forms", []) if f["run_type"] == run_type]
    if forms:
        allowed = {
            key for form in forms for group in form["groups"] for key in group["fields"]
        }
        if any(key not in allowed for key in context):
            raise HTTPException(422, "上下文字段不适用于该研究记录类型")
    else:
        allowed = set(fields)
    types = {
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "object": dict,
        "array": list,
    }
    for key, value in context.items():
        if value is not None and (
            not isinstance(value, types[fields[key]["value_type"]])
            or fields[key]["value_type"] in {"integer", "number"}
            and isinstance(value, bool)
        ):
            raise HTTPException(422, f"上下文字段 {key} 类型不正确")
    if status in {"running", "completed"}:
        missing = [
            key
            for key, field in fields.items()
            if key in allowed
            and field.get("required")
            and (context.get(key) is None or context.get(key) == "")
        ]
        if missing:
            raise HTTPException(
                422, "开始或完成记录前请补齐上下文字段：" + "、".join(missing)
            )


def positive_int(value, default, maximum=None):
    try:
        result = int(default if value is None else value)
    except (ValueError, TypeError):
        raise HTTPException(422, "分页参数必须是整数")
    if result < 0 or maximum and result > maximum:
        raise HTTPException(422, "分页参数超出范围")
    return result


def pagination(params):
    limit = positive_int(params.get("limit"), 50, 100)
    if not limit:
        raise HTTPException(422, "limit 必须大于零")
    return limit, positive_int(params.get("offset"), 0)


def date_value(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(422, "日期必须使用 ISO 8601 格式")


def search_pattern(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def text_filter(cls, q):
    fields = [
        getattr(cls, key)
        for key in (
            "title",
            "name",
            "filename",
            "description",
            "objective",
            "observation",
            "statement",
            "content",
            "decision",
        )
        if hasattr(cls, key)
    ]
    return or_(*(field.ilike(search_pattern(q), escape="\\") for field in fields))


def filter_values(value):
    values = [part.strip() for part in value.split(",") if part.strip()]
    if not values or len(values) > 100 or any(len(part) > 200 for part in values):
        raise HTTPException(422, "筛选列表应包含 1–100 个值，每个值不超过 200 字符")
    return list(dict.fromkeys(values))


def collection_statement(db, actor, pid, kind, params):
    project = svc.project_for(db, actor, pid)
    if params.get("active_only") == "true" and (
        project.archived_at or project.status == "archived"
    ):
        raise HTTPException(404, "活动项目不存在")
    cls = QUERY_COLLECTIONS.get(kind)
    if cls is None:
        raise HTTPException(404, "记录集合不存在")
    clauses = [cls.project_id == pid, *svc.visible_records(cls)]
    if params.get("q"):
        clauses.append(text_filter(cls, params["q"][:300]))
    for key, column in (
        ("artifact_categories", getattr(cls, "category", None)),
        ("evidence_statuses", cls.status if cls is m.Evidence else None),
        ("evidence_types", getattr(cls, "evidence_type", None)),
    ):
        if params.get(key) and column is not None:
            clauses.append(column.in_(filter_values(params[key])))
    if params.get("run_types"):
        types = filter_values(params["run_types"])
        selected_runs = select(m.ResearchRun.id).where(
            m.ResearchRun.project_id == pid,
            m.ResearchRun.run_type.in_(types),
            *svc.visible_records(m.ResearchRun),
        )
        if cls is m.ResearchRun:
            clauses.append(cls.run_type.in_(types))
        elif cls is m.Evidence:
            clauses.append(cls.linked_run_id.in_(selected_runs))
        elif cls is m.Artifact:
            link = m.LINKS[("research_runs", "artifact_ids")]
            clauses.append(
                or_(
                    cls.run_id.in_(selected_runs),
                    cls.id.in_(
                        select(link.c.target_id).where(
                            link.c.owner_id.in_(selected_runs)
                        )
                    ),
                )
            )
        elif hasattr(cls, "run_id"):
            clauses.append(cls.run_id.in_(selected_runs))
    aliases = {
        "outcome": "scientific_outcome",
        "type": "evidence_type"
        if cls is m.Evidence
        else "mime_type"
        if cls is m.Artifact
        else "run_type",
        "parent": "parent_run_id",
        "run": "linked_run_id" if cls is m.Evidence else "run_id",
        "run_id": "linked_run_id" if cls is m.Evidence else "run_id",
    }
    for field in (
        "run_type",
        "status",
        "scientific_outcome",
        "parent_run_id",
        "linked_run_id",
        "run_id",
        "evidence_type",
        "mime_type",
        "category",
        "outcome",
        "type",
        "parent",
        "run",
    ):
        value = params.get(field)
        key = aliases.get(field, field)
        if cls is m.Artifact and key == "run_id":
            continue
        if value is not None and hasattr(cls, key):
            column = getattr(cls, key)
            clauses.append(column.is_(None) if value == "null" else column == value)
    if params.get("is_highlighted") is not None and cls is m.ResearchRun:
        if params["is_highlighted"] not in ("true", "false"):
            raise HTTPException(422, "is_highlighted 必须是 true 或 false")
        clauses.append(cls.is_highlighted.is_(params["is_highlighted"] == "true"))
    for field, operation in (
        ("date_from", "ge"),
        ("since", "ge"),
        ("date_to", "le"),
        ("until", "le"),
    ):
        if params.get(field):
            value = date_value(params[field])
            clauses.append(
                cls.created_at >= value
                if operation == "ge"
                else cls.created_at < value + timedelta(days=1)
                if len(params[field]) == 10
                else cls.created_at <= value
            )
    tag = params.get("tag_id", params.get("tag"))
    if tag:
        link = m.LINKS.get((cls.__tablename__, "tag_ids"))
        if link is None:
            raise HTTPException(422, "该集合不支持标签")
        clauses.append(
            cls.id.in_(
                select(link.c.owner_id)
                .join(m.Tag, m.Tag.id == link.c.target_id)
                .where(
                    m.Tag.id == tag,
                    m.Tag.project_id == pid,
                    *svc.visible_records(m.Tag),
                )
            )
        )
    if cls is m.Artifact and params.get("run_id", params.get("run")):
        run_id = params.get("run_id", params.get("run"))
        link = m.LINKS[("research_runs", "artifact_ids")]
        clauses.append(
            or_(
                cls.run_id == run_id,
                cls.id.in_(select(link.c.target_id).where(link.c.owner_id == run_id)),
            )
        )
    return cls, select(cls).where(*clauses)


def collection_query(db, actor, pid, kind, params):
    cls, statement = collection_statement(db, actor, pid, kind, params)
    limit, offset = pagination(params)
    sort = params.get("sort", "created_at")
    direction = params.get("direction", "desc")
    if sort not in ("created_at", "updated_at", "title") or direction not in (
        "asc",
        "desc",
    ):
        raise HTTPException(422, "排序字段或方向不正确")
    column = getattr(cls, sort, getattr(cls, "name", getattr(cls, "filename", cls.id)))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    ordered = (
        statement.order_by(
            column.asc() if direction == "asc" else column.desc(), cls.id
        )
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [svc.serialize(db, obj) for obj in db.scalars(ordered)],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def audit_statement(db, actor, params, activity=False):
    clauses = [m.AuditLog.owner_id == actor.user.id]
    pid = params.get("project_id")
    if pid:
        svc.project_for(db, actor, pid, include_trashed=True)
        clauses.append(m.AuditLog.project_id == pid)
    for key in ("actor_type", "action", "resource_type"):
        if params.get(key):
            clauses.append(getattr(m.AuditLog, key) == params[key])
    if params.get("q"):
        pattern = search_pattern(params["q"][:300])
        clauses.append(
            or_(
                *(
                    getattr(m.AuditLog, f).ilike(pattern, escape="\\")
                    for f in ("actor", "action", "resource_type", "resource_id")
                )
            )
        )
    period = params.get("range", "all")
    if period not in {"7", "30", "90", "all"}:
        raise HTTPException(422, "时间范围必须是 7、30、90 或 all")
    if period != "all":
        clauses.append(m.AuditLog.timestamp >= m.now() - timedelta(days=int(period)))
    if params.get("since"):
        clauses.append(m.AuditLog.timestamp >= date_value(params["since"]))
    if activity:
        global_pref = db.scalar(
            select(m.ActivityPreference).where(
                m.ActivityPreference.owner_id == actor.user.id,
                m.ActivityPreference.scope == "",
            )
        )
        if global_pref:
            clauses.append(m.AuditLog.timestamp > global_pref.hide_before)
        hidden = (
            select(m.ActivityPreference.id)
            .where(
                m.ActivityPreference.owner_id == actor.user.id,
                m.ActivityPreference.scope == m.AuditLog.project_id,
                m.ActivityPreference.hide_before >= m.AuditLog.timestamp,
            )
            .exists()
        )
        clauses.append(~hidden)
    return select(m.AuditLog).where(*clauses)


def audit_query(db, actor, params, activity=False):
    statement = audit_statement(db, actor, params, activity)
    limit, offset = pagination(params)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    return {
        "items": [
            svc.serialize(db, obj)
            for obj in db.scalars(
                statement.order_by(m.AuditLog.timestamp.desc(), m.AuditLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def set_highlight(db, actor, request, rid, payload):
    if (actor.token or actor.actor_type != "human") and not payload.user_requested:
        raise HTTPException(403, "AI 星标操作必须来自用户显式请求")
    run = svc.resource(db, actor, m.ResearchRun, rid, write=True)
    before = svc.serialize(db, run)
    run.is_highlighted = payload.is_highlighted
    run.highlight_type = payload.type if payload.is_highlighted else None
    run.highlight_note = payload.note if payload.is_highlighted else ""
    run.highlighted_at = m.now() if payload.is_highlighted else None
    run.highlighted_by = actor.user.id if payload.is_highlighted else None
    db.flush()
    svc.audit(db, actor, request, "set_run_highlight", run, before)
    return run


def clone_run(db, actor, request, rid, payload, modules):
    parent = svc.resource(db, actor, m.ResearchRun, rid, write=True)
    data = {
        "title": payload.title,
        "run_type": payload.run_type or parent.run_type,
        "objective": parent.objective
        if payload.objective is None
        else payload.objective,
        "parent_run_id": parent.id,
        "hypothesis": parent.hypothesis,
        "artifact_ids": [str(x) for x in payload.artifact_ids],
    }
    for flag, field in (
        ("inherit_protocol", "protocol"),
        ("inherit_environment", "environment"),
        ("inherit_software", "software_version"),
        ("inherit_code", "code_revision"),
    ):
        if getattr(payload, flag):
            data[field] = getattr(parent, field)
    allowed_context = set()
    if payload.inherit_code:
        for field in (
            "repository",
            "branch",
            "commit_sha",
            "issue_url",
            "pull_request_url",
        ):
            data[field] = getattr(parent, field)
        allowed_context.update({"repository", "branch", "commit", "config"})
    if payload.inherit_environment:
        allowed_context.add("environment_conditions")
    context = {
        key: copy.deepcopy(value)
        for key, value in parent.context_data.items()
        if key in allowed_context
    }
    if data["run_type"] == parent.run_type:
        data["context_data"] = context
    run = svc.create_record(
        db, actor, request, "runs", parent.project_id, data, modules
    )
    if payload.inherit_parameters:
        for parameter in db.scalars(
            select(m.Parameter).where(
                m.Parameter.run_id == parent.id, *svc.visible_records(m.Parameter)
            )
        ):
            inherited = {
                key: svc.serialize(db, parameter)[key]
                for key in SCHEMAS["parameters"].model_fields
            }
            inherited["is_confirmed"] = False
            svc.create_record(
                db,
                actor,
                request,
                "parameters",
                parent.project_id,
                inherited,
                modules,
                run.id,
            )
    svc.audit(db, actor, request, "clone_run", run, {"parent_run_id": parent.id})
    return run


def upsert_values(db, actor, request, rid, kind, items, modules):
    run = svc.resource(db, actor, m.ResearchRun, rid, write=True)
    names = [item.name for item in items]
    if len(names) != len(set(names)):
        raise HTTPException(422, "批量输入不能包含重复名称")
    cls = m.Parameter if kind == "parameters" else m.Metric
    result = []
    for item in items:
        data = item.model_dump(mode="json")
        existing = list(
            db.scalars(
                select(cls)
                .where(
                    cls.run_id == rid, cls.name == item.name, *svc.visible_records(cls)
                )
                .with_for_update()
            )
        )
        if len(existing) > 1:
            raise HTTPException(409, "存在重复名称的旧记录，请先整理后再批量更新")
        if existing:
            obj = existing[0]
            svc.scientific_authority(actor, kind, data, obj)
            before = svc.serialize(db, obj)
            svc.validate_links(db, obj, data, modules)
            svc.apply_data(db, obj, data)
            svc.audit(db, actor, request, "upsert_" + kind, obj, before)
        else:
            obj = svc.create_record(
                db, actor, request, kind, run.project_id, data, modules, run.id
            )
        result.append(svc.serialize(db, obj))
    return result


def project_summary(db, actor, pid):
    project = svc.project_for(db, actor, pid)
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
        "highlighted_runs": collection_query(
            db, actor, pid, "runs", {"limit": "5", "is_highlighted": "true"}
        )["items"],
        "recent_runs": collection_query(db, actor, pid, "runs", {"limit": "5"})[
            "items"
        ],
        "current_tasks": [
            svc.serialize(db, task)
            for task in db.scalars(
                select(m.Task)
                .where(
                    m.Task.project_id == pid,
                    m.Task.status != "done",
                    *svc.visible_records(m.Task),
                )
                .order_by(m.Task.created_at.desc())
                .limit(5)
            )
        ],
        "current_gates": collection_query(
            db, actor, pid, "gates", {"limit": "20", "direction": "asc"}
        )["items"],
        "current_risks": collection_query(
            db, actor, pid, "risks", {"limit": "5", "status": "open"}
        )["items"],
        "current_decisions": collection_query(
            db, actor, pid, "decisions", {"limit": "5"}
        )["items"],
        "evidence_summary": evidence_summary,
    }


def install_workflow(app, actor_dep, db_dep, objects):
    @app.get("/api/capabilities")
    def capabilities(actor=Depends(actor_dep)):
        return CAPABILITIES

    @app.get("/api/projects/{pid}/summary")
    def summary(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        if request.query_params.get("format") == "page":
            from .connected import summary_page

            return summary_page(db, actor, str(pid), dict(request.query_params))
        return project_summary(db, actor, str(pid))

    @app.get("/api/projects/{pid}/{kind}/query")
    def query(
        pid: UUID,
        kind: str,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        return collection_query(db, actor, str(pid), kind, dict(request.query_params))

    @app.patch("/api/runs/{rid}/highlight")
    def highlight(
        rid: UUID,
        payload: HighlightInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        run = set_highlight(db, actor, request, str(rid), payload)
        db.commit()
        return svc.serialize(db, run)

    @app.post("/api/runs/{rid}/clone")
    def clone(
        rid: UUID,
        payload: CloneInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        run = clone_run(db, actor, request, str(rid), payload, app.state.modules)
        db.commit()
        return svc.serialize(db, run)

    @app.post("/api/runs/{rid}/parameters/batch")
    def parameters_batch(
        rid: UUID,
        payload: ParametersBatch,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        result = upsert_values(
            db,
            actor,
            request,
            str(rid),
            "parameters",
            payload.parameters,
            app.state.modules,
        )
        db.commit()
        return result

    @app.patch("/api/artifacts/{aid}")
    def tag_artifact(
        aid: UUID,
        request: Request,
        payload: TaggedInput,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        data = payload.model_dump(mode="json")
        obj = svc.resource(db, actor, m.Artifact, str(aid), write=True)
        before = svc.serialize(db, obj)
        svc.validate_links(db, obj, data, app.state.modules)
        svc.apply_data(db, obj, data)
        svc.audit(db, actor, request, "tag_artifact", obj, before)
        db.commit()
        return svc.serialize(db, obj)

    @app.get("/api/audit")
    def audit(
        request: Request,
        response: Response,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        page = audit_query(db, actor, dict(request.query_params))
        response.headers["X-Total-Count"] = str(page["total"])
        return page if request.query_params.get("format") == "page" else page["items"]

    @app.get("/api/projects/{pid}/audit")
    def project_audit(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return audit_query(
            db, actor, {**dict(request.query_params), "project_id": str(pid)}
        )

    @app.post("/api/activity/clear")
    def clear_activity(
        payload: ActivityClearInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.require_human(actor)
        scope = str(payload.project_id) if payload.project_id else ""
        if scope:
            svc.project_for(db, actor, scope, write=True)
        else:
            db.scalar(
                select(m.User).where(m.User.id == actor.user.id).with_for_update()
            )
        preference = db.scalar(
            select(m.ActivityPreference)
            .where(
                m.ActivityPreference.owner_id == actor.user.id,
                m.ActivityPreference.scope == scope,
            )
            .with_for_update()
        )
        before = svc.serialize(db, preference) if preference else None
        if preference is None:
            preference = m.ActivityPreference(owner_id=actor.user.id, scope=scope)
            db.add(preference)
        preference.hide_before = m.now()
        db.flush()
        svc.audit(db, actor, request, "clear_activity_display", preference, before)
        db.commit()
        return {
            "ok": True,
            "project_id": scope or None,
            "hide_before": preference.hide_before,
        }

    @app.get("/api/search")
    def search(request: Request, actor=Depends(actor_dep), db=Depends(db_dep)):
        params = dict(request.query_params)
        limit, offset = pagination(params)
        q = params.get("q", "").strip()
        if not q:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        statements = []
        selected = params.get("kind")
        for kind, cls in QUERY_COLLECTIONS.items():
            if selected and selected != kind:
                continue
            label = getattr(
                cls, "title", getattr(cls, "name", getattr(cls, "filename", cls.id))
            )
            conditions = [
                m.Project.owner_id == actor.user.id,
                *svc.visible_records(m.Project),
                m.Project.status != "archived",
                *svc.visible_records(cls),
                text_filter(cls, q[:300]),
            ]
            if params.get("project_id"):
                svc.project_for(db, actor, params["project_id"])
                conditions.append(cls.project_id == params["project_id"])
            statements.append(
                select(
                    literal(kind).label("kind"),
                    cls.id.label("id"),
                    cls.project_id.label("project_id"),
                    label.label("title"),
                    cls.created_at.label("created_at"),
                )
                .join(m.Project, m.Project.id == cls.project_id)
                .where(*conditions)
            )
        if not statements:
            raise HTTPException(422, "未知搜索集合")
        combined = union_all(*statements).subquery()
        total = db.scalar(select(func.count()).select_from(combined))
        rows = (
            db.execute(
                select(combined)
                .order_by(combined.c.created_at.desc(), combined.c.id)
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    from .bundles import install_bundle_routes

    install_bundle_routes(app, actor_dep, db_dep, objects)
