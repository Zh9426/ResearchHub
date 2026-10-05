"""Alembic revision is exercised against isolated SQLite, never called production validation."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_frozen_migration_upgrade_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("infrastructure/migrations/alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    tables = inspect(engine).get_table_names()
    assert (
        "research_runs" in tables
        and "claims_evidence_ids" in tables
        and "gate_criteria_evidence_ids" in tables
    )
    from apps.api.researchhub.models import Base

    assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
