"""Run separately after restarting the QA API, PostgreSQL and MinIO services."""

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest


def test_existing_run_and_artifact_survive_service_restart():
    url = os.getenv("HUB_LIVE_URL")
    credentials_path = os.getenv("HUB_QA_CREDENTIALS_FILE")
    if not url or not credentials_path or not os.getenv("HUB_CHECK_RESTART"):
        pytest.skip("Requires explicit post-restart acceptance invocation")
    credentials = json.loads(Path(credentials_path).read_text(encoding="utf-8-sig"))
    probe = json.loads(Path("storage/persistence-probe.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
        response = client.post("/api/auth/login", json=credentials)
        assert response.status_code == 200
        assert client.get("/api/health").json()["database"] == "postgresql"
        context = client.get(f"/api/runs/{probe['run_id']}/context")
        assert context.status_code == 200
        assert context.json()["run"]["scientific_outcome"] == "negative_result"
        artifact = client.get(f"/api/artifacts/{probe['artifact_id']}/download")
        assert artifact.status_code == 200
        assert artifact.content.decode() == probe["content"]
        assert hashlib.sha256(artifact.content).hexdigest() == probe["checksum"]
        audit = client.get("/api/activity").json()
        assert any(entry["resource_id"] == probe["artifact_id"] for entry in audit)
