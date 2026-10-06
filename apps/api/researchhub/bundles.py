"""Bounded project exports and staged, human-confirmed scientific bundles."""

# FastAPI dependency declarations intentionally use call defaults.
# ruff: noqa: B008
import csv
import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from datetime import timedelta, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from starlette.background import BackgroundTask

from . import models as m
from . import service as svc
from .schemas import (
    BundleManifest,
    ImportConfirmInput,
    MetricInput,
    ParameterInput,
    RunInput,
)
from .storage import ALLOWED_ARTIFACT_TYPES, ARTIFACT_SIGNATURES
from .workflow import audit_statement

MAX_BUNDLE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_EXPORT_BYTES = 256 * 1024 * 1024
MAX_EXPORT_ROWS = 20000


def staging_root():
    # Only deployment configuration controls this path, never client input.
    root = Path(
        os.getenv(
            "IMPORT_STAGING_DIR",
            str(Path(tempfile.gettempdir()) / "researchhub-imports"),
        )
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def unique_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("重复 JSON 字段")
            result[key] = value
        return result

    return json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("非有限数值")),
    )


def safe_zip_path(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or any(ord(c) < 32 for c in name)
        or ":" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
        or name.startswith("/")
    ):
        raise HTTPException(422, "Bundle 包含不安全的路径")
    return path


def validate_bundle(db, actor, project, stream):
    try:
        archive = zipfile.ZipFile(stream)
        infos = archive.infolist()
        if len(infos) > 256:
            raise HTTPException(413, "Bundle 文件数超过上限")
        names = set()
        expanded = 0
        for info in infos:
            safe_zip_path(info.filename)
            mode = info.external_attr >> 16
            if (
                stat.S_ISLNK(mode)
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                or info.flag_bits & 1
            ):
                raise HTTPException(422, "Bundle 不允许符号链接、特殊文件或加密文件")
            if info.filename.casefold() in names:
                raise HTTPException(422, "Bundle 包含重复文件路径")
            names.add(info.filename.casefold())
            expanded += info.file_size
            if (
                info.file_size > MAX_BUNDLE_BYTES
                or expanded > MAX_EXPANDED_BYTES
                or info.file_size > max(1, info.compress_size) * 100
            ):
                raise HTTPException(413, "Bundle 解压大小或压缩比例超过上限")
        available = {i.filename for i in infos if not i.is_dir()}
        run_file = (
            "researchhub-run.json"
            if "researchhub-run.json" in available
            else "run.json"
        )
        artifact_file = (
            "manifest.json" if "manifest.json" in available else "artifacts.json"
        )
        required = {run_file, "parameters.json", "metrics.json", artifact_file}
        if not required <= available:
            raise HTTPException(
                422,
                "Bundle 缺少 researchhub-run.json、parameters.json、metrics.json 或 manifest.json",
            )

        def read_json(name):
            if archive.getinfo(name).file_size > 1024 * 1024:
                raise HTTPException(413, "Bundle 元数据文件超过 1 MiB")
            return unique_json(archive.read(name).decode("utf-8-sig"))

        run = RunInput.model_validate(read_json(run_file)).model_dump(mode="json")
        raw_parameters, raw_metrics = (
            read_json("parameters.json"),
            read_json("metrics.json"),
        )
        if (
            not isinstance(raw_parameters, list)
            or not isinstance(raw_metrics, list)
            or len(raw_parameters) > 100
            or len(raw_metrics) > 100
        ):
            raise HTTPException(422, "参数和指标必须是最多 100 条的数组")
        parameters = [
            ParameterInput.model_validate(p).model_dump(mode="json")
            for p in raw_parameters
        ]
        metrics = [
            MetricInput.model_validate(p).model_dump(mode="json") for p in raw_metrics
        ]
        raw_manifest = read_json(artifact_file)
        manifest = BundleManifest.model_validate(
            {"artifacts": raw_manifest}
            if artifact_file == "artifacts.json"
            else raw_manifest
        ).model_dump(mode="json")
        artifacts = manifest["artifacts"]
        if len({p["name"] for p in parameters}) != len(parameters) or len(
            {p["name"] for p in metrics}
        ) != len(metrics):
            raise HTTPException(422, "Bundle 参数或指标包含重复名称")
        if (
            run["human_conclusion"]
            or any(
                p["is_confirmed"] or p["source_kind"] in {"measured", "calibrated"}
                for p in parameters
            )
            or any(
                p["status"] in {"measured", "calibrated", "validated", "reproduced"}
                for p in metrics
            )
        ):
            raise HTTPException(
                422, "Bundle 不能导入人工结论、确认或测量验证状态；导入后请人工核验"
            )
        candidate = m.ResearchRun(id=m.uid(), project_id=project.id)
        svc.validate_links(db, candidate, run, {})
        for parameter in parameters:
            svc.reference(db, m.Source, parameter["source_id"], project.id)
        metric_ids = {item["id"] for item in svc.module_for(project)["metric_schemas"]}
        if any(
            item["metric_schema_id"] and item["metric_schema_id"] not in metric_ids
            for item in metrics
        ):
            raise HTTPException(422, "Bundle 指标未在项目冻结模块中定义")
        categories = svc.module_for(project)["artifact_categories"]
        referenced = set()
        filenames = set()
        for artifact in artifacts:
            path = safe_zip_path(artifact["path"])
            if (
                len(path.parts) < 2
                or path.parts[0] not in {"artifacts", "files"}
                or artifact["path"] not in available
                or artifact["path"] in referenced
            ):
                raise HTTPException(422, "Artifact 路径缺失、重复或不在 artifacts/ 内")
            filename = artifact["filename"]
            if (
                any(c in filename for c in ("/", "\\", "\x00", "\r", "\n"))
                or filename.casefold() in filenames
            ):
                raise HTTPException(422, "Artifact 文件名不安全或重复")
            filenames.add(filename.casefold())
            referenced.add(artifact["path"])
            ext = filename.rsplit(".", 1)[-1].lower()
            if (
                ext not in ALLOWED_ARTIFACT_TYPES
                or artifact["mime_type"] not in ALLOWED_ARTIFACT_TYPES[ext]
            ):
                raise HTTPException(422, "Artifact 文件扩展名或 MIME 类型不支持")
            if not archive.getinfo(artifact["path"]).file_size:
                raise HTTPException(422, "Artifact 不能为空文件")
            if artifact["category"] not in categories:
                raise HTTPException(422, "Artifact 分类未在项目冻结模块中定义")
            hash_ = hashlib.sha256()
            with archive.open(artifact["path"]) as source:
                prefix = source.read(8)
                if ext in ARTIFACT_SIGNATURES and not prefix.startswith(
                    ARTIFACT_SIGNATURES[ext]
                ):
                    raise HTTPException(422, "Artifact 内容与文件类型不匹配")
                hash_.update(prefix)
                while chunk := source.read(65536):
                    hash_.update(chunk)
            if hash_.hexdigest() != artifact["checksum"]:
                raise HTTPException(422, "Artifact SHA-256 不匹配")
        if available != required | referenced:
            raise HTTPException(422, "Bundle 含有未声明或重复入口的文件")
        conflicts = []
        if db.scalar(
            select(m.ResearchRun.id)
            .where(
                m.ResearchRun.project_id == project.id,
                m.ResearchRun.title == run["title"],
                m.ResearchRun.trashed_at.is_(None),
            )
            .limit(1)
        ):
            conflicts.append(
                {
                    "field": "title",
                    "message": "项目中已有相同标题；确认导入将创建独立记录",
                }
            )
        for artifact in artifacts:
            if db.scalar(
                select(m.Artifact.id)
                .where(
                    m.Artifact.project_id == project.id,
                    m.Artifact.checksum == artifact["checksum"],
                )
                .limit(1)
            ):
                conflicts.append(
                    {
                        "field": "checksum",
                        "path": artifact["path"],
                        "message": "项目已有相同内容；确认将创建新的导入记录",
                    }
                )
        return {
            "run": run,
            "parameters": parameters,
            "metrics": metrics,
            "artifacts": artifacts,
            "conflicts": conflicts,
        }
    except HTTPException:
        raise
    except (
        zipfile.BadZipFile,
        UnicodeError,
        ValueError,
        KeyError,
        RuntimeError,
        ValidationError,
    ) as error:
        raise HTTPException(422, "Bundle ZIP 或元数据格式无效") from error
    finally:
        if "archive" in locals():
            archive.close()


def response_for_stream(stream, filename, media_type):
    stream.seek(0)

    def chunks():
        while chunk := stream.read(65536):
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=BackgroundTask(stream.close),
    )


def csv_rows(rows):
    # Formula protection is for spreadsheet safety; JSONL preserves exact text.
    def cell(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    iterator = iter(rows)
    first = next(iterator, None)
    if first is None:
        yield b"id\r\n"
        return
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(first), extrasaction="raise")
    writer.writeheader()
    for row in [first]:
        writer.writerow({k: cell(v) for k, v in row.items()})
    yield buffer.getvalue().encode("utf-8-sig")
    for row in iterator:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow({k: cell(v) for k, v in row.items()})
        yield buffer.getvalue().encode("utf-8")


def project_export(db, actor, pid, include_files, objects):
    project = svc.project_for(db, actor, pid, include_trashed=True, lock=True)
    statements = {
        kind: select(cls).where(cls.project_id == pid).order_by(cls.created_at, cls.id)
        for kind, cls in {**m.COLLECTIONS, "artifacts": m.Artifact}.items()
    }
    run_ids = select(m.ResearchRun.id).where(m.ResearchRun.project_id == pid)
    statements.update(
        {
            "parameters": select(m.Parameter).where(m.Parameter.run_id.in_(run_ids)),
            "metrics": select(m.Metric).where(m.Metric.run_id.in_(run_ids)),
            "gate_criteria": select(m.GateCriterion).where(
                m.GateCriterion.gate_id.in_(
                    select(m.Gate.id).where(m.Gate.project_id == pid)
                )
            ),
        }
    )
    audit_stmt = audit_statement(db, actor, {"project_id": pid})
    total = sum(
        db.scalar(select(func.count()).select_from(stmt.subquery()))
        for stmt in [*statements.values(), audit_stmt]
    )
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(413, "导出记录超过 20000 条，请缩小项目或联系维护者")
    artifacts = list(db.scalars(statements["artifacts"]))
    if include_files and sum(a.size for a in artifacts) > MAX_EXPORT_BYTES:
        raise HTTPException(413, "导出文件大小超过 256 MiB")
    stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115 - StreamingResponse closes it after sending.
    size = 0

    def write_member(archive, filename, chunks):
        nonlocal size
        with archive.open(filename, "w", force_zip64=True) as target:
            for chunk in chunks:
                size += len(chunk)
                if size > MAX_EXPORT_BYTES:
                    raise HTTPException(413, "导出总大小超过 256 MiB")
                target.write(chunk)

    try:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            write_member(
                archive, "project.json", [json_bytes(svc.serialize(db, project))]
            )
            write_member(
                archive, "module-manifest.json", [json_bytes(svc.module_for(project))]
            )
            for kind, stmt in statements.items():
                rows = (
                    svc.serialize(db, obj)
                    for obj in db.scalars(stmt.execution_options(yield_per=100))
                )
                write_member(archive, kind + ".csv", csv_rows(rows))
                # Exact structured metadata is a recovery/analysis companion to CSV.
                write_member(
                    archive,
                    kind + ".jsonl",
                    (
                        json_bytes(svc.serialize(db, obj))
                        for obj in db.scalars(stmt.execution_options(yield_per=100))
                    ),
                )
            write_member(
                archive,
                "audit.jsonl",
                (
                    json_bytes(svc.serialize(db, obj))
                    for obj in db.scalars(
                        audit_stmt.order_by(m.AuditLog.timestamp).execution_options(
                            yield_per=100
                        )
                    )
                ),
            )
            write_member(
                archive,
                "activity.csv",
                csv_rows(
                    svc.serialize(db, obj)
                    for obj in db.scalars(
                        audit_statement(
                            db, actor, {"project_id": pid}, activity=True
                        ).order_by(m.AuditLog.timestamp)
                    )
                ),
            )
            for artifact in artifacts if include_files else []:
                source = objects().get(artifact.object_key)
                hash_ = hashlib.sha256()
                count = 0

                def file_chunks(source=source, artifact=artifact, hash_=hash_):
                    nonlocal count
                    while chunk := source.read(65536):
                        count += len(chunk)
                        if count > artifact.size:
                            raise HTTPException(409, "Artifact 大小与保存记录不一致")
                        hash_.update(chunk)
                        yield chunk

                try:
                    write_member(
                        archive,
                        f"artifacts/{artifact.id}/{artifact.filename}",
                        file_chunks(),
                    )
                finally:
                    source.close()
                if count != artifact.size or hash_.hexdigest() != artifact.checksum:
                    raise HTTPException(409, "Artifact SHA-256 或大小与记录不一致")
            write_member(
                archive,
                "README.md",
                [
                    "# Research Hub 项目导出\n\n科研数据库只读快照，包含模块冻结定义、科研记录、生命周期与完整 Audit。CSV 防公式注入，JSONL 保留精确结构。文件导出逐个校验 SHA-256。此项目导出不等同于单 Run 导入 Bundle，也不是 PostgreSQL/MinIO 完整备份。\n".encode()
                ],
            )
        return response_for_stream(stream, f"researchhub-{pid}.zip", "application/zip")
    except HTTPException:
        stream.close()
        raise
    except Exception as error:
        stream.close()
        raise HTTPException(
            503, "项目导出失败；没有提供部分导出，请检查对象存储与数据一致性"
        ) from error


def install_bundle_routes(app, actor_dep, db_dep, objects):
    @app.get("/api/projects/{pid}/export")
    def export(
        pid: UUID,
        include_files: bool = False,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        return project_export(db, actor, str(pid), include_files, objects)

    def build_audit_export(db, actor, params, format, label):
        if format not in {"jsonl", "csv"}:
            raise HTTPException(422, "审计导出格式必须是 jsonl 或 csv")
        statement = audit_statement(db, actor, params).order_by(m.AuditLog.timestamp)
        if (
            db.scalar(select(func.count()).select_from(statement.subquery()))
            > MAX_EXPORT_ROWS
        ):
            raise HTTPException(413, "审计导出记录数超过上限")
        rows = (
            svc.serialize(db, row)
            for row in db.scalars(statement.execution_options(yield_per=100))
        )
        stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115 - StreamingResponse owns the stream.
        count = 0
        try:
            for chunk in (
                csv_rows(rows) if format == "csv" else (json_bytes(row) for row in rows)
            ):
                count += len(chunk)
                if count > MAX_EXPORT_BYTES:
                    raise HTTPException(413, "审计导出大小超过上限")
                stream.write(chunk)
            return response_for_stream(
                stream,
                f"audit-{label}.{format}",
                "text/csv" if format == "csv" else "application/x-ndjson",
            )
        except Exception:
            stream.close()
            raise

    @app.get("/api/projects/{pid}/audit/export")
    def export_audit(
        pid: UUID,
        request: Request,
        format: str = "jsonl",
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        return build_audit_export(
            db,
            actor,
            {**dict(request.query_params), "project_id": str(pid)},
            format,
            str(pid),
        )

    @app.get("/api/audit/export")
    def export_global_audit(
        request: Request,
        format: str = "jsonl",
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        return build_audit_export(
            db, actor, dict(request.query_params), format, "owner"
        )

    @app.get("/api/projects/{pid}/research-log")
    def research_log(pid: UUID, actor=Depends(actor_dep), db=Depends(db_dep)):
        project = svc.project_for(db, actor, str(pid))
        statement = (
            select(m.ResearchRun)
            .where(
                m.ResearchRun.project_id == str(pid),
                *svc.visible_records(m.ResearchRun),
            )
            .order_by(m.ResearchRun.created_at)
        )
        if (
            db.scalar(select(func.count()).select_from(statement.subquery()))
            > MAX_EXPORT_ROWS
        ):
            raise HTTPException(413, "研究日志记录数超过上限")
        stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115 - StreamingResponse owns the stream.
        stream.write(
            f"# {project.name}\n\n{project.current_objective}\n\n模块：{project.module_id} {project.module_version}\n".encode()
        )
        try:
            for run in db.scalars(statement.execution_options(yield_per=100)):
                text = f"\n## {'★ ' if run.is_highlighted else ''}{run.title}\n\n{run.created_at.isoformat()} · {run.run_type} · {run.status} · {run.scientific_outcome}\n\n目标：{run.objective}\n\n观察：{run.observation}\n\n人工结论：{run.human_conclusion}\n\n下一步：{run.next_step}\n"
                stream.write(text.encode("utf-8"))
                if stream.tell() > MAX_EXPORT_BYTES:
                    raise HTTPException(413, "研究日志大小超过上限")
            return response_for_stream(
                stream, f"research-log-{pid}.md", "text/markdown"
            )
        except Exception:
            stream.close()
            raise

    @app.post("/api/projects/{pid}/imports/preview")
    def preview(
        pid: UUID,
        file: UploadFile = File(...),
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.require_human(actor)
        project = svc.project_for(db, actor, str(pid), write=True)
        # Expired staging is housekeeping metadata, never a scientific write.
        for old in db.scalars(
            select(m.ImportPreview)
            .where(
                m.ImportPreview.owner_id == actor.user.id,
                m.ImportPreview.expires_at < m.now(),
            )
            .limit(100)
        ):
            (staging_root() / (old.id + ".zip")).unlink(missing_ok=True)
            db.delete(old)
        active = db.scalar(
            select(func.count())
            .select_from(m.ImportPreview)
            .where(
                m.ImportPreview.owner_id == actor.user.id,
                m.ImportPreview.expires_at >= m.now(),
                m.ImportPreview.consumed_at.is_(None),
            )
        )
        if active >= 10:
            raise HTTPException(429, "最多保留 10 个待确认预览，请确认或等待过期")
        preview_id = m.uid()
        path = staging_root() / (preview_id + ".zip")
        size = 0
        hash_ = hashlib.sha256()
        try:
            with path.open("xb") as target:
                while chunk := file.file.read(65536):
                    size += len(chunk)
                    if size > MAX_BUNDLE_BYTES:
                        raise HTTPException(413, "Bundle ZIP 超过 50 MiB")
                    hash_.update(chunk)
                    target.write(chunk)
            with path.open("rb") as stream:
                parsed = validate_bundle(db, actor, project, stream)
            row = m.ImportPreview(
                id=preview_id,
                owner_id=actor.user.id,
                project_id=project.id,
                digest=hash_.hexdigest(),
                module_digest=svc.module_digest(svc.module_for(project)),
                expires_at=m.now() + timedelta(hours=1),
            )
            db.add(row)
            db.commit()
            return {
                "preview_id": preview_id,
                "digest": row.digest,
                "run": parsed["run"],
                "parameters": parsed["parameters"],
                "metrics": parsed["metrics"],
                "artifacts": parsed["artifacts"],
                "counts": {
                    key: len(parsed[key])
                    for key in ("parameters", "metrics", "artifacts")
                },
                "conflicts": parsed["conflicts"],
                "expires_at": row.expires_at,
            }
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/projects/{pid}/imports/confirm")
    def confirm(
        pid: UUID,
        payload: ImportConfirmInput,
        request: Request,
        actor=Depends(actor_dep),
        db=Depends(db_dep),
    ):
        svc.require_human(actor)
        project = svc.project_for(db, actor, str(pid), write=True)
        row = db.scalar(
            select(m.ImportPreview)
            .where(
                m.ImportPreview.id == str(payload.preview_id),
                m.ImportPreview.owner_id == actor.user.id,
                m.ImportPreview.project_id == project.id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(404, "导入预览不存在")
        expiry = (
            row.expires_at
            if row.expires_at.tzinfo
            else row.expires_at.replace(tzinfo=timezone.utc)
        )
        if row.consumed_at or expiry < m.now():
            raise HTTPException(409, "预览已使用或已过期，请重新预览")
        if payload.digest != row.digest or row.module_digest != svc.module_digest(
            svc.module_for(project)
        ):
            raise HTTPException(409, "Bundle 或模块定义已变化，请重新预览")
        path = staging_root() / (row.id + ".zip")
        if not path.is_file() or path.is_symlink():
            raise HTTPException(410, "临时 Bundle 已不可用，请重新上传")
        keys = []
        owner_id, project_id = actor.user.id, project.id
        try:
            with path.open("rb") as stream:
                hash_ = hashlib.sha256()
                while chunk := stream.read(65536):
                    hash_.update(chunk)
                if hash_.hexdigest() != row.digest:
                    raise HTTPException(409, "临时 Bundle 完整性校验失败")
                stream.seek(0)
                parsed = validate_bundle(db, actor, project, stream)
                run = svc.create_record(
                    db,
                    actor,
                    request,
                    "runs",
                    project.id,
                    parsed["run"],
                    app.state.modules,
                )
                for kind in ("parameters", "metrics"):
                    for item in parsed[kind]:
                        svc.create_record(
                            db,
                            actor,
                            request,
                            kind,
                            project.id,
                            item,
                            app.state.modules,
                            run.id,
                        )
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    for item in parsed["artifacts"]:
                        aid = m.uid()
                        key = f"{owner_id}/{project_id}/{aid}"
                        keys.append(key)
                        info = archive.getinfo(item["path"])
                        with archive.open(item["path"]) as source:
                            objects().put(
                                key, source, info.file_size, item["mime_type"]
                            )
                        artifact = m.Artifact(
                            id=aid,
                            project_id=project.id,
                            run_id=run.id,
                            filename=item["filename"],
                            mime_type=item["mime_type"],
                            category=item["category"],
                            checksum=item["checksum"],
                            size=info.file_size,
                            object_key=key,
                            artifact_metadata={
                                **item["metadata"],
                                "import_provenance": {
                                    "preview_id": row.id,
                                    "bundle_digest": row.digest,
                                    "path": item["path"],
                                },
                            },
                            created_by=owner_id,
                        )
                        db.add(artifact)
                        db.flush()
                        svc.audit(db, actor, request, "import_artifact", artifact)
                row.consumed_at = m.now()
                svc.audit(
                    db,
                    actor,
                    request,
                    "import_bundle",
                    run,
                    {
                        "bundle_digest": row.digest,
                        "preview_id": row.id,
                        "module_digest": row.module_digest,
                    },
                )
                result = svc.run_context(db, actor, run.id)
                db.commit()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Successful scientific commits must not become failed responses
                # because temporary-file housekeeping failed.
                pass
            return result
        except Exception as error:
            db.rollback()
            # Includes ambiguous upload/commit failure. GC rechecks live references,
            # so an acknowledged DB commit can never have its live objects removed.
            for key in keys:
                svc.enqueue_object_deletion(db, owner_id, project_id, key)
            if keys:
                db.commit()
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(
                503, "导入失败，科研记录已回滚；对象清理进入可重试队列"
            ) from error
