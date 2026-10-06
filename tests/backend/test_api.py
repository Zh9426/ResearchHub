"""Fast API service tests use isolated SQLite only; production uses PostgreSQL."""

import hashlib
import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from apps.api.researchhub.main import create_app

    app = create_app(database_url=f"sqlite:///{tmp_path / 'unit.db'}", initialize=True)

    class Objects:
        def __init__(self):
            self.data = {}

        def put(self, key, stream, size, mime):
            self.data[key] = stream.read()

        def get(self, key):
            return io.BytesIO(self.data[key])

        def delete(self, key):
            self.data.pop(key, None)

    app.state.objects = Objects()
    with TestClient(app) as c:
        yield c


def login(client):
    r = client.post(
        "/api/auth/setup",
        json={
            "email": "owner@example.test",
            "password": "research-test-password",
            "display_name": "Owner",
        },
    )
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r.json()


def project(client, module="generic"):
    r = client.post("/api/projects", json={"name": "Test project", "module_id": module})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def run(client, pid, **extra):
    r = client.post(
        f"/api/projects/{pid}/runs",
        json={"title": "Simulation", "run_type": "simulation", **extra},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_auth_owner_csrf_and_setup(client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/auth/status").json()["setup_required"]
    login(client)
    assert not client.get("/api/auth/status").json()["setup_required"]
    assert (
        client.post(
            "/api/auth/setup",
            json={"email": "second@test.org", "password": "long-valid-password"},
        ).status_code
        == 409
    )
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            "/api/projects", json={"name": "Denied", "module_id": "generic"}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    pid = project(client)
    assert client.get(f"/api/projects/{pid}").status_code == 200
    assert client.get("/api/projects/not-an-id").status_code in (404, 422)
    client.post("/api/auth/logout")
    assert client.get(f"/api/projects/{pid}").status_code == 401


def test_modules_runs_provenance_crud_and_audit(client):
    login(client)
    modules = client.get("/api/modules").json()
    assert {m["id"] for m in modules} == {"generic", "hdsp", "ice-sonocuring"}
    pid = project(client)
    parent = run(client, pid)
    child = run(
        client,
        pid,
        parent_run_id=parent,
        scientific_outcome="negative_result",
        status="completed",
    )
    r = client.post(
        f"/api/runs/{child}/parameters",
        json={
            "name": "unknown temperature",
            "value": None,
            "source_kind": "unknown",
            "value_type": "number",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] is None
    metric = client.post(
        f"/api/runs/{child}/metrics", json={"name": "Score", "value": 0.3}
    ).json()
    assert (
        client.patch(f"/api/metrics/{metric['id']}", json={"value": 0.4}).json()[
            "value"
        ]
        == 0.4
    )
    assert (
        client.patch(f"/api/runs/{parent}", json={"parent_run_id": child}).status_code
        == 422
    )
    context = client.get(f"/api/runs/{child}/context").json()
    assert context["parent"]["id"] == parent
    assert context["run"]["scientific_outcome"] == "negative_result"
    other = project(client)
    assert (
        client.post(
            f"/api/projects/{other}/runs",
            json={"title": "Bad", "run_type": "simulation", "parent_run_id": child},
        ).status_code
        == 422
    )
    assert client.get("/api/activity").json()
    assert client.delete(f"/api/metrics/{metric['id']}").status_code == 200


def test_evidence_claim_gate_and_foreign_links(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    other = project(client)
    rid = run(client, pid, run_type="numerical_validation")
    e = client.post(
        f"/api/projects/{pid}/evidence",
        json={
            "title": "SYNTHETIC evidence",
            "status": "synthetic",
            "linked_run_id": rid,
        },
    ).json()
    claim = client.post(
        f"/api/projects/{pid}/claims",
        json={
            "statement": "Demonstration only",
            "evidence_ids": [e["id"]],
            "run_ids": [rid],
        },
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["evidence_ids"] == [e["id"]]
    assert (
        client.post(
            f"/api/projects/{other}/claims",
            json={"statement": "Cross project", "evidence_ids": [e["id"]]},
        ).status_code
        == 422
    )
    gates = client.get(f"/api/projects/{pid}/gates").json()
    gate = gates[0]
    assert (
        client.patch(f"/api/gates/{gate['id']}", json={"status": "passed"}).status_code
        == 422
    )
    criteria = [
        {**c, "status": "passed", "evidence_ids": [e["id"]]} for c in gate["criteria"]
    ]
    assert (
        client.patch(
            f"/api/gates/{gate['id']}",
            json={"status": "passed", "criteria": criteria, "evidence_ids": [e["id"]]},
        ).status_code
        == 200
    )


def test_upload_checksum_validation_and_scopes(client):
    login(client)
    pid = project(client)
    data = b"parameter,value\nfrequency,unknown\n"
    r = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("test.csv", data, "text/csv")},
        data={"category": "data"},
    )
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["checksum"] == hashlib.sha256(data).hexdigest()
    assert client.get(f"/api/artifacts/{a['id']}/download").content == data
    assert (
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("../evil.exe", b"x", "application/octet-stream")},
            data={"category": "data"},
        ).status_code
        == 422
    )
    token = client.post(
        "/api/auth/tokens",
        json={"name": "MCP read", "scopes": ["research:read"], "actor_type": "codex"},
    ).json()
    client.cookies.clear()
    client.headers["Authorization"] = "Bearer " + token["token"]
    assert client.get("/api/projects").status_code == 200
    assert (
        client.post(
            f"/api/projects/{pid}/notes", json={"title": "Denied", "content": "x"}
        ).status_code
        == 403
    )


def test_entity_validation_tasks_seed_and_unknown_source(client):
    login(client)
    pid = project(client)
    milestone = client.post(
        f"/api/projects/{pid}/milestones", json={"title": "M"}
    ).json()
    task = client.post(
        f"/api/projects/{pid}/tasks",
        json={"title": "T", "milestone_id": milestone["id"]},
    ).json()
    assert (
        client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()[
            "status"
        ]
        == "done"
    )
    assert (
        client.post(
            f"/api/projects/{pid}/tasks", json={"title": "T", "status": "invented"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{pid}/sources",
            json={"title": "Unknown", "source_kind": "unknown"},
        ).json()["source_kind"]
        == "unknown"
    )
    assert client.post("/api/demo/seed").status_code == 200
    assert client.post("/api/demo/seed").status_code == 200
    assert len(client.get("/api/projects").json()) == 4


def test_multi_owner_authorization(client):
    from apps.api.researchhub import models as m
    from apps.api.researchhub.main import password_hash

    login(client)
    pid = project(client)
    rid = run(client, pid)
    with client.app.state.session_factory() as db:
        other = m.User(
            email="other@example.test",
            password_hash=password_hash("second-research-password"),
            display_name="Other",
        )
        db.add(other)
        db.commit()
    client.post("/api/auth/logout")
    auth = client.post(
        "/api/auth/login",
        json={"email": "other@example.test", "password": "second-research-password"},
    ).json()
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
    assert client.get("/api/projects").json() == []
    for path in (
        f"/api/projects/{pid}",
        f"/api/projects/{pid}/context",
        f"/api/runs/{rid}",
        f"/api/runs/{rid}/context",
    ):
        assert client.get(path).status_code == 404
    assert client.patch(f"/api/runs/{rid}", json={"title": "Stolen"}).status_code == 404
    assert (
        client.post(
            f"/api/runs/{rid}/metrics", json={"name": "Stolen", "value": 1}
        ).status_code
        == 404
    )


def test_cross_project_relationships_and_deletion(client):
    login(client)
    a, b = project(client), project(client)
    ar, br = run(client, a), run(client, b)
    source = client.post(
        f"/api/projects/{b}/sources", json={"title": "Other source"}
    ).json()
    assert (
        client.post(
            f"/api/runs/{ar}/parameters", json={"name": "P", "source_id": source["id"]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{a}/notes", json={"title": "Bad", "run_id": br}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{a}/evidence", json={"title": "Bad", "linked_run_id": br}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{a}/artifacts",
            files={"file": ("x.txt", b"x", "text/plain")},
            data={"category": "data", "run_id": br},
        ).status_code
        == 422
    )
    child = run(client, a, parent_run_id=ar)
    assert client.delete(f"/api/runs/{ar}").status_code == 200
    assert client.get(f"/api/runs/{child}").json()["parent_run_id"] == ar
    # Reversible trash preserves lineage rather than changing the scientific graph.
    assert client.get(f"/api/runs/{ar}").status_code == 404
    assert client.delete(f"/api/projects/{a}").status_code == 200
    assert client.get(f"/api/runs/{child}").status_code == 404


def test_upload_checksum_size_mime_and_artifact_metadata(client, monkeypatch):
    login(client)
    pid = project(client)
    assert (
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("fake.png", b"not a png", "image/png")},
            data={"category": "figure"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("a.csv", b"abc", "image/png")},
            data={"category": "data"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("a.txt", b"abc", "text/plain")},
            data={"category": "data", "checksum": "bad"},
        ).status_code
        == 422
    )
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    assert (
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("a.txt", b"abcde", "text/plain")},
            data={"category": "data"},
        ).status_code
        == 413
    )
    a = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("a.txt", b"abcd", "text/plain")},
        data={"category": "data", "metadata": '{"label":"synthetic"}'},
    ).json()
    metadata = client.get(f"/api/artifacts/{a['id']}")
    assert metadata.status_code == 200
    assert metadata.json()["metadata"]["label"] == "synthetic"


def test_trusted_mcp_actor_and_atomic_metric_batch(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    token = client.post(
        "/api/auth/tokens",
        json={
            "name": "MCP write",
            "scopes": ["research:read", "research:write"],
            "actor_type": "codex",
        },
    ).json()
    client.cookies.clear()
    client.headers["Authorization"] = "Bearer " + token["token"]
    client.headers["X-Actor-Type"] = "human"
    r = client.post(
        f"/api/runs/{rid}/metrics/batch",
        json={
            "metrics": [
                {"name": "good", "value": 1},
                {"name": "bad", "value": 2, "metric_schema_id": "not-present"},
            ]
        },
    )
    assert r.status_code == 422
    assert client.get(f"/api/runs/{rid}/metrics").json() == []
    assert (
        client.post(
            f"/api/projects/{pid}/notes",
            json={"title": "Automated", "content": "SYNTHETIC"},
        ).status_code
        == 200
    )
    audit = client.get("/api/activity").json()[0]
    assert audit["actor_type"] == "codex" and audit["source"] == "mcp"
    assert (
        client.post(
            "/api/auth/tokens", json={"name": "esc", "scopes": ["research:write"]}
        ).status_code
        == 403
    )
    client.headers.pop("Authorization")
    auth = client.post(
        "/api/auth/login",
        json={"email": "owner@example.test", "password": "research-test-password"},
    ).json()
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
    assert client.delete("/api/auth/tokens/" + token["id"]).status_code == 200
    client.cookies.clear()
    client.headers["Authorization"] = "Bearer " + token["token"]
    assert client.get("/api/projects").status_code == 401


def test_gate_unknown_criterion_evidence_rejected(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    unknown = client.post(
        f"/api/projects/{pid}/evidence", json={"title": "Not established"}
    ).json()
    valid = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "Validation", "status": "validated"},
    ).json()
    gate = client.get(f"/api/projects/{pid}/gates").json()[0]
    criteria = [
        {**c, "status": "passed", "evidence_ids": [unknown["id"]]}
        for c in gate["criteria"]
    ]
    assert (
        client.patch(
            f"/api/gates/{gate['id']}",
            json={
                "criteria": criteria,
                "status": "passed",
                "evidence_ids": [valid["id"]],
            },
        ).status_code
        == 422
    )


def passed_gate(client, pid, criterion_evidence, gate_evidence):
    gate = client.get(f"/api/projects/{pid}/gates").json()[0]
    criteria = [
        {**c, "status": "passed", "evidence_ids": criterion_evidence}
        for c in gate["criteria"]
    ]
    response = client.patch(
        f"/api/gates/{gate['id']}",
        json={"status": "passed", "criteria": criteria, "evidence_ids": gate_evidence},
    )
    assert response.status_code == 200, response.text
    return client.get(f"/api/gates/{gate['id']}").json()


@pytest.mark.parametrize(
    "mutation", ["unknown", "hypothesis", "assumed", "rejected", "delete"]
)
@pytest.mark.parametrize("criterion_link", [True, False])
def test_evidence_invalidation_reopens_gate_with_audit(
    client, mutation, criterion_link
):
    login(client)
    pid = project(client, "ice-sonocuring")
    target = client.post(
        f"/api/projects/{pid}/evidence", json={"title": "Target", "status": "validated"}
    ).json()
    independent = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "Independent", "status": "measured"},
    ).json()
    gate = passed_gate(
        client,
        pid,
        [target["id"]] if criterion_link else [independent["id"]],
        [independent["id"]] if criterion_link else [target["id"]],
    )
    if mutation == "delete":
        response = client.delete(f"/api/evidence/{target['id']}")
    else:
        response = client.patch(
            f"/api/evidence/{target['id']}", json={"status": mutation}
        )
    assert response.status_code == 200, response.text
    changed = client.get(f"/api/gates/{gate['id']}").json()
    assert changed["status"] == "blocked"
    assert target["id"] in changed["blocking_reason"]
    assert {c["status"] for c in changed["criteria"]} == {
        "in_progress" if criterion_link else "passed"
    }
    audit = client.get("/api/activity").json()
    gate_change = next(a for a in audit if a["action"] == "invalidate_gate_evidence")
    assert gate_change["before"] == gate
    # SQLite reloads timestamps without offsets; compare the persisted research state.
    assert {k: v for k, v in gate_change["after"].items() if k != "updated_at"} == {
        k: v for k, v in changed.items() if k != "updated_at"
    }
    assert gate_change["project_id"] == pid
    assert gate_change["request_id"] == response.headers["X-Request-ID"]
    assert gate_change["actor_type"] == "human" and gate_change["source"] == "web"
    criterion_changes = [a for a in audit if a["action"] == "reopen_gate_criterion"]
    if criterion_link:
        assert len(criterion_changes) == len(gate["criteria"])
        assert all(a["before"]["status"] == "passed" for a in criterion_changes)
        assert all(a["after"]["status"] == "in_progress" for a in criterion_changes)
        assert all(a["project_id"] == pid for a in criterion_changes)
        assert all(
            a["request_id"] == response.headers["X-Request-ID"]
            for a in criterion_changes
        )
        if mutation == "delete":
            assert all(
                a["before"]["evidence_ids"] == [target["id"]] for a in criterion_changes
            )
            assert all(
                a["after"]["evidence_ids"] == [target["id"]] for a in criterion_changes
            )
    else:
        assert criterion_changes == []


def test_trashing_supporting_evidence_preserves_links_but_requires_reapproval(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    evidence = [
        client.post(
            f"/api/projects/{pid}/evidence",
            json={"title": title, "status": "validated"},
        ).json()["id"]
        for title in ("First", "Retained")
    ]
    gate = passed_gate(client, pid, evidence, evidence)
    assert client.delete(f"/api/evidence/{evidence[0]}").status_code == 200
    retained = client.get(f"/api/gates/{gate['id']}").json()
    assert retained["status"] == "blocked" and set(retained["evidence_ids"]) == set(
        evidence
    )
    assert all(
        c["status"] == "in_progress" and set(c["evidence_ids"]) == set(evidence)
        for c in retained["criteria"]
    )
    assert any(
        a["action"] == "invalidate_gate_evidence"
        for a in client.get("/api/activity").json()
    )
    assert [e["id"] for e in client.get(f"/api/projects/{pid}/evidence").json()] == [
        evidence[1]
    ]


def test_rejecting_one_of_multiple_evidence_invalidates_passage(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    evidence = [
        client.post(
            f"/api/projects/{pid}/evidence",
            json={"title": title, "status": "validated"},
        ).json()["id"]
        for title in ("Rejected", "Retained")
    ]
    gate = passed_gate(client, pid, evidence, evidence)
    assert (
        client.patch(
            f"/api/evidence/{evidence[0]}", json={"status": "rejected"}
        ).status_code
        == 200
    )
    changed = client.get(f"/api/gates/{gate['id']}").json()
    assert changed["status"] == "blocked"
    assert all(c["status"] == "in_progress" for c in changed["criteria"])


def test_valid_evidence_updates_do_not_reopen_gate(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    evidence = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "Evidence", "status": "validated"},
    ).json()
    gate = passed_gate(client, pid, [evidence["id"]], [evidence["id"]])
    for payload in ({"description": "Clarified scope"}, {"status": "reproduced"}):
        assert (
            client.patch(f"/api/evidence/{evidence['id']}", json=payload).status_code
            == 200
        )
        assert client.get(f"/api/gates/{gate['id']}").json() == gate


def test_evidence_and_gate_changes_rollback_together_on_audit_failure(
    client, monkeypatch
):
    from apps.api.researchhub import service as svc

    login(client)
    pid = project(client, "ice-sonocuring")
    evidence = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "Evidence", "status": "validated"},
    ).json()
    gate = passed_gate(client, pid, [evidence["id"]], [evidence["id"]])
    original = svc.audit
    evidence = client.get(f"/api/evidence/{evidence['id']}").json()

    def fail_gate_audit(db, actor, request, action, obj, before=None):
        if action == "invalidate_gate_evidence":
            raise RuntimeError("Audit persistence failure")
        return original(db, actor, request, action, obj, before)

    monkeypatch.setattr(svc, "audit", fail_gate_audit)
    with pytest.raises(RuntimeError, match="Audit persistence failure"):
        client.patch(f"/api/evidence/{evidence['id']}", json={"status": "rejected"})
    assert client.get(f"/api/evidence/{evidence['id']}").json() == evidence
    assert client.get(f"/api/gates/{gate['id']}").json() == gate


def test_chunked_request_without_content_length_is_bounded_and_replayed(
    client, monkeypatch
):
    login(client)
    pid = project(client)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    oversized = client.post(
        f"/api/projects/{pid}/artifacts",
        content=(chunk for chunk in (b"a" * 524288, b"b" * 524288, b"12345")),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert "Content-Length" not in oversized.request.headers
    assert oversized.status_code == 413
    accepted = client.post(
        "/api/projects",
        content=(chunk for chunk in (b'{"name":"Chunked",', b'"module_id":"generic"}')),
        headers={"Content-Type": "application/json"},
    )
    assert "Content-Length" not in accepted.request.headers
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["name"] == "Chunked"


def test_request_body_cap_before_multipart_parse(client, monkeypatch):
    login(client)
    pid = project(client)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    r = client.post(
        f"/api/projects/{pid}/artifacts",
        content=b"x" * (1048576 + 5),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 413


def test_strict_payload_and_parameter_types(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    assert (
        client.post(
            f"/api/runs/{rid}/parameters",
            json={"name": "bad", "value": "invented", "value_type": "number"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{pid}/tasks", json={"title": "T", "owner_id": "spoof"}
        ).status_code
        == 422
    )
    assert (
        client.patch(f"/api/projects/{pid}", json={"module_id": "hdsp"}).status_code
        == 422
    )


def test_run_difference_includes_units_sources_added_and_removed(client):
    login(client)
    pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    source = client.post(
        f"/api/projects/{pid}/sources",
        json={"title": "Measured source", "source_kind": "measured"},
    ).json()
    client.post(
        f"/api/runs/{parent}/parameters",
        json={"name": "pressure", "value": 1, "unit": "Pa", "source_kind": "assumed"},
    )
    client.post(
        f"/api/runs/{child}/parameters",
        json={
            "name": "pressure",
            "value": 1,
            "unit": "kPa",
            "source_kind": "measured",
            "source_id": source["id"],
            "source_location": "page 2",
        },
    )
    client.post(f"/api/runs/{parent}/parameters", json={"name": "removed", "value": 5})
    client.post(f"/api/runs/{child}/parameters", json={"name": "added", "value": 7})
    changes = {
        p["name"]: p
        for p in client.get(f"/api/runs/{child}/context").json()["changes_from_parent"][
            "parameters"
        ]
    }
    assert changes["pressure"]["parent"] == changes["pressure"]["current"] == 1
    assert changes["pressure"]["fields"]["unit"] == {"parent": "Pa", "current": "kPa"}
    assert changes["pressure"]["fields"]["source_kind"] == {
        "parent": "assumed",
        "current": "measured",
    }
    assert changes["pressure"]["fields"]["source_id"]["current"] == source["id"]
    assert (
        changes["removed"]["change_type"] == "removed"
        and changes["removed"]["current"] is None
    )
    assert (
        changes["added"]["change_type"] == "added"
        and changes["added"]["parent"] is None
    )


def test_login_attempt_limit_is_bounded(client, monkeypatch):
    monkeypatch.setenv("LOGIN_ATTEMPT_LIMIT", "2")
    login(client)
    client.post("/api/auth/logout")
    bad = {"email": "owner@example.test", "password": "wrong-long-password"}
    assert client.post("/api/auth/login", json=bad).status_code == 401
    assert client.post("/api/auth/login", json=bad).status_code == 401
    limited = client.post("/api/auth/login", json=bad)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
