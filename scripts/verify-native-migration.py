"""迁移个人原生数据库，并逐行验证最近 v0.1 备份中的原有列；不输出内容。"""
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parents[1]
backups = sorted((root / "storage/backups").glob("v01-baseline-*"))
if not backups:
    raise RuntimeError("必须先建立 v0.1 基线备份")
baseline = backups[-1]
before = json.loads((baseline / "before-rows.json").read_text(encoding="utf-8"))
runtime = json.loads((root / "storage/runtime/native-env.json").read_text(encoding="utf-8-sig"))
os.environ["DATABASE_URL"] = runtime["DATABASE_URL"]
command.upgrade(Config(str(root / "infrastructure/migrations/alembic.ini")), "head")
engine = create_engine(runtime["DATABASE_URL"])
checked = 0
with engine.connect() as db:
    for table, rows in before.items():
        actual = [dict(row) for row in db.execute(text('SELECT * FROM "' + table + '"')).mappings()]
        actual = json.loads(json.dumps(actual, default=str))
        columns = list(rows[0]) if rows else []
        original_values = [{key: row[key] for key in columns} for row in actual]
        canonical = lambda values: sorted(json.dumps(row, sort_keys=True) for row in values)
        if canonical(rows) != canonical(original_values):
            raise RuntimeError(f"迁移保留检查失败：{table}；请保留备份并停止写入")
        checked += len(rows)
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
engine.dispose()
(baseline / "migration-verification.json").write_text(json.dumps({
    "status": "verified", "revision": revision, "tables": len(before), "original_rows": checked,
    "original_columns_preserved": True,
}, indent=2), encoding="utf-8")
print(f"Migration verified: {revision}; {len(before)} original tables, {checked} original rows preserved.")
