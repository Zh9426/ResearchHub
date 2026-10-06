"""对已停止写入的个人原生数据库进行备份；凭据仅在进程内使用。"""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from scripts.backup_data import export_objects


def main():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "storage/runtime/native-env.json").read_text(encoding="utf-8-sig"))
    output = root / "storage/backups" / ("v01-baseline-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True)
    url = make_url(config["DATABASE_URL"])
    environment = {**os.environ, "PGPASSWORD": url.password or ""}
    result = subprocess.run([
        str(root / "storage/runtime/pgsql/bin/pg_dump.exe"),
        "-h", url.host or "127.0.0.1", "-p", str(url.port or 5432),
        "-U", url.username or "", "-d", url.database or "", "-Fc",
        "-f", str(output / "postgres.dump"),
    ], env=environment, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("PostgreSQL 备份失败；未输出可能含凭据的进程日志")
    for key in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        os.environ[key] = config[key]
    os.environ["S3_BUCKET"] = "researchhub"
    export_objects(output / "objects.zip")
    engine = create_engine(url)
    with engine.connect() as db:
        tables = inspect(engine).get_table_names()
        # 仅保存原有列，用于迁移后逐行比较；此文件与数据库备份一起被忽略。
        records = {name: [dict(row) for row in db.execute(text('SELECT * FROM "' + name + '"')).mappings()]
                   for name in tables if name != "alembic_version"}
    engine.dispose()
    (output / "before-rows.json").write_text(json.dumps(records, default=str), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(), "baseline": "3cf52e0b18c301a8180c01cfba58d96c33fd585a",
        "table_count": len(records), "row_count": sum(map(len, records.values())),
        "checksums": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                      for name in ("postgres.dump", "objects.zip", "before-rows.json")},
    }, indent=2), encoding="utf-8")
    print(f"本地备份完成：{output}；{len(records)} 张表；未输出科研内容或凭据。")


if __name__ == "__main__":
    main()
