"""One-time initial revision generator; emits a frozen schema, no live model imports."""

from pathlib import Path

from .models import Base


def main():
    result = [
        '"""RH v0.1 initial relational schema (frozen)."""',
        "from alembic import op",
        "import sqlalchemy as sa",
        "revision = '0001_core'",
        "down_revision = None",
        "branch_labels = None",
        "depends_on = None",
        "def upgrade():",
    ]
    for table in Base.metadata.sorted_tables:
        result.append(f"    op.create_table({table.name!r},")
        for c in table.columns:
            args = [repr(c.name), "sa." + repr(c.type)]
            for fk in c.foreign_keys:
                args.append(
                    f"sa.ForeignKey({fk.target_fullname!r}, ondelete={fk.ondelete!r})"
                )
            args.extend([f"nullable={c.nullable!r}", f"primary_key={c.primary_key!r}"])
            if c.unique:
                args.append("unique=True")
            result.append("        sa.Column(" + ", ".join(args) + "),")
        result.append("    )")
        for index in table.indexes:
            result.append(
                f"    op.create_index({index.name!r}, {table.name!r}, {[c.name for c in index.columns]!r}, unique={index.unique!r})"
            )
    result.append("def downgrade():")
    for table in reversed(Base.metadata.sorted_tables):
        result.append(f"    op.drop_table({table.name!r})")
    path = Path("infrastructure/migrations/versions/0001_core.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
