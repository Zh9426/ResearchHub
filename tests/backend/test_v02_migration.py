"""Frozen revision/data preservation checks use an isolated database, not production."""

from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    MetaData,
    create_engine,
    select,
    text,
)
from sqlalchemy.exc import DatabaseError


def test_v01_all_relational_rows_preserved_and_frozen_definitions(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path / 'preserved.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("infrastructure/migrations/alembic.ini")
    command.upgrade(config, "0001_core")
    engine = create_engine(url)
    old = MetaData()
    old.reflect(engine)
    snapshots = {}
    identifiers = {
        name: f"{index:08}-0000-0000-0000-000000000000"
        for index, name in enumerate(old.tables, 1)
    }
    with engine.begin() as connection:
        for table in old.sorted_tables:
            if table.name == "alembic_version":
                continue
            values = {}
            for column in table.columns:
                if column.name == "id":
                    values[column.name] = identifiers[table.name]
                elif column.nullable:
                    values[column.name] = None
                elif column.foreign_keys:
                    values[column.name] = identifiers[
                        next(iter(column.foreign_keys)).column.table.name
                    ]
                elif isinstance(column.type, Boolean):
                    values[column.name] = False
                elif isinstance(column.type, Integer):
                    values[column.name] = 7
                elif isinstance(column.type, DateTime):
                    values[column.name] = datetime(2026, 10, 5, tzinfo=timezone.utc)
                elif isinstance(column.type, JSON):
                    values[column.name] = {
                        "baseline": ["unknown", None, "negative_result"]
                    }
                else:
                    values[column.name] = "baseline-" + column.name
            if table.name == "projects":
                values["module_id"] = "generic"
                values["status"] = "archived"
            if table.name == "research_runs":
                values.update(
                    run_type="simulation",
                    scientific_outcome="negative_result",
                    status="completed",
                )
            if table.name == "parameters":
                values.update(value=None, source_kind="unknown", is_confirmed=False)
            connection.execute(table.insert().values(**values))
            snapshots[table.name] = [
                dict(row._mapping) for row in connection.execute(select(table))
            ]
    # Changing runtime loader availability cannot affect deployed manifest interpretation.
    from apps.api.researchhub import modules

    monkeypatch.setattr(
        modules,
        "load_modules",
        lambda: (_ for _ in ()).throw(AssertionError("runtime manifest loaded")),
    )
    command.upgrade(config, "head")
    current = MetaData()
    current.reflect(engine)
    with engine.connect() as connection:
        for name, rows in snapshots.items():
            columns = [current.tables[name].c[key] for key in rows[0]]
            assert [
                dict(row._mapping) for row in connection.execute(select(*columns))
            ] == rows
        project = dict(
            connection.execute(select(current.tables["projects"])).one()._mapping
        )
        assert project["module_version"] == "0.1.0"
        assert project["module_snapshot"]["id"] == "generic"
        assert project["module_snapshot"]["version"] == "0.1.0"
        assert project["archived_at"] is not None
        assert project["trashed_at"] is None
        assert connection.scalar(text("SELECT COUNT(*) FROM object_deletions")) == 0
    for statement in (
        "UPDATE audit_logs SET action='tampered'",
        "DELETE FROM audit_logs",
    ):
        with pytest.raises(DatabaseError), engine.begin() as connection:
            connection.execute(text(statement))
    engine.dispose()


def test_postgres_offline_upgrade_contains_frozen_snapshot_and_append_only_trigger(
    tmp_path, monkeypatch
):
    import io

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://localhost/isolated_sql_generation"
    )
    output = io.StringIO()
    config = Config("infrastructure/migrations/alembic.ini", output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "module_snapshot" in sql and "module_version='0.1.0'" in sql
    assert "CREATE TRIGGER audit_logs_append_only" in sql
    assert "CREATE TABLE object_deletions" in sql
    assert "::json" in sql
