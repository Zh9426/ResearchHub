"""显式 opt-in：真实 Compose PG/MinIO，恢复至全新数据库和桶。"""
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from scripts.backup_data import client, export_objects, restore_objects


def test_compose_backup_restore(monkeypatch):
    if os.getenv("HUB_COMPOSE_RECOVERY") != "1":
        pytest.skip("Requires explicit isolated Compose recovery with writers stopped")
    config = dict(line.split("=", 1) for line in Path(".env.qa").read_text().splitlines() if "=" in line)
    command = ["docker", "compose", "-p", "researchhub-v02-qa", "--env-file", ".env.qa",
               "-f", "docker-compose.yml", "-f", "docker-compose.qa.yml"]
    suffix = uuid.uuid4().hex[:10]
    target_db = "researchhub_recovery_" + suffix
    target_bucket = "researchhub-recovery-" + suffix
    directory = Path("storage/backups") / ("compose-recovery-" + suffix)
    directory.mkdir(parents=True)

    def compose(*args):
        result = subprocess.run([*command, *args], capture_output=True, check=False)
        assert result.returncode == 0, "Isolated Compose operation failed; inspect local container logs"
        return result.stdout

    def url(database):
        return URL.create("postgresql+psycopg", username=config["POSTGRES_USER"],
                          password=config["POSTGRES_PASSWORD"], host="127.0.0.1", port=35432, database=database)

    engine = create_engine(url(config["POSTGRES_DB"]))
    with engine.connect() as db:
        tables = inspect(engine).get_table_names()
        expected = {table: db.scalar(text('SELECT count(*) FROM "' + table + '"')) for table in tables}
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://127.0.0.1:39000")
    for name in ("S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.setenv(name, config[name])
    monkeypatch.setenv("S3_BUCKET", config["S3_BUCKET"])
    export_objects(directory / "objects.zip")
    compose("exec", "-T", "db", "pg_dump", "-U", config["POSTGRES_USER"], "-d", config["POSTGRES_DB"],
            "-Fc", "-f", "/tmp/qa-recovery.dump")
    compose("cp", "db:/tmp/qa-recovery.dump", str(directory / "postgres.dump"))
    compose("exec", "-T", "db", "createdb", "-U", config["POSTGRES_USER"], target_db)
    compose("exec", "-T", "db", "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
            "-U", config["POSTGRES_USER"], "-d", target_db, "/tmp/qa-recovery.dump")
    monkeypatch.setenv("S3_BUCKET", target_bucket)
    restore_objects(directory / "objects.zip")
    recovered = create_engine(url(target_db))
    with recovered.connect() as db:
        actual = {table: db.scalar(text('SELECT count(*) FROM "' + table + '"')) for table in tables}
        assert expected == actual
        probe = json.loads(Path("storage/persistence-probe.json").read_text())
        key = db.scalar(text("SELECT object_key FROM artifacts WHERE id=:id"), {"id": probe["artifact_id"]})
    response = client().get_object(Bucket=target_bucket, Key=key)
    try:
        assert hashlib.sha256(response["Body"].read()).hexdigest() == probe["checksum"]
    finally:
        response["Body"].close()
    (directory / "verification.json").write_text(json.dumps({"status": "verified", "tables": len(tables),
        "database": target_db, "bucket": target_bucket, "artifact_checksum": probe["checksum"]}), encoding="utf-8")
    engine.dispose()
    recovered.dispose()
