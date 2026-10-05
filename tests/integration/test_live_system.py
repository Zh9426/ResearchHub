"""Explicit opt-in acceptance against a disposable, real PostgreSQL/S3 deployment.

Set HUB_LIVE_URL and HUB_QA_CREDENTIALS_FILE. Never run against personal research data.
These tests create visibly SYNTHETIC records and preserve a persistence probe.
"""

import hashlib
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="session")
def live():
    url = os.getenv("HUB_LIVE_URL")
    credentials_path = os.getenv("HUB_QA_CREDENTIALS_FILE")
    if not url or not credentials_path:
        pytest.skip("Live PostgreSQL/MinIO acceptance requires explicit disposable QA deployment")
    credentials = json.loads(Path(credentials_path).read_text(encoding="utf-8-sig"))
    with httpx.Client(base_url=url.rstrip("/"), timeout=60, trust_env=False) as client:
        state = client.get("/api/auth/status")
        assert state.status_code == 200, state.text
        path = "/api/auth/setup" if state.json()["setup_required"] else "/api/auth/login"
        response = client.post(path, json=credentials)
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield client


def create(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


@pytest.mark.parametrize("module_id", ["generic", "hdsp", "ice-sonocuring"])
def test_real_module_workspace(live, module_id):
    manifest = live.get(f"/api/modules/{module_id}").json()
    project = create(live, "/api/projects", {
        "name": f"SYNTHETIC acceptance {module_id} {uuid.uuid4().hex[:6]}",
        "module_id": module_id,
        "description": "Disposable QA; no research conclusions.",
    })
    context = live.get(f"/api/projects/{project['id']}/context").json()
    assert context["module"]["id"] == module_id
    assert len(context["gates"]) == len(manifest["stage_gates"])
    if module_id == "generic":
        assert "frequency" not in {entry["id"] for entry in manifest["parameter_schemas"]}
    if module_id == "ice-sonocuring":
        assert {gate["gate_id"] for gate in context["gates"]} == {f"G{i}" for i in range(6)}
    stage_id = manifest["research_stages"][0]["id"]
    response = live.patch(f"/api/projects/{project['id']}", json={"current_stage": stage_id})
    assert response.status_code == 200, response.text
    assert response.json()["current_stage"] == stage_id


def test_complete_scientific_workflow_and_real_object_storage(live):
    project = create(live, "/api/projects", {
        "name": f"SYNTHETIC persistence probe {uuid.uuid4().hex[:6]}",
        "module_id": "generic",
    })
    pid = project["id"]
    question = create(live, f"/api/projects/{pid}/questions", {"title": "Is this QA workflow reproducible?"})
    hypothesis = create(live, f"/api/projects/{pid}/hypotheses", {
        "statement": "SYNTHETIC hypothesis only",
        "research_question_id": question["id"],
    })
    assert hypothesis["evidence_status"] == "hypothesis"
    parent = create(live, f"/api/projects/{pid}/runs", {
        "title": "SYNTHETIC baseline", "run_type": "simulation", "status": "completed",
        "human_conclusion": "QA baseline, no scientific result",
    })
    child = create(live, f"/api/projects/{pid}/runs", {
        "title": "SYNTHETIC child, negative result", "run_type": "simulation",
        "parent_run_id": parent["id"], "status": "completed",
        "scientific_outcome": "negative_result", "changes_from_parent": "QA sample value changed",
        "environment": "Disposable local PostgreSQL + MinIO QA",
        "software_version": "Research Hub v0.1", "code_revision": "QA",
        "observation": "Synthetic observation", "ai_analysis": "Unverified AI interpretation",
        "human_conclusion": "No distinguishable difference in this synthetic example",
    })
    parameter = create(live, f"/api/runs/{child['id']}/parameters", {
        "name": "unknown input", "value": None, "value_type": "number", "unit": "unit",
        "source_kind": "unknown", "is_confirmed": False,
    })
    assert parameter["value"] is None and parameter["source_kind"] == "unknown"
    source = create(live, f"/api/projects/{pid}/sources", {
        "title": "SYNTHETIC QA source", "source_kind": "synthetic", "citation": "Acceptance test fixture",
    })
    create(live, f"/api/runs/{parent['id']}/parameters", {
        "name": "sample", "value": 1, "value_type": "number", "source_kind": "synthetic",
        "source_id": source["id"], "source_location": "test fixture", "uncertainty": "not applicable",
        "valid_conditions": "QA only",
    })
    create(live, f"/api/runs/{child['id']}/parameters", {
        "name": "sample", "value": 2, "value_type": "number", "source_kind": "synthetic",
    })
    metric = create(live, f"/api/runs/{child['id']}/metrics", {
        "name": "QA score", "value": 0.25, "status": "synthetic",
    })
    response = live.patch(f"/api/metrics/{metric['id']}", json={"value": 0.5})
    assert response.status_code == 200 and response.json()["value"] == 0.5
    payload = b'{"status":"SYNTHETIC","purpose":"durability probe"}\n'
    upload = live.post(f"/api/projects/{pid}/artifacts", files={
        "file": ("synthetic-probe.json", payload, "application/json"),
    }, data={"run_id": child["id"], "category": "data", "metadata": '{"synthetic":true}'})
    assert upload.status_code in (200, 201), upload.text
    artifact = upload.json()
    assert artifact["checksum"] == hashlib.sha256(payload).hexdigest()
    assert artifact["size"] == len(payload)
    assert live.get(f"/api/artifacts/{artifact['id']}/download").content == payload
    evidence = create(live, f"/api/projects/{pid}/evidence", {
        "title": "SYNTHETIC evidence", "status": "synthetic", "evidence_type": "simulation",
        "linked_run_id": child["id"], "linked_artifact_id": artifact["id"],
        "linked_source_id": source["id"], "limitations": "Only a software acceptance fixture",
    })
    claim = create(live, f"/api/projects/{pid}/claims", {
        "title": "SYNTHETIC claim", "statement": "Only the QA linkage works",
        "evidence_ids": [evidence["id"]], "run_ids": [child["id"]],
        "artifact_ids": [artifact["id"]], "source_ids": [source["id"]],
    })
    assert claim["evidence_ids"] == [evidence["id"]]
    milestone = create(live, f"/api/projects/{pid}/milestones", {"title": "SYNTHETIC QA milestone"})
    task = create(live, f"/api/projects/{pid}/tasks", {
        "title": "SYNTHETIC verify durability", "milestone_id": milestone["id"], "priority": "high",
    })
    assert live.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()["status"] == "done"
    create(live, f"/api/projects/{pid}/notes", {
        "title": "SYNTHETIC QA note", "content": "Private local record", "run_id": child["id"],
    })
    create(live, f"/api/projects/{pid}/decisions", {
        "title": "SYNTHETIC candidate rejection", "decision": "Keep the negative result",
        "reason": "Research outcome differs from execution failure", "alternatives": "Discarding results",
        "context": "QA only", "run_id": child["id"], "evidence_ids": [evidence["id"]],
    })
    context = live.get(f"/api/runs/{child['id']}/context").json()
    assert context["parent"]["id"] == parent["id"]
    assert context["run"]["status"] == "completed"
    assert context["run"]["scientific_outcome"] == "negative_result"
    assert live.get(f"/api/runs/{parent['id']}/context").json()["children"][0]["id"] == child["id"]
    audit = live.get("/api/activity").json()
    assert any(entry["action"] == "upload_artifact" for entry in audit)
    assert all("actor_type" in entry and "request_id" in entry for entry in audit)
    probe_path = Path(os.environ.get("HUB_PERSISTENCE_PROBE", "storage/persistence-probe.json"))
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    probe_path.write_text(json.dumps({
        "project_id": pid, "run_id": child["id"], "artifact_id": artifact["id"],
        "checksum": artifact["checksum"], "content": payload.decode(),
    }), encoding="utf-8")


def test_private_data_and_token_scope_boundary(live):
    project = create(live, "/api/projects", {"name": "SYNTHETIC token QA", "module_id": "generic"})
    with httpx.Client(base_url=str(live.base_url), trust_env=False) as anonymous:
        assert anonymous.get(f"/api/projects/{project['id']}").status_code == 401
        token = create(live, "/api/auth/tokens", {
            "name": "SYNTHETIC MCP read only", "scopes": ["research:read"], "actor_type": "codex",
        })
        anonymous.headers["Authorization"] = f"Bearer {token['token']}"
        assert anonymous.get("/api/projects").status_code == 200
        denied = anonymous.post(f"/api/projects/{project['id']}/notes", json={"title": "Must not persist"})
        assert denied.status_code == 403
    assert live.get("/api/projects/not-a-uuid").status_code in (404, 422)
    assert live.get(f"/api/runs/{uuid.uuid4()}").status_code == 404


def test_artifact_validation_is_enforced_by_real_api(live):
    project = create(live, "/api/projects", {"name": "SYNTHETIC upload QA", "module_id": "generic"})
    response = live.post(f"/api/projects/{project['id']}/artifacts", files={
        "file": ("../untrusted.exe", b"MZ", "application/octet-stream"),
    }, data={"category": "data"})
    assert response.status_code in (400, 422), response.text


def test_demo_seed_is_explicit_idempotent_and_labelled(live):
    first = live.post("/api/demo/seed")
    assert first.status_code == 200, first.text
    before = live.get("/api/projects").json()
    assert live.post("/api/demo/seed").status_code == 200
    after = live.get("/api/projects").json()
    assert len(after) == len(before)
    demos = [project for project in after if project.get("is_demo")]
    assert {project["module_id"] for project in demos} == {"generic", "hdsp", "ice-sonocuring"}


def test_real_evidence_rejection_invalidates_gate_atomically(live):
    project = create(live, "/api/projects", {"name": "SYNTHETIC gate integrity QA", "module_id": "ice-sonocuring"})
    evidence = create(live, f"/api/projects/{project['id']}/evidence", {
        "title": "SYNTHETIC status transition fixture", "status": "validated",
        "limitations": "Tests software status transitions, no scientific validation.",
    })
    gate = live.get(f"/api/projects/{project['id']}/gates").json()[0]
    payload = {"status": "passed", "evidence_ids": [evidence["id"]], "criteria": [
        {**criterion, "status": "passed", "evidence_ids": [evidence["id"]]} for criterion in gate["criteria"]
    ]}
    assert live.patch(f"/api/gates/{gate['id']}", json=payload).status_code == 200
    rejected = live.patch(f"/api/evidence/{evidence['id']}", json={"status": "rejected"})
    assert rejected.status_code == 200
    changed = live.get(f"/api/gates/{gate['id']}").json()
    assert changed["status"] == "blocked" and changed["blocking_reason"]
    assert all(c["status"] == "in_progress" for c in changed["criteria"])
    entries = live.get(f"/api/projects/{project['id']}/context").json()["activity"]
    assert any(a["action"] == "invalidate_gate_evidence" and a["before"]["status"] == "passed"
               and a["after"]["status"] == "blocked" for a in entries)
