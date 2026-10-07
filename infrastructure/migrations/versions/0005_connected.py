"""RH-007 nullable saved code provenance; no external GitHub operations."""

import sqlalchemy as sa
from alembic import op

revision = "0005_connected"
down_revision = "0004_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("repository", sa.String(500), nullable=True))
    for name, length in (
        ("repository", 500),
        ("branch", 255),
        ("commit_sha", 40),
        ("issue_url", 500),
        ("pull_request_url", 500),
    ):
        op.add_column(
            "research_runs", sa.Column(name, sa.String(length), nullable=True)
        )


def downgrade():
    for name in ("pull_request_url", "issue_url", "commit_sha", "branch", "repository"):
        op.drop_column("research_runs", name)
    op.drop_column("projects", "repository")
