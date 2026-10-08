"""Only opaque ciphertext and signed PUBLIC transport state; no Domain tables."""

from sqlalchemy import BigInteger, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "relay_qa_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manifest: Mapped[bytes] = mapped_column(LargeBinary)
    sequence: Mapped[int] = mapped_column(BigInteger, default=0)
    chain: Mapped[str] = mapped_column(String(64), default="0" * 64)
    pending_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_count: Mapped[int] = mapped_column(Integer, default=0)


class Message(Base):
    __tablename__ = "relay_qa_messages"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    digest: Mapped[str] = mapped_column(String(64))
    key_epoch: Mapped[int] = mapped_column(BigInteger)
    nonce: Mapped[str] = mapped_column(String(24))
    sequence: Mapped[int] = mapped_column(BigInteger)
    chain: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[bytes] = mapped_column(LargeBinary)
    __table_args__ = (
        UniqueConstraint("project", "key_epoch", "nonce"),
        UniqueConstraint("project", "sequence"),
    )


class RequestReceipt(Base):
    __tablename__ = "relay_qa_requests"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    device: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    response: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class PublicObject(Base):
    __tablename__ = "relay_qa_public_objects"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)


class PairSession(Base):
    __tablename__ = "relay_qa_pair_sessions"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    submissions: Mapped[bytes] = mapped_column(LargeBinary, default=b"[]")
    receipt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Chunk(Base):
    __tablename__ = "relay_qa_chunks"
    project: Mapped[str] = mapped_column(String(36), primary_key=True)
    locator: Mapped[str] = mapped_column(String(36), primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    receipt: Mapped[bytes] = mapped_column(LargeBinary)
    manifest_identity: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(24))
    __table_args__ = (UniqueConstraint("project", "locator", "nonce"),)


class Budget(Base):
    __tablename__ = "relay_qa_rate_budgets"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    events: Mapped[bytes] = mapped_column(LargeBinary, default=b"[]")
