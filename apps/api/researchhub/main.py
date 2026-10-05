# FastAPI dependency and field declarations intentionally use call defaults.
# ruff: noqa: B008
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
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from . import models as m
from . import service as svc
from .middleware import BodyLimitMiddleware
from .modules import load_modules
from .schemas import SCHEMAS, AuthInput, MetricsBatch, TokenInput
from .security import LoginAttempts
from .storage import S3Objects


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
    app = FastAPI(title="Research Hub", version="0.1.0")
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
            connection.execute("PRAGMA foreign_keys=ON")

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
            "version": "0.1.0",
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
    def projects(actor=Depends(actor_dep), db=Depends(db_dep)):
        return [
            svc.serialize(db, p)
            for p in db.scalars(
                select(m.Project)
                .where(m.Project.owner_id == actor.user.id)
                .order_by(m.Project.updated_at.desc())
            )
        ]

    def make_project(db, actor, request, payload, is_demo=False):
        data = svc.parsed("projects", payload)
        module = app.state.modules.get(data["module_id"])
        if not module:
            raise HTTPException(422, "Unknown module")
        if data["current_stage"] and data["current_stage"] not in {
            s["id"] for s in module["research_stages"]
        }:
            raise HTTPException(422, "Unknown stage")
        p = m.Project(owner_id=actor.user.id, is_demo=is_demo, **data)
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
    def context(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        return svc.project_context(db, actor, str(pid), app.state.modules)

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
        p = svc.project_for(db, actor, str(pid))
        before = svc.serialize(db, p)
        if "module_id" in payload and payload["module_id"] != p.module_id:
            raise HTTPException(422, "Project module cannot change after creation")
        data = svc.parsed(
            "projects",
            {**{k: before[k] for k in SCHEMAS["projects"].model_fields}, **payload},
        )
        if data["current_stage"] and data["current_stage"] not in {
            s["id"] for s in app.state.modules[p.module_id]["research_stages"]
        }:
            raise HTTPException(422, "Unknown stage")
        svc.apply_data(db, p, data)
        svc.audit(db, actor, request, "update_project", p, before)
        db.commit()
        return svc.serialize(db, p)

    @app.delete("/api/projects/{pid}")
    def delete_project(
        pid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
    ):
        p = svc.project_for(db, actor, str(pid))
        before = svc.serialize(db, p)
        svc.audit(db, actor, request, "delete_project", p, before)
        db.flush()
        db.delete(p)
        db.commit()
        return {"ok": True}

    @app.get("/api/activity")
    def activity(actor=Depends(actor_dep), db=Depends(db_dep)):
        return [
            svc.serialize(db, o)
            for o in db.scalars(
                select(m.AuditLog)
                .where(m.AuditLog.owner_id == actor.user.id)
                .order_by(m.AuditLog.timestamp.desc())
                .limit(200)
            )
        ]

    @app.get("/api/tasks")
    def all_tasks(actor=Depends(actor_dep), db=Depends(db_dep)):
        return [
            svc.serialize(db, t)
            for t in db.scalars(
                select(m.Task)
                .join(m.Project)
                .where(m.Project.owner_id == actor.user.id)
            )
        ]

    @app.get("/api/runs/{rid}/context")
    def run_context(rid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        return svc.run_context(db, actor, str(rid))

    def add_collection(kind, cls):
        def list_records(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
            svc.project_for(db, actor, str(pid))
            return [
                svc.serialize(db, o)
                for o in db.scalars(
                    select(cls)
                    .where(cls.project_id == str(pid))
                    .order_by(cls.created_at)
                )
            ]

        def create_record(
            pid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            svc.project_for(db, actor, str(pid))
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
            obj = svc.resource(db, actor, cls, str(rid))
            before = svc.serialize(db, obj)
            data = svc.parsed(
                kind, {**{k: before[k] for k in SCHEMAS[kind].model_fields}, **payload}
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
                    db, actor, request, dependents, obj.id,
                    f"状态已变为 {obj.status}",
                )
            db.commit()
            return svc.serialize(db, obj)

        def delete_record(
            rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
        ):
            obj = svc.resource(db, actor, cls, str(rid))
            dependents = (
                svc.evidence_dependents(db, obj) if isinstance(obj, m.Evidence) else []
            )
            svc.audit(db, actor, request, "delete_" + kind, obj, svc.serialize(db, obj))
            db.flush()
            db.delete(obj)
            db.flush()
            if dependents:
                svc.reconcile_evidence_dependents(
                    db, actor, request, dependents, obj.id, "已删除",
                )
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
        def listing(rid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
            svc.resource(db, actor, m.ResearchRun, str(rid))
            return [
                svc.serialize(db, o)
                for o in db.scalars(select(cls).where(cls.run_id == str(rid)))
            ]

        def creating(
            rid: UUID,
            request: Request,
            payload: dict = Body(...),
            actor=Depends(actor_dep),
            db=Depends(db_dep),
        ):
            r = svc.resource(db, actor, m.ResearchRun, str(rid))
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
            obj = svc.resource(db, actor, cls, str(rid))
            before = svc.serialize(db, obj)
            data = svc.parsed(
                kind, {**{k: before[k] for k in SCHEMAS[kind].model_fields}, **payload}
            )
            svc.validate_links(db, obj, data, app.state.modules)
            svc.apply_data(db, obj, data)
            svc.audit(db, actor, request, "update_" + kind, obj, before)
            db.commit()
            return svc.serialize(db, obj)

        def deleting(
            rid: UUID, request: Request, actor=Depends(actor_dep), db=Depends(db_dep)
        ):
            obj = svc.resource(db, actor, cls, str(rid))
            svc.audit(db, actor, request, "delete_" + kind, obj, svc.serialize(db, obj))
            db.flush()
            db.delete(obj)
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
        r = svc.resource(db, actor, m.ResearchRun, str(rid))
        objs = [
            svc.create_record(
                db,
                actor,
                request,
                "metrics",
                r.project_id,
                item.model_dump(mode="json"),
                app.state.modules,
                r.id,
            )
            for item in payload.metrics
        ]
        db.commit()
        return [svc.serialize(db, o) for o in objs]

    def objects():
        if app.state.objects is None:
            app.state.objects = S3Objects()
        return app.state.objects

    @app.get("/api/projects/{pid}/artifacts")
    def artifacts(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        svc.project_for(db, actor, str(pid))
        return [
            svc.serialize(db, o)
            for o in db.scalars(
                select(m.Artifact).where(m.Artifact.project_id == str(pid))
            )
        ]

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
        p = svc.project_for(db, actor, str(pid))
        svc.reference(db, m.ResearchRun, run_id, p.id)
        filename = file.filename or ""
        if (
            not filename
            or len(filename) > 255
            or any(c in filename for c in ("/", "\\", "\x00", "\r", "\n"))
        ):
            raise HTTPException(422, "Invalid filename")
        ext = filename.rsplit(".", 1)[-1].lower()
        allowed = {
            "png": {"image/png"},
            "jpg": {"image/jpeg"},
            "jpeg": {"image/jpeg"},
            "pdf": {"application/pdf"},
            "csv": {"text/csv", "application/csv", "text/plain"},
            "json": {"application/json", "text/plain"},
            "mat": {"application/octet-stream", "application/x-matlab-data"},
            "npy": {"application/octet-stream"},
            "npz": {"application/octet-stream", "application/zip"},
            "zip": {"application/zip", "application/x-zip-compressed"},
            "txt": {"text/plain"},
            "log": {"text/plain"},
        }
        mime = file.content_type or "application/octet-stream"
        if ext not in allowed or mime not in allowed[ext]:
            raise HTTPException(422, "Unsupported extension or MIME type")
        if category not in app.state.modules[p.module_id]["artifact_categories"]:
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
            prefix = stream.read(8)
            stream.seek(0)
            if ext in ("png", "jpg", "jpeg", "pdf"):
                signatures = {
                    "png": b"\x89PNG\r\n\x1a\n",
                    "jpg": b"\xff\xd8\xff",
                    "jpeg": b"\xff\xd8\xff",
                    "pdf": b"%PDF-",
                }
                if not prefix.startswith(signatures[ext]):
                    raise HTTPException(
                        422, "File content does not match declared type"
                    )
            aid = m.uid()
            key = f"{actor.user.id}/{p.id}/{aid}"
            try:
                objects().put(key, stream, size, mime)
            except (BotoCoreError, ClientError, ValueError, OSError):
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
            objects().delete(key)
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

    return app


app = create_app()
