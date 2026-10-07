# FastAPI dependency and field declarations intentionally use call defaults.
# ruff: noqa: B008
import copy
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import timedelta, timezone
from types import SimpleNamespace
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from . import models as m
from . import service as svc
from .middleware import BodyLimitMiddleware
from .modules import load_modules
from .schemas import (
    SCHEMAS,
    AuthInput,
    LifecycleInput,
    MetricsBatch,
    ModuleUpgradeInput,
    PurgeInput,
    StorageGCInput,
    TokenInput,
)
from .security import LoginAttempts
from .storage import ALLOWED_ARTIFACT_TYPES, S3Objects, artifact_signature_valid


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + result.hex()


def password_valid(password, stored):
    try:
        _, salt, value = stored.split("$")
        return hmac.compare_digest(
            hashlib.scrypt(
                password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
            ).hex(),
            value,
        )
    except (ValueError, TypeError):
        return False


def create_app(database_url=None, initialize=False):
    app = FastAPI(title="Research Hub", version="0.2.0")
    url = database_url or os.getenv(
        "DATABASE_URL", "postgresql+psycopg://localhost/researchhub"
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            from .intelligence import sqlite_json_equal

            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function(
                "researchhub_json_equal", 2, sqlite_json_equal, deterministic=True
            )

    if initialize:
        if not url.startswith("sqlite"):
            raise ValueError(
                "initialize is restricted to isolated SQLite unit tests; use Alembic in production"
            )
        m.Base.metadata.create_all(engine)
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.modules = load_modules()
    app.state.objects = None
    app.state.login_attempts = LoginAttempts()
    origins = [
        x.strip()
        for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if x.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def headers(request, call_next):
        request.state.request_id = secrets.token_hex(16)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def db_dep():
        with app.state.session_factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    def actor_dep(request: Request, db=Depends(db_dep)):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = db.scalar(
                select(m.ApiToken).where(
                    m.ApiToken.digest == digest(auth[7:]), m.ApiToken.revoked.is_(False)
                )
            )
            if not token:
                raise HTTPException(401, "Invalid API token")
            needed = (
                "research:read"
                if request.method in ("GET", "HEAD")
                else "research:write"
            )
            if needed not in token.scopes:
                raise HTTPException(403, "Token scope does not allow this action")
            return SimpleNamespace(
                user=db.get(m.User, token.user_id),
                token=token,
                actor_type=token.actor_type,
            )
        cookie = request.cookies.get("rh_session")
        session = (
            db.scalar(select(m.Session).where(m.Session.digest == digest(cookie)))
            if cookie
            else None
        )
        if not session:
            raise HTTPException(401, "Authentication required")
        expiry = (
            session.expires_at
            if session.expires_at.tzinfo
            else session.expires_at.replace(tzinfo=timezone.utc)
        )
        if expiry < m.now():
            raise HTTPException(401, "Authentication required")
        if request.method not in ("GET", "HEAD") and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session.csrf_token
        ):
            raise HTTPException(403, "CSRF token required")
        return SimpleNamespace(
            user=db.get(m.User, session.user_id),
            token=None,
            session=session,
            actor_type="human",
        )

    def human(actor):
        if actor.token:
            raise HTTPException(
                403, "Human session required for account administration"
            )

    def login_response(db, user, response):
        secret = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        db.add(
            m.Session(
                user_id=user.id,
                digest=digest(secret),
                csrf_token=csrf,
                expires_at=m.now() + timedelta(days=7),
            )
        )
        db.commit()
        response.set_cookie(
            "rh_session",
            secret,
            httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="lax",
            max_age=604800,
            path="/",
        )
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
            },
            "csrf_token": csrf,
        }

    @app.get("/api/health")
    def health(db=Depends(db_dep)):
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "postgresql"
            if engine.dialect.name == "postgresql"
            else "sqlite-unit-test",
            "version": "0.2.0",
        }

    @app.get("/api/auth/status")
    def status(db=Depends(db_dep)):
        return {"setup_required": db.scalar(select(m.User.id).limit(1)) is None}

    @app.post("/api/auth/setup")
    def setup(payload: AuthInput, response: Response, db=Depends(db_dep)):
        if db.scalar(select(m.User.id).limit(1)):
            raise HTTPException(409, "Account already initialized")
        user = m.User(
            email=payload.email.lower(),
            password_hash=password_hash(payload.password),
            display_name=payload.display_name,
            bootstrap_key="first_admin",
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Account already initialized")
        return login_response(db, user, response)

    @app.post("/api/auth/login")
    def login(
        payload: AuthInput, response: Response, request: Request, db=Depends(db_dep)
    ):
        peer = request.client.host if request.client else "unknown"
        app.state.login_attempts.begin(peer)
        user = db.scalar(select(m.User).where(m.User.email == payload.email.lower()))
        if not user or not password_valid(payload.password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
        app.state.login_attempts.success(peer)
        return login_response(db, user, response)

    @app.get("/api/auth/me")
    def me(actor=Depends(actor_dep)):
        return {
            "user": {
                "id": actor.user.id,
                "email": actor.user.email,
                "display_name": actor.user.display_name,
            },
            "csrf_token": actor.session.csrf_token if not actor.token else None,
        }

    @app.post("/api/auth/logout")
    def logout(response: Response, actor=Depends(actor_dep), db=Depends(db_dep)):
        human(actor)
        db.delete(actor.session)
        db.commit()
        response.delete_cookie("rh_session", path="/")
        return {"ok": True}

    @app.get("/api/auth/tokens")
    def tokens(actor=Depends(actor_dep), db=Depends(db_dep)):
        human(actor)
        return [
            {
                k: v
                for k, v in svc.serialize(db, t).items()
                if k not in ("digest", "user_id")
            }
            for t in db.scalars(
                select(m.ApiToken).where(m.ApiToken.user_id == actor.user.id)
            )
        ]

    @app.post("/api/auth/tokens")
    def issue_token(
        payload: TokenInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        human(actor)
        secret = "rh_" + secrets.token_urlsafe(48)
        t = m.ApiToken(
            user_id=actor.user.id, digest=digest(secret), **payload.model_dump()
        )
        db.add(t)
        db.flush()
        db.add(
            m.AuditLog(
                owner_id=actor.user.id,
                actor=actor.user.email,
                actor_type="human",
                action="issue_api_token",
                resource_type="api_tokens",
                resource_id=t.id,
                before=None,
                after={"name": t.name, "scopes": t.scopes, "actor_type": t.actor_type},
                source="web",
                request_id=request.state.request_id,
            )
        )
        db.commit()
        return {
            "id": t.id,
            "name": t.name,
            "scopes": t.scopes,
            "actor_type": t.actor_type,
            "token": secret,
        }

    @app.delete("/api/auth/tokens/{tid}")
    def revoke(
        tid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        human(actor)
        t = db.get(m.ApiToken, str(tid))
        if not t or t.user_id != actor.user.id:
            raise HTTPException(404, "Token not found")
        t.revoked = True
        db.add(
            m.AuditLog(
                owner_id=actor.user.id,
                actor=actor.user.email,
                actor_type="human",
                action="revoke_api_token",
                resource_type="api_tokens",
                resource_id=t.id,
                source="web",
                request_id=request.state.request_id,
            )
        )
        db.commit()
        return {"ok": True}

    @app.get("/api/modules")
    def modules(actor=Depends(actor_dep)):
        return list(app.state.modules.values())

    @app.get("/api/modules/{mid}")
    def module(mid: str, actor=Depends(actor_dep)):
        if mid not in app.state.modules:
            raise HTTPException(404, "Module not found")
        return app.state.modules[mid]

    @app.get("/api/projects")
    def projects(
        include_archived: bool = False, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        return [
            svc.serialize(db, p)
            for p in db.scalars(
                select(m.Project)
                .where(
                    m.Project.owner_id == actor.user.id,
                    m.Project.trashed_at.is_(None),
                    *(
                        []
                        if include_archived
                        else [
                            m.Project.archived_at.is_(None),
                            m.Project.status != "archived",
                        ]
                    ),
                )
                .order_by(m.Project.updated_at.desc())
            )
        ]

    def make_project(db, actor, request, payload, is_demo=False):
        data = svc.parsed("projects", payload)
        initially_archived = data["status"] == "archived"
        if initially_archived:
            svc.require_human(actor)
            data["status"] = "active"
        module = app.state.modules.get(data["module_id"])
        if not module:
            raise HTTPException(422, "Unknown module")
        if data["current_stage"] and data["current_stage"] not in {
            s["id"] for s in module["research_stages"]
        }:
            raise HTTPException(422, "Unknown stage")
        from .modules import CAPABILITY_IDS

        if data["enabled_capabilities"] is None:
            data["enabled_capabilities"] = module.get("default_capabilities", [])
        if (
            len(set(data["enabled_capabilities"])) != len(data["enabled_capabilities"])
            or not set(data["enabled_capabilities"]) <= CAPABILITY_IDS
        ):
            raise HTTPException(422, "Unknown or duplicate capability")
        p = m.Project(
            owner_id=actor.user.id,
            is_demo=is_demo,
            module_version=module["version"],
            module_snapshot=copy.deepcopy(module),
            **data,
        )
        db.add(p)
        db.flush()
        svc.audit(db, actor, request, "create_project", p)
        for g in module["stage_gates"]:
            svc.create_record(
                db,
                actor,
                request,
                "gates",
                p.id,
                {
                    "gate_id": g["id"],
                    "stage_id": g["stage_id"],
                    "name": g["name"],
                    "description": g["description"],
                    "criteria": [
                        {**c, "status": "not_started", "evidence_ids": []}
                        for c in g["criteria"]
                    ],
                },
                app.state.modules,
            )
        if initially_archived:
            before = svc.serialize(db, p)
            p.status = "archived"
            p.archived_at = m.now()
            db.flush()
            svc.audit(db, actor, request, "archive_projects", p, before)
        return p

    @app.post("/api/projects")
    def create_project(
        request: Request,
        payload: dict = Body(...),
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        p = make_project(db, actor, request, payload)
        db.commit()
        return svc.serialize(db, p)

    @app.get("/api/projects/{pid}/context")
    def context(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        from .workflow import positive_int

        selected = request.query_params.get("collections")
        selected = selected.split(",") if selected is not None else None
        if selected is not None and not set(selected) <= {
            *m.COLLECTIONS,
            "artifacts",
            "activity",
        }:
            raise HTTPException(422, "Unknown context collection")
        limit = positive_int(request.query_params.get("limit"), 100, 100)
        if limit == 0:
            raise HTTPException(422, "limit must be positive")
        return svc.project_context(
            db, actor, str(pid), app.state.modules, selected, limit
        )

    @app.get("/api/projects/{pid}")
    def get_project(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        return svc.serialize(db, svc.project_for(db, actor, str(pid)))

    @app.patch("/api/projects/{pid}")
    def patch_project(
        pid: UUID,
        request: Request,
        payload: dict = Body(...),
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        p = svc.project_for(db, actor, str(pid), write=True)
        before = svc.serialize(db, p)
        if payload.get("status") == "archived":
            svc.require_human(actor)
        if "module_id" in payload and payload["module_id"] != p.module_id:
            raise HTTPException(422, "Project module cannot change after creation")
        data = svc.parsed(
            "projects",
            {**{k: before[k] for k in SCHEMAS["projects"].model_fields}, **payload},
        )
        from .modules import CAPABILITY_IDS

        if (
            data["enabled_capabilities"] is None
            or len(set(data["enabled_capabilities"]))
            != len(data["enabled_capabilities"])
            or not set(data["enabled_capabilities"]) <= CAPABILITY_IDS
        ):
            raise HTTPException(422, "Unknown or duplicate capability")
        if data["current_stage"] and data["current_stage"] not in {
            s["id"] for s in svc.module_for(p)["research_stages"]
        }:
            raise HTTPException(422, "Unknown stage")
        svc.apply_data(db, p, data)
        if data["status"] == "archived" and p.archived_at is None:
            p.archived_at = m.now()
            db.flush()
        svc.audit(db, actor, request, "update_project", p, before)
        db.commit()
        return svc.serialize(db, p)

    @app.delete("/api/projects/{pid}")
    def delete_project(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        svc.lifecycle(db, actor, request, "projects", str(pid), "trash")
        db.commit()
        return {"ok": True}

    @app.get("/api/activity")
    def activity(
        request: Request,
        response: Response,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        from .workflow import audit_query

        page = audit_query(db, actor, dict(request.query_params), activity=True)
        response.headers["X-Total-Count"] = str(page["total"])
        return page if request.query_params.get("format") == "page" else page["items"]

    @app.get("/api/tasks")
    def all_tasks(
        request: Request,
        response: Response,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        from .workflow import pagination, text_filter

        params = dict(request.query_params)
        limit, offset = pagination(params)
        clauses = [
            m.Project.owner_id == actor.user.id,
            *svc.visible_records(m.Project),
            *svc.visible_records(m.Task),
        ]
        if params.get("project_id"):
            svc.project_for(db, actor, params["project_id"])
            clauses.append(m.Task.project_id == params["project_id"])
        if params.get("status"):
            clauses.append(m.Task.status == params["status"])
        if params.get("exclude_status"):
            clauses.append(m.Task.status != params["exclude_status"])
        if params.get("q"):
            clauses.append(text_filter(m.Task, params["q"][:300]))
        statement = select(m.Task).join(m.Project).where(*clauses)
        total = db.scalar(select(func.count()).select_from(statement.subquery()))
        items = [
            svc.serialize(db, obj)
            for obj in db.scalars(
                statement.order_by(m.Task.created_at.desc(), m.Task.id)
                .limit(limit)
                .offset(offset)
            )
        ]
        response.headers["X-Total-Count"] = str(total)
        return (
            {"items": items, "total": total, "limit": limit, "offset": offset}
            if params.get("format") == "page"
            else items
        )

    @app.get("/api/runs/{rid}/context")
    def run_context(rid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        return svc.run_context(db, actor, str(rid))

    def add_collection(kind, cls):
        def list_records(
            pid: UUID,
            request: Request,
            response: Response,
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            from .workflow import collection_query

            page = collection_query(
                db, actor, str(pid), kind, dict(request.query_params)
            )
            response.headers["X-Total-Count"] = str(page["total"])
            return page["items"]

        def create_record(
            pid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            svc.project_for(db, actor, str(pid), write=True)
            obj = svc.create_record(
                db, actor, request, kind, str(pid), payload, app.state.modules
            )
            db.commit()
            return svc.serialize(db, obj)

        def get_record(rid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
            return svc.serialize(db, svc.resource(db, actor, cls, str(rid)))

        def patch_record(
            rid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            obj = svc.resource(db, actor, cls, str(rid), write=True)
            before = svc.serialize(db, obj)
            svc.scientific_authority(actor, kind, payload, existing=obj)
            if isinstance(obj, m.ResearchRun) and isinstance(
                payload.get("context_data"), dict
            ):
                payload = {
                    **payload,
                    "context_data": {
                        **before["context_data"],
                        **payload["context_data"],
                    },
                }
            data = svc.parsed(
                kind, {**{k: before[k] for k in SCHEMAS[kind].model_fields}, **payload}
            )
            svc.scientific_authority(
                actor, kind, {key: data[key] for key in payload}, existing=obj
            )
            svc.validate_links(db, obj, data, app.state.modules)
            dependents = (
                svc.evidence_dependents(db, obj)
                if isinstance(obj, m.Evidence)
                and "status" in payload
                and data["status"] in svc.INSUFFICIENT_EVIDENCE_STATUSES
                else []
            )
            svc.apply_data(db, obj, data)
            svc.audit(db, actor, request, "update_" + kind, obj, before)
            if dependents:
                svc.reconcile_evidence_dependents(
                    db,
                    actor,
                    request,
                    dependents,
                    obj.id,
                    f"状态已变为 {obj.status}",
                )
            db.commit()
            return svc.serialize(db, obj)

        def delete_record(
            rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
        ):
            svc.lifecycle(db, actor, request, kind, str(rid), "trash")
            db.commit()
            return {"ok": True}

        app.add_api_route(
            "/api/projects/{pid}/" + kind,
            list_records,
            methods=["GET"],
            name="list_" + kind,
        )
        app.add_api_route(
            "/api/projects/{pid}/" + kind,
            create_record,
            methods=["POST"],
            name="create_" + kind,
        )
        app.add_api_route(
            "/api/" + kind + "/{rid}", get_record, methods=["GET"], name="get_" + kind
        )
        app.add_api_route(
            "/api/" + kind + "/{rid}",
            patch_record,
            methods=["PATCH"],
            name="patch_" + kind,
        )
        app.add_api_route(
            "/api/" + kind + "/{rid}",
            delete_record,
            methods=["DELETE"],
            name="delete_" + kind,
        )

    for kind, cls in m.COLLECTIONS.items():
        add_collection(kind, cls)

    def add_run_values(kind, cls):
        def listing(
            rid: UUID,
            request: Request,
            response: Response,
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            from .intelligence import run_values

            return run_values(
                db, actor, str(rid), kind, dict(request.query_params), response
            )

        def creating(
            rid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            r = svc.resource(db, actor, m.ResearchRun, str(rid), write=True)
            obj = svc.create_record(
                db,
                actor,
                request,
                kind,
                r.project_id,
                payload,
                app.state.modules,
                str(rid),
            )
            db.commit()
            return svc.serialize(db, obj)

        def patching(
            rid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            obj = svc.resource(db, actor, cls, str(rid), write=True)
            before = svc.serialize(db, obj)
            svc.scientific_authority(actor, kind, payload, existing=obj)
            data = svc.parsed(
                kind, {**{k: before[k] for k in SCHEMAS[kind].model_fields}, **payload}
            )
            svc.scientific_authority(
                actor, kind, {key: data[key] for key in payload}, existing=obj
            )
            svc.validate_links(db, obj, data, app.state.modules)
            svc.apply_data(db, obj, data)
            svc.audit(db, actor, request, "update_" + kind, obj, before)
            db.commit()
            return svc.serialize(db, obj)

        def deleting(
            rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
        ):
            svc.lifecycle(db, actor, request, kind, str(rid), "trash")
            db.commit()
            return {"ok": True}

        app.add_api_route(
            "/api/runs/{rid}/" + kind, listing, methods=["GET"], name="list_" + kind
        )
        app.add_api_route(
            "/api/runs/{rid}/" + kind, creating, methods=["POST"], name="create_" + kind
        )
        app.add_api_route(
            "/api/" + kind + "/{rid}", patching, methods=["PATCH"], name="patch_" + kind
        )
        app.add_api_route(
            "/api/" + kind + "/{rid}",
            deleting,
            methods=["DELETE"],
            name="delete_" + kind,
        )

    add_run_values("parameters", m.Parameter)
    add_run_values("metrics", m.Metric)

    @app.post("/api/runs/{rid}/metrics/batch")
    def metrics_batch(
        rid: UUID,
        request: Request,
        payload: MetricsBatch,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        r = svc.resource(db, actor, m.ResearchRun, str(rid), write=True)
        from .workflow import upsert_values

        objs = upsert_values(
            db, actor, request, r.id, "metrics", payload.metrics, app.state.modules
        )
        db.commit()
        return objs

    def objects():
        if app.state.objects is None:
            app.state.objects = S3Objects()
        return app.state.objects

    @app.get("/api/projects/{pid}/module-upgrade/preview")
    def module_upgrade_preview(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        p = svc.project_for(db, actor, str(pid))
        return svc.module_upgrade_preview(p, app.state.modules[p.module_id])

    @app.post("/api/projects/{pid}/module-upgrade")
    def module_upgrade(
        pid: UUID,
        payload: ModuleUpgradeInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.require_human(actor)
        p = svc.project_for(db, actor, str(pid), write=True)
        # Serialize upgrade transactions so two tabs cannot silently overwrite each other.
        p = db.scalar(
            select(m.Project)
            .where(m.Project.id == p.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        svc.upgrade_module(
            db,
            actor,
            request,
            p,
            app.state.modules[p.module_id],
            payload.expected_version,
            payload.expected_target_digest,
            app.state.modules,
        )
        db.commit()
        return svc.serialize(db, p)

    @app.get("/api/lifecycle/{kind}")
    def lifecycle_listing(
        kind: str,
        state: str = "trashed",
        limit: int = 100,
        offset: int = 0,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        cls = svc.LIFECYCLE_COLLECTIONS.get(kind)
        if cls is None or state not in {"trashed", "archived"}:
            raise HTTPException(422, "Invalid lifecycle resource type or state")
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "Invalid pagination")
        query = select(cls)
        if cls is m.Project:
            query = query.where(m.Project.owner_id == actor.user.id)
        elif cls in (m.Parameter, m.Metric):
            query = (
                query.join(m.ResearchRun)
                .join(m.Project)
                .where(m.Project.owner_id == actor.user.id)
            )
        else:
            query = query.join(m.Project).where(m.Project.owner_id == actor.user.id)
        stamp = cls.trashed_at if state == "trashed" else cls.archived_at
        return [
            svc.serialize(db, obj)
            for obj in db.scalars(
                query.where(stamp.is_not(None))
                .order_by(stamp.desc(), cls.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    @app.get("/api/projects/{pid}/lifecycle")
    def project_lifecycle(
        pid: UUID,
        kind: str = "runs",
        limit: int = 100,
        offset: int = 0,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.project_for(db, actor, str(pid), include_trashed=True)
        cls = svc.LIFECYCLE_COLLECTIONS.get(kind)
        if cls is None or not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "Invalid lifecycle type or pagination")
        query = select(cls)
        if cls is m.Project:
            query = query.where(m.Project.id == str(pid))
        elif cls in (m.Parameter, m.Metric):
            query = query.join(m.ResearchRun).where(
                m.ResearchRun.project_id == str(pid)
            )
        else:
            query = query.where(cls.project_id == str(pid))
        query = (
            query.where((cls.archived_at.is_not(None)) | (cls.trashed_at.is_not(None)))
            .order_by(cls.updated_at.desc(), cls.id)
            .limit(limit)
            .offset(offset)
        )
        return [svc.serialize(db, obj) for obj in db.scalars(query)]

    @app.patch("/api/lifecycle/{kind}/{rid}")
    def change_lifecycle(
        kind: str,
        rid: UUID,
        payload: LifecycleInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        obj = svc.lifecycle(db, actor, request, kind, str(rid), payload.action)
        db.commit()
        return svc.serialize(db, obj)

    @app.post("/api/lifecycle/{kind}/{rid}/purge")
    def purge_resource(
        kind: str,
        rid: UUID,
        payload: PurgeInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.purge(db, actor, request, kind, str(rid))
        db.commit()
        return {"ok": True, "object_cleanup": "queued"}

    @app.get("/api/storage/gc-preview")
    def gc_preview(actor=Depends(actor_dep), db=Depends(db_dep)):
        svc.require_human(actor)
        items = list(
            db.scalars(
                select(m.ObjectDeletion)
                .where(
                    m.ObjectDeletion.owner_id == actor.user.id,
                    m.ObjectDeletion.status != "deleted",
                )
                .order_by(m.ObjectDeletion.created_at)
                .limit(100)
            )
        )
        return {
            "items": [
                {
                    **svc.serialize(db, item),
                    "has_live_reference": db.scalar(
                        select(m.Artifact.id)
                        .where(m.Artifact.object_key == item.object_key)
                        .limit(1)
                    )
                    is not None,
                }
                for item in items
            ],
            "limit": 100,
            "scan_bucket": False,
        }

    @app.post("/api/storage/gc")
    def storage_gc(
        payload: StorageGCInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.require_human(actor)
        items = list(
            db.scalars(
                select(m.ObjectDeletion)
                .where(
                    m.ObjectDeletion.owner_id == actor.user.id,
                    m.ObjectDeletion.object_key.in_(payload.object_keys),
                )
                .with_for_update()
            )
        )
        if {item.object_key for item in items} != set(payload.object_keys):
            raise HTTPException(
                422, "Only owned, queued object keys from GC preview may be deleted"
            )
        result = {"deleted": 0, "failed": 0, "skipped_live": 0}
        for item in items:
            if db.scalar(
                select(m.Artifact.id)
                .where(m.Artifact.object_key == item.object_key)
                .limit(1)
            ):
                result["skipped_live"] += 1
                continue
            if item.status == "deleted":
                continue
            before = svc.serialize(db, item)
            item.attempts += 1
            try:
                objects().delete(item.object_key)
                item.status = "deleted"
                item.last_error = None
                result["deleted"] += 1
            except (BotoCoreError, ClientError, ValueError, OSError):
                item.status = "failed"
                item.last_error = "object_storage_unavailable"
                result["failed"] += 1
            db.flush()
            svc.audit(db, actor, request, "storage_gc_" + item.status, item, before)
        db.commit()
        return result

    @app.get("/api/projects/{pid}/artifacts")
    def artifacts(
        pid: UUID,
        request: Request,
        response: Response,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        from .workflow import collection_query

        page = collection_query(
            db, actor, str(pid), "artifacts", dict(request.query_params)
        )
        response.headers["X-Total-Count"] = str(page["total"])
        return page["items"]

    @app.post("/api/projects/{pid}/artifacts")
    def upload(
        pid: UUID,
        request: Request,
        file: UploadFile = File(...),
        run_id: str | None = Form(None),
        category: str = Form("data"),
        metadata: str = Form("{}"),
        checksum: str | None = Form(None),
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        p = svc.project_for(db, actor, str(pid), write=True)
        svc.reference(db, m.ResearchRun, run_id, p.id)
        if run_id:
            svc.resource(db, actor, m.ResearchRun, run_id, write=True)
        filename = file.filename or ""
        if (
            not filename
            or len(filename) > 255
            or any(c in filename for c in ("/", "\\", "\x00", "\r", "\n"))
        ):
            raise HTTPException(422, "Invalid filename")
        ext = filename.rsplit(".", 1)[-1].lower()
        allowed = ALLOWED_ARTIFACT_TYPES
        mime = file.content_type or "application/octet-stream"
        if ext not in allowed or mime not in allowed[ext]:
            raise HTTPException(422, "Unsupported extension or MIME type")
        if category not in svc.module_for(p)["artifact_categories"]:
            raise HTTPException(422, "Unknown artifact category")
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(422, "Invalid metadata JSON")
        if not isinstance(meta, dict) or len(metadata) > 65536:
            raise HTTPException(422, "Metadata must be a small JSON object")
        size = 0
        hash_ = hashlib.sha256()
        limit = int(os.getenv("MAX_UPLOAD_BYTES", "52428800"))
        with tempfile.SpooledTemporaryFile(max_size=1048576) as stream:
            while chunk := file.file.read(65536):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Upload exceeds configured limit")
                hash_.update(chunk)
                stream.write(chunk)
            if not size:
                raise HTTPException(422, "Empty files are not accepted")
            computed = hash_.hexdigest()
            if checksum and not hmac.compare_digest(checksum.lower(), computed):
                raise HTTPException(422, "Checksum mismatch")
            stream.seek(0)
            prefix = stream.read(65536)
            stream.seek(0)
            if not artifact_signature_valid(ext, prefix):
                raise HTTPException(422, "File content does not match declared type")
            aid = m.uid()
            key = f"{actor.user.id}/{p.id}/{aid}"
            try:
                objects().put(key, stream, size, mime)
            except (BotoCoreError, ClientError, ValueError, OSError):
                # The store may have persisted bytes before a timeout/lost reply.
                # Persist intent before returning 503; GC rechecks live references.
                db.rollback()
                svc.enqueue_object_deletion(db, actor.user.id, p.id, key)
                db.commit()
                raise HTTPException(503, "Object storage is unavailable")
        artifact = m.Artifact(
            id=aid,
            project_id=p.id,
            run_id=run_id,
            filename=filename,
            mime_type=mime,
            size=size,
            checksum=computed,
            object_key=key,
            category=category,
            artifact_metadata=meta,
            created_by=actor.user.id,
        )
        try:
            db.add(artifact)
            db.flush()
            svc.audit(db, actor, request, "upload_artifact", artifact)
            db.commit()
        except Exception:
            db.rollback()
            # Persist an orphan cleanup intent independently of the failed metadata transaction.
            # GC will recheck that no live metadata refers to this exact key.
            svc.enqueue_object_deletion(db, actor.user.id, p.id, key)
            db.commit()
            raise
        return svc.serialize(db, artifact)

    @app.get("/api/artifacts/{aid}/download")
    def download(aid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        a = svc.resource(db, actor, m.Artifact, str(aid))
        try:
            body = objects().get(a.object_key)
        except (BotoCoreError, ClientError, ValueError, OSError):
            raise HTTPException(503, "Object storage is unavailable")

        def chunks():
            try:
                while chunk := body.read(65536):
                    yield chunk
            finally:
                body.close()

        return StreamingResponse(
            chunks(),
            media_type=a.mime_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.filename)}",
                "Content-Length": str(a.size),
                "X-Checksum-SHA256": a.checksum,
            },
        )

    @app.get("/api/artifacts/{aid}")
    def artifact_metadata(aid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        return svc.serialize(db, svc.resource(db, actor, m.Artifact, str(aid)))

    @app.delete("/api/artifacts/{aid}")
    def delete_artifact(
        aid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        svc.lifecycle(db, actor, request, "artifacts", str(aid), "trash")
        db.commit()
        return {"ok": True}

    @app.post("/api/demo/seed")
    def seed(request: Request, actor=Depends(actor_dep), db=Depends(db_dep)):
        human(actor)
        existing = {
            p.module_id
            for p in db.scalars(
                select(m.Project).where(
                    m.Project.owner_id == actor.user.id, m.Project.is_demo.is_(True)
                )
            )
        }
        for mid, module in app.state.modules.items():
            if mid in existing:
                continue
            p = make_project(
                db,
                actor,
                request,
                {
                    "name": "演示 / 合成数据（DEMO / SYNTHETIC）" + module["name"],
                    "description": "界面演示数据，不代表真实科研结果。",
                    "module_id": mid,
                    "current_stage": module["research_stages"][0]["id"],
                    "current_objective": "验证工作流；所有结果均为合成数据。",
                },
                True,
            )
            first = None
            for i in range(2):
                r = svc.create_record(
                    db,
                    actor,
                    request,
                    "runs",
                    p.id,
                    {
                        "title": f"演示研究记录 {i + 1}（DEMO / SYNTHETIC）",
                        "run_type": module["run_types"][0]["id"],
                        "status": "completed",
                        "parent_run_id": first,
                        "observation": "合成数据演示观察",
                        "ai_analysis": "演示 AI 分析，未经验证。",
                        "human_conclusion": "演示数据不得作为真实结论。",
                        "scientific_outcome": "negative_result" if i else "unknown",
                    },
                    app.state.modules,
                )
                first = r.id
                svc.create_record(
                    db,
                    actor,
                    request,
                    "parameters",
                    p.id,
                    {
                        "name": module["parameter_schemas"][0]["id"]
                        if module["parameter_schemas"]
                        else "demo_parameter",
                        "value": None,
                        "source_kind": "unknown",
                    },
                    app.state.modules,
                    r.id,
                )
                svc.create_record(
                    db,
                    actor,
                    request,
                    "metrics",
                    p.id,
                    {
                        "name": module["metric_schemas"][0]["id"]
                        if module["metric_schemas"]
                        else "demo_score",
                        "value": 0.5 + i * 0.1,
                        "status": "synthetic",
                    },
                    app.state.modules,
                    r.id,
                )
            e = svc.create_record(
                db,
                actor,
                request,
                "evidence",
                p.id,
                {
                    "title": "演示证据（DEMO / SYNTHETIC）",
                    "status": "synthetic",
                    "linked_run_id": first,
                    "limitations": "仅用于界面演示，不支持现实世界结论。",
                },
                app.state.modules,
            )
            svc.create_record(
                db,
                actor,
                request,
                "tasks",
                p.id,
                {"title": "DEMO 核验来源与未知参数"},
                app.state.modules,
            )
            svc.create_record(
                db,
                actor,
                request,
                "notes",
                p.id,
                {
                    "title": "DEMO 演示说明",
                    "content": "请创建真实项目；演示数据不会自动混入真实课题。",
                },
                app.state.modules,
            )
            if mid == "ice-sonocuring":
                for g in db.scalars(select(m.Gate).where(m.Gate.project_id == p.id)):
                    if g.gate_id == "G0":
                        data = svc.serialize(db, g)
                        g.status = "passed"
                        svc.apply_data(
                            db,
                            g,
                            {
                                "evidence_ids": [e.id],
                                "criteria": [
                                    {**c, "status": "passed", "evidence_ids": [e.id]}
                                    for c in data["criteria"]
                                ],
                            },
                        )
                    elif g.gate_id == "G1":
                        g.status = "in_progress"
                    elif g.gate_id == "G2":
                        g.status = "blocked"
                        g.blocking_reason = (
                            "DEMO：数值可信度待核验，尚无真实受控比较证据。"
                        )
                    svc.audit(db, actor, request, "demo_update_gate", g)
        db.commit()
        return {"ok": True, "message": "DEMO / SYNTHETIC projects ready"}

    from .intelligence import install_intelligence
    from .workflow import install_workflow

    install_intelligence(app, actor_dep, db_dep)
    install_workflow(app, actor_dep, db_dep, objects)
    return app


app = create_app()
