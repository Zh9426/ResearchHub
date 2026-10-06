"""Add workflow metadata without changing frozen definitions or scientific records."""

import sqlalchemy as sa
from alembic import op

revision = "0003_workflow"
down_revision = "0002_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "enabled_capabilities", sa.JSON(), nullable=False, server_default="[]"
        ),
    )
    for column in (
        sa.Column("context_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "is_highlighted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("highlight_type", sa.String(100), nullable=True),
        sa.Column("highlight_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("highlighted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("highlighted_by", sa.String(36), nullable=True),
    ):
        op.add_column("research_runs", column)
    with op.batch_alter_table("research_runs") as batch:
        batch.create_foreign_key(
            "fk_runs_highlighted_by", "users", ["highlighted_by"], ["id"]
        )
    for table in (
        "claims_evidence_ids",
        "claims_run_ids",
        "claims_artifact_ids",
        "claims_source_ids",
        "decisions_evidence_ids",
        "stage_gates_evidence_ids",
        "gate_criteria_evidence_ids",
    ):
        op.create_index(f"ix_{table}_target", table, ["target_id"])
    for owner, key, target in [("research_runs", "artifact_ids", "artifacts")] + [
        (name, "tag_ids", "tags")
        for name in (
            "research_runs",
            "evidence",
            "artifacts",
            "notes",
            "decisions",
            "tasks",
        )
    ]:
        table = f"{owner}_{key}"
        op.create_table(
            table,
            sa.Column(
                "owner_id",
                sa.String(36),
                sa.ForeignKey(f"{owner}.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "target_id",
                sa.String(36),
                sa.ForeignKey(f"{target}.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )
        op.create_index(f"ix_{table}_target", table, ["target_id"])

    def stamp_columns():
        return [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ]

    op.create_table(
        "activity_preferences",
        *stamp_columns(),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(36), nullable=False),
        sa.Column("hide_before", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "scope", name="uq_activity_owner_scope"),
    )
    op.create_table(
        "import_previews",
        *stamp_columns(),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("module_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for field in ("owner_id", "project_id"):
        op.create_index(f"ix_import_previews_{field}", "import_previews", [field])
    for table in (
        "research_runs",
        "evidence",
        "artifacts",
        "tasks",
        "notes",
        "decisions",
    ):
        op.create_index(
            f"ix_{table}_project_created", table, ["project_id", "created_at", "id"]
        )
    for name, table, fields in (
        (
            "ix_runs_project_filters",
            "research_runs",
            ["project_id", "run_type", "status", "scientific_outcome"],
        ),
        (
            "ix_runs_project_highlight",
            "research_runs",
            ["project_id", "is_highlighted", "created_at"],
        ),
        ("ix_runs_parent", "research_runs", ["parent_run_id"]),
        ("ix_evidence_run", "evidence", ["linked_run_id"]),
        ("ix_artifacts_run", "artifacts", ["run_id"]),
        ("ix_audit_owner_timestamp", "audit_logs", ["owner_id", "timestamp", "id"]),
        ("ix_audit_project_timestamp", "audit_logs", ["project_id", "timestamp"]),
    ):
        op.create_index(name, table, fields)


def downgrade():
    for name, table in (
        ("ix_runs_project_filters", "research_runs"),
        ("ix_runs_project_highlight", "research_runs"),
        ("ix_runs_parent", "research_runs"),
        ("ix_evidence_run", "evidence"),
        ("ix_artifacts_run", "artifacts"),
        ("ix_audit_owner_timestamp", "audit_logs"),
        ("ix_audit_project_timestamp", "audit_logs"),
    ):
        op.drop_index(name, table)
    for table in (
        "research_runs",
        "evidence",
        "artifacts",
        "tasks",
        "notes",
        "decisions",
    ):
        op.drop_index(f"ix_{table}_project_created", table)
    for table in (
        "claims_evidence_ids",
        "claims_run_ids",
        "claims_artifact_ids",
        "claims_source_ids",
        "decisions_evidence_ids",
        "stage_gates_evidence_ids",
        "gate_criteria_evidence_ids",
    ):
        op.drop_index(f"ix_{table}_target", table)
    op.drop_table("import_previews")
    op.drop_table("activity_preferences")
    for owner, key in [("research_runs", "artifact_ids")] + [
        (name, "tag_ids")
        for name in (
            "research_runs",
            "evidence",
            "artifacts",
            "notes",
            "decisions",
            "tasks",
        )
    ]:
        op.drop_table(f"{owner}_{key}")
    with op.batch_alter_table("research_runs") as batch:
        batch.drop_constraint("fk_runs_highlighted_by", type_="foreignkey")
        for field in (
            "context_data",
            "is_highlighted",
            "highlight_type",
            "highlight_note",
            "highlighted_at",
            "highlighted_by",
        ):
            batch.drop_column(field)
    op.drop_column("projects", "enabled_capabilities")
