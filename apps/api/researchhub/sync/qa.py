"""Explicit isolated PostgreSQL access. Never falls back to product DATABASE_URL."""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

QA_DATABASE = "researchhub_sync_kernel_qa"
QA_USER = "researchhub_sync_qa"


def assert_qa_bind(bind):
    """Prevent callers bypassing the explicit QA factory with a product engine."""
    if os.environ.get("HUB_SYNC_QA") != "1":
        raise RuntimeError("Sync Kernel requires explicit HUB_SYNC_QA=1")
    engine = getattr(bind, "engine", bind)
    url = engine.url
    if (url.drivername != "postgresql+psycopg" or url.database != QA_DATABASE
            or url.username != QA_USER or url.host not in {"localhost", "127.0.0.1"}):
        raise RuntimeError("Only the dedicated loopback QA PostgreSQL is allowed")


def qa_engine():
    """Require opt-in and exact QA identity before any schema or Domain operation."""
    if os.environ.get("HUB_SYNC_QA") != "1":
        raise RuntimeError("Sync Kernel requires explicit HUB_SYNC_QA=1")
    raw_url = os.environ.get("HUB_SYNC_QA_URL")
    if raw_url:
        url = make_url(raw_url)
    else:
        config_path = Path(os.environ.get(
            "HUB_SYNC_QA_CONFIG", "storage/runtime/sync-s1-qa.json"
        ))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("scope") != "sync-kernel-s1":
            raise RuntimeError("Wrong isolated QA scope")
        url = URL.create(
            "postgresql+psycopg", username=config["username"],
            password=config["password"], host=config["host"], port=config["port"],
            database=config["database"],
        )
    if (url.drivername != "postgresql+psycopg" or url.database != QA_DATABASE
            or url.username != QA_USER or url.host not in {"localhost", "127.0.0.1"}):
        raise RuntimeError("Only the dedicated loopback QA PostgreSQL is allowed")
    engine = create_engine(url, pool_pre_ping=True)
    assert_qa_bind(engine)
    with engine.connect() as db:
        actual_database, actual_user = db.execute(text(
            "SELECT current_database(), current_user"
        )).one()
        if (actual_database, actual_user) != (QA_DATABASE, QA_USER):
            engine.dispose()
            raise RuntimeError("Server QA database/role verification failed")
    return engine
