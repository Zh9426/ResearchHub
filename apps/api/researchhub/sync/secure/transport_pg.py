"""Trusted client QA PostgreSQL only; independent of Relay and product metadata."""

import itertools
import json
import os
from pathlib import Path

from sqlalchemy import BigInteger, LargeBinary, String, create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from packages.secure_wire.canonical import canonical_bytes, strict_loads
from packages.secure_wire.membership import verify_bootstrap, verify_transition

from ..models import initialize_qa
from ..qa import QA_DATABASE, QA_USER, assert_qa_bind


class ClientBase(DeclarativeBase):
    pass


class Trust(ClientBase):
    __tablename__ = "secure_client_trust"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    semantic_project: Mapped[str] = mapped_column(String(36))
    owner: Mapped[str] = mapped_column(String(64))
    recovery: Mapped[str] = mapped_column(String(64))
    history: Mapped[bytes] = mapped_column(LargeBinary)
    principals: Mapped[bytes] = mapped_column(LargeBinary)
    cursor: Mapped[int] = mapped_column(BigInteger, default=0)
    chain: Mapped[str] = mapped_column(String(64), default="0" * 64)
    checkpoint: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class SealedOutbox(ClientBase):
    __tablename__ = "secure_client_outbox"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    message: Mapped[str] = mapped_column(String(36), primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)


class Received(ClientBase):
    __tablename__ = "secure_client_received"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    digest: Mapped[str] = mapped_column(String(64))
    chain: Mapped[str] = mapped_column(String(64))
    result: Mapped[bytes] = mapped_column(LargeBinary)


def guard(engine):
    assert_qa_bind(engine)
    if engine.url.port != 35433 or engine.url.query or not engine.url.password:
        raise RuntimeError("Only dedicated client QA port 35433 is allowed")


def client_engine():
    if os.environ.get("HUB_SYNC_QA") != "1":
        raise RuntimeError("Explicit HUB_SYNC_QA=1 required")
    raw = os.environ.get("HUB_SYNC_QA_URL")
    if raw:
        url = make_url(raw)
    else:
        config = json.loads(Path("storage/runtime/sync-s1-qa.json").read_text())
        if config.get("scope") != "sync-kernel-s1":
            raise RuntimeError("Wrong client QA scope")
        url = URL.create(
            "postgresql+psycopg",
            username=config["username"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
            database=config["database"],
        )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        echo=False,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=10000",
        },
    )
    guard(engine)  # Before first network connection, including schema operations.
    with engine.connect() as db:
        if db.execute(text("SELECT current_database(), current_user")).one() != (
            QA_DATABASE,
            QA_USER,
        ):
            engine.dispose()
            raise RuntimeError("Client QA server identity mismatch")
    return engine


def initialize(engine):
    guard(engine)
    initialize_qa(engine)
    ClientBase.metadata.create_all(engine)


def locked(db, project):
    guard(db.get_bind())
    row = db.scalar(select(Trust).where(Trust.project == project).with_for_update())
    if row is None:
        raise ValueError("TRUST_PIN_REQUIRED")
    history = strict_loads(row.history)
    if not isinstance(history, list) or not history:
        raise ValueError("TRUST_HISTORY_REQUIRED")
    verify_bootstrap(history[0], row.owner, row.recovery)
    for previous, candidate in itertools.pairwise(history):
        if candidate["membership_epoch"] != previous["membership_epoch"] + 1:
            raise ValueError("TRUST_HISTORY_GAP")
        verify_transition(previous, candidate, row.recovery)
    if any(item["opaque_project_id"] != project for item in history):
        raise ValueError("TRUST_PROJECT_MISMATCH")
    if canonical_bytes(history) != row.history:
        raise ValueError("TRUST_NONCANONICAL")
    return row, history


def pin(engine, manifest, owner, recovery, semantic_project, principals):
    guard(engine)
    verify_bootstrap(manifest, owner, recovery)
    with Session(engine) as db, db.begin():
        db.add(
            Trust(
                project=manifest["opaque_project_id"],
                semantic_project=semantic_project,
                owner=owner,
                recovery=recovery,
                history=canonical_bytes([manifest]),
                principals=canonical_bytes(principals),
            )
        )


def advance_history(engine, project, candidate):
    """Trusted local authority update; shares receive's lock through commit."""
    with Session(engine) as db, db.begin():
        row, history = locked(db, project)
        verify_transition(history[-1], candidate, row.recovery)
        if candidate != history[-1]:
            row.history = canonical_bytes([*history, candidate])

class PeerReceiptOutbox(ClientBase):
    __tablename__ = 'secure_client_peer_receipts'
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target: Mapped[str] = mapped_column(String(36), primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)
