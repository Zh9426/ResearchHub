"""实际 PostgreSQL/MinIO foundation 验收；只写明确 SYNTHETIC QA 数据。"""
# ruff: noqa: F811 - pytest registers the imported live fixture by name.
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from test_live_system import create, live  # noqa: F401


def test_real_frozen_module_authority_and_recovery(live):
    project = create(live, "/api/projects", {"name": "SYNTHETIC v02 foundation " + uuid.uuid4().hex[:6], "module_id": "hdsp"})
    pid = project["id"]
    assert project["module_version"] == project["module_snapshot"]["version"]
    run = create(live, f"/api/projects/{pid}/runs", {"title": "SYNTHETIC negative", "run_type": "acoustic_simulation",
        "status": "completed", "scientific_outcome": "negative_result", "human_conclusion": "SYNTHETIC QA only"})
    token = create(live, "/api/auth/tokens", {"name": "SYNTHETIC authority probe", "actor_type": "codex",
        "scopes": ["research:read", "research:write"]})
    live.headers["Authorization"] = "Bearer " + token["token"]
    try:
        assert live.patch(f'/api/runs/{run["id"]}', json={"human_conclusion": "AI forbidden"}).status_code == 403
        assert live.post(f'/api/runs/{run["id"]}/parameters', json={"name": "pressure", "value": None, "is_confirmed": True}).status_code == 403
        assert live.post(f'/api/projects/{pid}/evidence', json={"title": "AI forbidden", "status": "validated"}).status_code == 403
        proposed = create(live, f"/api/projects/{pid}/evidence", {"title": "SYNTHETIC proposed"})
        assert proposed["status"] == "proposed"
        assert live.delete(f'/api/runs/{run["id"]}').status_code == 403
    finally:
        del live.headers["Authorization"]
        assert live.delete(f'/api/auth/tokens/{token["id"]}').status_code == 200
    assert live.delete(f'/api/runs/{run["id"]}').status_code == 200
    assert live.get(f'/api/runs/{run["id"]}').status_code == 404
    assert live.post(f'/api/lifecycle/runs/{run["id"]}/purge', json={"confirm": True}).status_code == 409
    assert live.patch(f'/api/lifecycle/runs/{run["id"]}', json={"action": "restore"}).status_code == 200
    recovered = live.get(f'/api/runs/{run["id"]}').json()
    assert recovered["scientific_outcome"] == "negative_result" and recovered["status"] == "completed"
    assert any(entry["action"] == "restore_runs" for entry in live.get("/api/activity").json())


def test_real_pg_audit_append_only_and_object_gc(live):
    if os.getenv("HUB_COMPOSE_RECOVERY") != "1":
        pytest.skip("Requires explicit QA-only database access")
    config = dict(line.split("=", 1) for line in Path(".env.qa").read_text().splitlines() if "=" in line)
    engine = create_engine(URL.create("postgresql+psycopg", username=config["POSTGRES_USER"],
        password=config["POSTGRES_PASSWORD"], host="127.0.0.1", port=35432, database=config["POSTGRES_DB"]))
    project = create(live, "/api/projects", {"name": "SYNTHETIC GC " + uuid.uuid4().hex[:6], "module_id": "generic"})
    pid = project["id"]
    upload = live.post(f"/api/projects/{pid}/artifacts", files={"file": ("synthetic.txt", b"SYNTHETIC QA GC", "text/plain")}, data={"category": "data"})
    assert upload.status_code in (200, 201)
    artifact = upload.json()
    assert live.delete(f"/api/artifacts/{artifact['id']}").status_code == 200
    from apps.api.researchhub.models import now
    with engine.begin() as db:
        # 仅模拟该 SYNTHETIC fixture 的保留期，不允许 API 客户端修改此字段。
        db.execute(text("UPDATE artifacts SET trashed_at=:stamp WHERE id=:id"), {"stamp": now()-timedelta(days=31), "id": artifact["id"]})
    assert live.post(f"/api/lifecycle/artifacts/{artifact['id']}/purge", json={"confirm": True}).status_code == 200
    queue = live.get("/api/storage/gc-preview").json()["items"]
    assert any(row["object_key"] == artifact["object_key"] for row in queue)
    result = live.post("/api/storage/gc", json={"confirm": True, "object_keys": [artifact["object_key"]]})
    assert result.status_code == 200 and result.json()["deleted"] == 1
    with pytest.raises(DBAPIError), engine.begin() as db:
        db.execute(text("DELETE FROM audit_logs WHERE project_id=:pid"), {"pid": pid})
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE project_id=:pid"), {"pid": pid}) > 0
    engine.dispose()
