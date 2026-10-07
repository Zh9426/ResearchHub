"""RH-006 metric provenance and trace indexes; previous revisions are immutable."""

import sqlalchemy as sa
from alembic import op

revision = "0004_intelligence"
down_revision = "0003_workflow"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("metrics") as batch:
        batch.add_column(
            sa.Column(
                "source_kind", sa.String(30), nullable=False, server_default="unknown"
            )
        )
        batch.add_column(sa.Column("source_id", sa.String(36), nullable=True))
        for name in (
            "source_location",
            "derivation",
            "uncertainty",
            "valid_conditions",
        ):
            batch.add_column(sa.Column(name, sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_metrics_source_id",
            "sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_metrics_source_id", ["source_id"])
    op.create_table(
        "metrics_artifact_ids",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_metrics_artifact_ids_target", "metrics_artifact_ids", ["target_id"]
    )
    op.create_index("ix_parameters_source_id", "parameters", ["source_id"])
    op.create_index(
        "ix_audit_resource_history",
        "audit_logs",
        ["owner_id", "resource_type", "resource_id", "timestamp"],
    )
    op.create_index("ix_evidence_source", "evidence", ["linked_source_id"])
    op.create_index("ix_evidence_artifact", "evidence", ["linked_artifact_id"])


def downgrade():
    op.drop_index("ix_evidence_artifact", "evidence")
    op.drop_index("ix_evidence_source", "evidence")
    op.drop_index("ix_audit_resource_history", "audit_logs")
    op.drop_index("ix_parameters_source_id", "parameters")
    op.drop_table("metrics_artifact_ids")
    with op.batch_alter_table("metrics") as batch:
        batch.drop_index("ix_metrics_source_id")
        batch.drop_constraint("fk_metrics_source_id", type_="foreignkey")
        for name in (
            "source_kind",
            "source_id",
            "source_location",
            "derivation",
            "uncertainty",
            "valid_conditions",
        ):
            batch.drop_column(name)
