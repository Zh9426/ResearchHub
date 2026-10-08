"""Explicit QA-only database guard. No native-env or DATABASE_URL fallback."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DB = "researchhub_secure_relay_qa"
USER = "researchhub_relay_qa"
PG_HOST = "researchhub-secure-relay-pg"


def validate_url(value, *, opt_in, profile):
    try:
        url = make_url(value)
        expected = (
            ("127.0.0.1", 35434)
            if profile == "host"
            else (PG_HOST, 5432)
            if profile == "container"
            else None
        )
        if (
            opt_in != "1"
            or url.drivername != "postgresql+psycopg"
            or (url.host, url.port) != expected
            or url.database != DB
            or url.username != USER
            or not url.password
            or url.query
        ):
            raise ValueError("QA_DATABASE_REJECTED")
    except Exception:  # noqa: BLE001 -- never reflect credential-bearing URL parser errors
        raise ValueError("QA_DATABASE_REJECTED") from None
    return url


def connect(value=None, *, profile=None):
    url = validate_url(
        value or os.environ.get("HUB_RELAY_QA_DATABASE_URL", ""),
        opt_in=os.environ.get("HUB_RELAY_QA"),
        profile=profile or os.environ.get("HUB_RELAY_QA_PROFILE"),
    )
    engine = create_engine(
        url,
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_size=8,
        max_overflow=0,
        pool_timeout=5,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000 -c lock_timeout=5000 -c synchronous_commit=on",
        },
    )
    with engine.connect() as db:
        actual = db.execute(text("SELECT current_database(), current_user")).one()
        if tuple(actual) != (DB, USER):
            engine.dispose()
            raise ValueError("QA_DATABASE_REJECTED")
    return engine
