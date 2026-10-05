"""Opt-in quiescent QA recovery drill; creates fresh targets and preserves them."""

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from apps.api.researchhub.models import Base
from scripts.backup_data import client, export_objects, restore_objects


def test_native_postgresql_and_minio_restore_to_fresh_targets(monkeypatch):
    config_file = os.getenv("HUB_NATIVE_ENV_FILE")
    if not config_file or not os.getenv("HUB_CHECK_RECOVERY"):
        pytest.skip("Requires explicit native QA recovery drill with API/Web stopped")
    config = json.loads(Path(config_file).read_text(encoding="utf-8-sig"))
    suffix = uuid.uuid4().hex[:10]
    database = f"researchhub_recovery_{suffix}"
    bucket = f"researchhub-recovery-{suffix}"
    directory = Path("storage/backups") / f"qa-recovery-{suffix}"
    directory.mkdir(parents=True)
    binary = Path("storage/runtime/pgsql/bin").resolve()
    environment = {**os.environ, "PGPASSWORD": config["POSTGRES_PASSWORD"]}
    common = ["-h", "127.0.0.1", "-p", str(config["POSTGRES_PORT"]), "-U", config["POSTGRES_USER"]]
    source_url = make_url(config["QA_DATABASE_URL"])
    source_engine = create_engine(source_url)
    with source_engine.connect() as source:
        expected = {name: source.scalar(text(f'SELECT count(*) FROM "{name}"')) for name in Base.metadata.tables}
    for name in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.setenv(name, config[name])
    monkeypatch.setenv("S3_BUCKET", "researchhub-qa")
    export_objects(directory / "objects.zip")
    subprocess.run([str(binary / "pg_dump.exe"), *common, "-d", "researchhub_qa", "-Fc", "-f", str(directory / "postgres.dump")], env=environment, check=True, capture_output=True)
    subprocess.run([str(binary / "createdb.exe"), *common, database], env=environment, check=True, capture_output=True)
    subprocess.run([str(binary / "pg_restore.exe"), *common, "-d", database, "--exit-on-error", "--no-owner", "--no-privileges", str(directory / "postgres.dump")], env=environment, check=True, capture_output=True)
    monkeypatch.setenv("S3_BUCKET", bucket)
    restore_objects(directory / "objects.zip")
    recovered_engine = create_engine(source_url.set(database=database))
    try:
        with recovered_engine.connect() as recovered:
            actual = {name: recovered.scalar(text(f'SELECT count(*) FROM "{name}"')) for name in Base.metadata.tables}
            assert actual == expected
            probe = json.loads(Path("storage/persistence-probe.json").read_text(encoding="utf-8"))
            key = recovered.scalar(text("SELECT object_key FROM artifacts WHERE id=:id"), {"id": probe["artifact_id"]})
            assert key
        response = client().get_object(Bucket=bucket, Key=key)
        try:
            data = response["Body"].read()
        finally:
            response["Body"].close()
        assert hashlib.sha256(data).hexdigest() == probe["checksum"]
        assert data.decode() == probe["content"]
        (directory / "verification.json").write_text(json.dumps({
            "database": database, "bucket": bucket, "table_count": len(actual),
            "artifact_checksum": probe["checksum"], "status": "SYNTHETIC QA recovery verified",
        }), encoding="utf-8")
    finally:
        source_engine.dispose()
        recovered_engine.dispose()
