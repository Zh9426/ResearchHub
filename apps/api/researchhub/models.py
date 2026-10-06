"""Relational research records. JSON is limited to genuinely structured values."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DDL,
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class Lifecycle:
    """Storage lifecycle is independent from a record's scientific status."""

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    trashed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100), default="Researcher")
    password_hash: Mapped[str] = mapped_column(Text)
    bootstrap_key: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )


class Session(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApiToken(Record, Base):
    __tablename__ = "api_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON)
    actor_type: Mapped[str] = mapped_column(String(20))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Lifecycle, Record, Base):
    __tablename__ = "projects"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    module_id: Mapped[str] = mapped_column(String(80))
    module_version: Mapped[str] = mapped_column(String(80))
    module_snapshot: Mapped[dict] = mapped_column(JSON)
    enabled_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active")
    current_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_objective: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectRecord(Lifecycle, Record):
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )


class ResearchQuestion(ProjectRecord, Base):
    __tablename__ = "research_questions"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open")


class Hypothesis(ProjectRecord, Base):
    __tablename__ = "hypotheses"
    research_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_questions.id", ondelete="SET NULL"), nullable=True
    )
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    evidence_status: Mapped[str] = mapped_column(String(30), default="hypothesis")


class Milestone(ProjectRecord, Base):
    __tablename__ = "milestones"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    target_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Task(ProjectRecord, Base):
    __tablename__ = "tasks"
    milestone_id: Mapped[str | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ResearchRun(ProjectRecord, Base):
    __tablename__ = "research_runs"
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    run_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text, default="")
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="planned")
    scientific_outcome: Mapped[str] = mapped_column(String(30), default="unknown")
    protocol: Mapped[str] = mapped_column(Text, default="")
    observation: Mapped[str] = mapped_column(Text, default="")
    ai_analysis: Mapped[str] = mapped_column(Text, default="")
    human_conclusion: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(Text, default="")
    environment: Mapped[str] = mapped_column(Text, default="")
    software_version: Mapped[str] = mapped_column(String(200), default="")
    code_revision: Mapped[str] = mapped_column(String(200), default="")
    changes_from_parent: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    is_highlighted: Mapped[bool] = mapped_column(Boolean, default=False)
    highlight_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    highlight_note: Mapped[str] = mapped_column(Text, default="")
    highlighted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    highlighted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class Parameter(Lifecycle, Record, Base):
    __tablename__ = "parameters"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    value: Mapped[object | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    value_type: Mapped[str] = mapped_column(String(30), default="number")
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(30), default="unknown")
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    source_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class Metric(Lifecycle, Record, Base):
    __tablename__ = "metrics"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    value: Mapped[object | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_schema_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")


class Source(ProjectRecord, Base):
    __tablename__ = "sources"
    title: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(30), default="unknown")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True)
    citation: Mapped[str] = mapped_column(Text, default="")
    source_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Artifact(ProjectRecord, Base):
    __tablename__ = "artifacts"
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    category: Mapped[str] = mapped_column(String(100))
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Evidence(ProjectRecord, Base):
    __tablename__ = "evidence"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(100), default="observation")
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    linked_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    linked_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    linked_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    limitations: Mapped[str] = mapped_column(Text, default="")


class Claim(ProjectRecord, Base):
    __tablename__ = "claims"
    title: Mapped[str] = mapped_column(String(200), default="")
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    limitations: Mapped[str] = mapped_column(Text, default="")


class Note(ProjectRecord, Base):
    __tablename__ = "notes"
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")


class Decision(ProjectRecord, Base):
    __tablename__ = "decisions"
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    context: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="proposed")


class Risk(ProjectRecord, Base):
    __tablename__ = "risks"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(30), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    mitigation: Mapped[str] = mapped_column(Text, default="")


class Tag(ProjectRecord, Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(30), default="gray")


class Gate(ProjectRecord, Base):
    __tablename__ = "stage_gates"
    gate_id: Mapped[str] = mapped_column(String(100))
    stage_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    blocking_reason: Mapped[str] = mapped_column(Text, default="")


class GateCriterion(Lifecycle, Record, Base):
    __tablename__ = "gate_criteria"
    gate_id: Mapped[str] = mapped_column(
        ForeignKey("stage_gates.id", ondelete="CASCADE")
    )
    criterion_id: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    provenance: Mapped[str] = mapped_column(Text, default="proposed")


class AuditLog(Record, Base):
    __tablename__ = "audit_logs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(200))
    actor_type: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(36))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(50))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    request_id: Mapped[str] = mapped_column(String(100))


class ObjectDeletion(Record, Base):
    """Durable outbox survives metadata purge and transient object store failure."""

    __tablename__ = "object_deletions"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ActivityPreference(Record, Base):
    __tablename__ = "activity_preferences"
    __table_args__ = (
        UniqueConstraint("owner_id", "scope", name="uq_activity_owner_scope"),
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Empty scope is the global feed; project ids are independently clearable.
    scope: Mapped[str] = mapped_column(String(36), default="")
    hide_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportPreview(Record, Base):
    __tablename__ = "import_previews"
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    digest: Mapped[str] = mapped_column(String(64))
    module_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


for action in ("UPDATE", "DELETE"):
    event.listen(
        AuditLog.__table__,
        "after_create",
        DDL(
            "CREATE TRIGGER audit_logs_no_"
            + action.lower()
            + " BEFORE "
            + action
            + " ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )


LINKS = {}
for owner, target, k in [
    ("claims", "evidence", "evidence_ids"),
    ("claims", "research_runs", "run_ids"),
    ("claims", "artifacts", "artifact_ids"),
    ("claims", "sources", "source_ids"),
    ("decisions", "evidence", "evidence_ids"),
    ("stage_gates", "evidence", "evidence_ids"),
    ("gate_criteria", "evidence", "evidence_ids"),
    ("research_runs", "artifacts", "artifact_ids"),
    *[
        (owner, "tags", "tag_ids")
        for owner in (
            "research_runs",
            "evidence",
            "artifacts",
            "notes",
            "decisions",
            "tasks",
        )
    ],
]:
    LINKS[(owner, k)] = Table(
        f"{owner}_{k}",
        Base.metadata,
        Column(
            "owner_id", ForeignKey(f"{owner}.id", ondelete="CASCADE"), primary_key=True
        ),
        Column(
            "target_id",
            ForeignKey(f"{target}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    Index(f"ix_{owner}_{k}_target", LINKS[(owner, k)].c.target_id)

for cls in (ResearchRun, Evidence, Artifact, Task, Note, Decision):
    Index(
        f"ix_{cls.__tablename__}_project_created",
        cls.project_id,
        cls.created_at,
        cls.id,
    )
Index(
    "ix_runs_project_filters",
    ResearchRun.project_id,
    ResearchRun.run_type,
    ResearchRun.status,
    ResearchRun.scientific_outcome,
)
Index(
    "ix_runs_project_highlight",
    ResearchRun.project_id,
    ResearchRun.is_highlighted,
    ResearchRun.created_at,
)
Index("ix_runs_parent", ResearchRun.parent_run_id)
Index("ix_evidence_run", Evidence.linked_run_id)
Index("ix_artifacts_run", Artifact.run_id)
Index("ix_audit_owner_timestamp", AuditLog.owner_id, AuditLog.timestamp, AuditLog.id)
Index("ix_audit_project_timestamp", AuditLog.project_id, AuditLog.timestamp)

COLLECTIONS = {
    "runs": ResearchRun,
    "tasks": Task,
    "milestones": Milestone,
    "questions": ResearchQuestion,
    "hypotheses": Hypothesis,
    "evidence": Evidence,
    "claims": Claim,
    "sources": Source,
    "notes": Note,
    "decisions": Decision,
    "risks": Risk,
    "tags": Tag,
    "gates": Gate,
}
