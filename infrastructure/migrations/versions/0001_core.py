"""RH v0.1 initial relational schema (frozen)."""

import sqlalchemy as sa
from alembic import op

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column(
            "email",
            sa.String(length=254),
            nullable=False,
            primary_key=False,
            unique=True,
        ),
        sa.Column(
            "display_name", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column("password_hash", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "bootstrap_key",
            sa.String(length=20),
            nullable=True,
            primary_key=False,
            unique=True,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_table(
        "api_tokens",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column(
            "digest",
            sa.String(length=64),
            nullable=False,
            primary_key=False,
            unique=True,
        ),
        sa.Column("scopes", sa.JSON(), nullable=False, primary_key=False),
        sa.Column(
            "actor_type", sa.String(length=20), nullable=False, primary_key=False
        ),
        sa.Column("revoked", sa.Boolean(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_table(
        "audit_logs",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete=None),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("project_id", sa.String(length=36), nullable=True, primary_key=False),
        sa.Column("actor", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column(
            "actor_type", sa.String(length=30), nullable=False, primary_key=False
        ),
        sa.Column("action", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column(
            "resource_type", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column(
            "resource_id", sa.String(length=36), nullable=False, primary_key=False
        ),
        sa.Column("before", sa.JSON(), nullable=True, primary_key=False),
        sa.Column("after", sa.JSON(), nullable=True, primary_key=False),
        sa.Column("source", sa.String(length=50), nullable=False, primary_key=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "request_id", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_audit_logs_owner_id", "audit_logs", ["owner_id"], unique=False)
    op.create_index(
        "ix_audit_logs_project_id", "audit_logs", ["project_id"], unique=False
    )
    op.create_table(
        "projects",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete=None),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("module_id", sa.String(length=80), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "current_stage", sa.String(length=100), nullable=True, primary_key=False
        ),
        sa.Column("current_objective", sa.Text(), nullable=False, primary_key=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "digest",
            sa.String(length=64),
            nullable=False,
            primary_key=False,
            unique=True,
        ),
        sa.Column(
            "csrf_token", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_table(
        "claims",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("statement", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("limitations", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_claims_project_id", "claims", ["project_id"], unique=False)
    op.create_table(
        "milestones",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "target_date", sa.DateTime(timezone=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_milestones_project_id", "milestones", ["project_id"], unique=False
    )
    op.create_table(
        "research_questions",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_research_questions_project_id",
        "research_questions",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "research_runs",
        sa.Column(
            "parent_run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("run_type", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("objective", sa.Text(), nullable=False, primary_key=False),
        sa.Column("hypothesis", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "scientific_outcome",
            sa.String(length=30),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("protocol", sa.Text(), nullable=False, primary_key=False),
        sa.Column("observation", sa.Text(), nullable=False, primary_key=False),
        sa.Column("ai_analysis", sa.Text(), nullable=False, primary_key=False),
        sa.Column("human_conclusion", sa.Text(), nullable=False, primary_key=False),
        sa.Column("next_step", sa.Text(), nullable=False, primary_key=False),
        sa.Column("environment", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "software_version", sa.String(length=200), nullable=False, primary_key=False
        ),
        sa.Column(
            "code_revision", sa.String(length=200), nullable=False, primary_key=False
        ),
        sa.Column("changes_from_parent", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete=None),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_research_runs_project_id", "research_runs", ["project_id"], unique=False
    )
    op.create_table(
        "risks",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("severity", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("mitigation", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_risks_project_id", "risks", ["project_id"], unique=False)
    op.create_table(
        "sources",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column(
            "source_kind", sa.String(length=30), nullable=False, primary_key=False
        ),
        sa.Column("url", sa.Text(), nullable=True, primary_key=False),
        sa.Column("doi", sa.String(length=300), nullable=True, primary_key=False),
        sa.Column("citation", sa.Text(), nullable=False, primary_key=False),
        sa.Column("source_location", sa.Text(), nullable=True, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"], unique=False)
    op.create_table(
        "stage_gates",
        sa.Column("gate_id", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column("stage_id", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column("name", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("blocking_reason", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_stage_gates_project_id", "stage_gates", ["project_id"], unique=False
    )
    op.create_table(
        "tags",
        sa.Column("name", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column("color", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"], unique=False)
    op.create_table(
        "artifacts",
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False, primary_key=False),
        sa.Column(
            "mime_type", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column("size", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("checksum", sa.String(length=64), nullable=False, primary_key=False),
        sa.Column(
            "object_key",
            sa.String(length=500),
            nullable=False,
            primary_key=False,
            unique=True,
        ),
        sa.Column("category", sa.String(length=100), nullable=False, primary_key=False),
        sa.Column("metadata", sa.JSON(), nullable=False, primary_key=False),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete=None),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_artifacts_project_id", "artifacts", ["project_id"], unique=False
    )
    op.create_table(
        "claims_run_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "claims_source_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "decisions",
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("context", sa.Text(), nullable=False, primary_key=False),
        sa.Column("decision", sa.Text(), nullable=False, primary_key=False),
        sa.Column("reason", sa.Text(), nullable=False, primary_key=False),
        sa.Column("alternatives", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_decisions_project_id", "decisions", ["project_id"], unique=False
    )
    op.create_table(
        "gate_criteria",
        sa.Column(
            "gate_id",
            sa.String(length=36),
            sa.ForeignKey("stage_gates.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "criterion_id", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("provenance", sa.Text(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_table(
        "hypotheses",
        sa.Column(
            "research_question_id",
            sa.String(length=36),
            sa.ForeignKey("research_questions.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "evidence_status", sa.String(length=30), nullable=False, primary_key=False
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index(
        "ix_hypotheses_project_id", "hypotheses", ["project_id"], unique=False
    )
    op.create_table(
        "metrics",
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column(
            "value", sa.JSON(none_as_null=True), nullable=True, primary_key=False
        ),
        sa.Column("unit", sa.String(length=100), nullable=True, primary_key=False),
        sa.Column(
            "metric_schema_id", sa.String(length=100), nullable=True, primary_key=False
        ),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_metrics_run_id", "metrics", ["run_id"], unique=False)
    op.create_table(
        "notes",
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("content", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_notes_project_id", "notes", ["project_id"], unique=False)
    op.create_table(
        "parameters",
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column(
            "value", sa.JSON(none_as_null=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "value_type", sa.String(length=30), nullable=False, primary_key=False
        ),
        sa.Column("unit", sa.String(length=100), nullable=True, primary_key=False),
        sa.Column(
            "source_kind", sa.String(length=30), nullable=False, primary_key=False
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("source_location", sa.Text(), nullable=True, primary_key=False),
        sa.Column("uncertainty", sa.Text(), nullable=True, primary_key=False),
        sa.Column("valid_conditions", sa.Text(), nullable=True, primary_key=False),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, primary_key=False),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_parameters_run_id", "parameters", ["run_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column(
            "milestone_id",
            sa.String(length=36),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column("priority", sa.String(length=20), nullable=False, primary_key=False),
        sa.Column(
            "due_date", sa.DateTime(timezone=True), nullable=True, primary_key=False
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"], unique=False)
    op.create_table(
        "claims_artifact_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "evidence",
        sa.Column("title", sa.String(length=200), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "evidence_type", sa.String(length=100), nullable=False, primary_key=False
        ),
        sa.Column("status", sa.String(length=30), nullable=False, primary_key=False),
        sa.Column(
            "linked_run_id",
            sa.String(length=36),
            sa.ForeignKey("research_runs.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "linked_artifact_id",
            sa.String(length=36),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "linked_source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("limitations", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False
        ),
    )
    op.create_index("ix_evidence_project_id", "evidence", ["project_id"], unique=False)
    op.create_table(
        "claims_evidence_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "decisions_evidence_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("decisions.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "gate_criteria_evidence_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("gate_criteria.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_table(
        "stage_gates_evidence_ids",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("stage_gates.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )


def downgrade():
    op.drop_table("stage_gates_evidence_ids")
    op.drop_table("gate_criteria_evidence_ids")
    op.drop_table("decisions_evidence_ids")
    op.drop_table("claims_evidence_ids")
    op.drop_table("evidence")
    op.drop_table("claims_artifact_ids")
    op.drop_table("tasks")
    op.drop_table("parameters")
    op.drop_table("notes")
    op.drop_table("metrics")
    op.drop_table("hypotheses")
    op.drop_table("gate_criteria")
    op.drop_table("decisions")
    op.drop_table("claims_source_ids")
    op.drop_table("claims_run_ids")
    op.drop_table("artifacts")
    op.drop_table("tags")
    op.drop_table("stage_gates")
    op.drop_table("sources")
    op.drop_table("risks")
    op.drop_table("research_runs")
    op.drop_table("research_questions")
    op.drop_table("milestones")
    op.drop_table("claims")
    op.drop_table("sessions")
    op.drop_table("projects")
    op.drop_table("audit_logs")
    op.drop_table("api_tokens")
    op.drop_table("users")
