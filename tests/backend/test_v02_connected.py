"""Connected contract unit tests; isolated SQLite does not prove live services."""

from test_api import client as api_client
from test_api import login, project, run

from apps.api.researchhub import models as m

client = api_client
REPO = "https://github.com/Zh9426/ResearchHub"


def test_connected_reads_owner_scope_and_hidden_projects(client):
    login(client)
    pid = project(client)
    rid = run(client, pid, title="Private unique needle")
    foreign_pid = project(client)
    foreign_rid = run(client, foreign_pid, title="Foreign unique needle")
    with client.app.state.session_factory() as db:
        other = m.User(
            email="foreign@example.test",
            display_name="Foreign",
            password_hash="unusable",
        )
        db.add(other)
        db.flush()
        db.get(m.Project, foreign_pid).owner_id = other.id
        db.commit()
    token = client.post(
        "/api/auth/tokens",
        json={"name": "Read scope", "scopes": ["research:read"], "actor_type": "codex"},
    ).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    for endpoint in (
        f"/api/projects/{foreign_pid}/summary?format=page",
        f"/api/projects/{foreign_pid}/runs/query?active_only=true",
        f"/api/projects/{foreign_pid}/blockers",
        f"/api/runs/{foreign_rid}/context?format=page",
        f"/api/runs/{rid}/compare?other_run_id={foreign_rid}",
        f"/api/projects/{foreign_pid}/evidence-trace/runs/{foreign_rid}",
    ):
        assert client.get(endpoint).status_code == 404, endpoint
    searched = client.get(
        "/api/search", params={"q": "unique needle", "limit": 1}
    ).json()
    assert searched["total"] == 1 and searched["items"][0]["id"] == rid
    assert (
        client.get(f"/api/projects/{pid}/evidence-trace/runs/{foreign_rid}").status_code
        == 404
    )
    assert (
        client.post(
            f"/api/runs/{rid}/artifacts/register", json={"file_id": m.uid()}
        ).status_code
        == 403
    )
    client.headers.pop("Authorization")
    assert (
        client.patch(
            f"/api/lifecycle/projects/{pid}", json={"action": "archive"}
        ).status_code
        == 200
    )
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/projects?format=page").json()["total"] == 0
    assert client.get("/api/search?q=unique%20needle").json()["total"] == 0
    for endpoint in (
        f"/api/projects/{pid}/summary?format=page",
        f"/api/projects/{pid}/runs/query?active_only=true",
        f"/api/projects/{pid}/blockers",
        f"/api/runs/{rid}/context?format=page",
        f"/api/projects/{pid}/evidence-trace/runs/{rid}",
    ):
        assert client.get(endpoint).status_code == 404


def test_code_provenance_saved_validated_and_cloned(client):
    login(client)
    pid = project(client)
    response = client.patch(f"/api/projects/{pid}", json={"repository": REPO})
    assert response.status_code == 200, response.text
    assert response.json()["repository"] == REPO
    data = {
        "repository": REPO,
        "branch": "codex/researchhub-v0.2",
        "commit_sha": "a" * 40,
        "issue_url": REPO + "/issues/12",
        "pull_request_url": REPO + "/pull/14",
        "code_revision": "legacy revision",
    }
    rid = run(client, pid, **data)
    cloned = client.post(f"/api/runs/{rid}/clone", json={"title": "Child"}).json()
    for key, value in data.items():
        assert cloned[key] == value
    no_code = client.post(
        f"/api/runs/{rid}/clone", json={"title": "No code", "inherit_code": False}
    ).json()
    assert no_code["repository"] is None and no_code["commit_sha"] is None
    for invalid in (
        "http://github.com/a/b",
        "https://evil.test/a/b",
        "https://github.com/a/b?token=secret",
        "https://user:pass@github.com/a/b",
        "https://github.com/a/b/tree/main",
    ):
        assert (
            client.patch(
                f"/api/projects/{pid}", json={"repository": invalid}
            ).status_code
            == 422
        )
    assert (
        client.patch(f"/api/runs/{rid}", json={"commit_sha": "abcd"}).status_code == 422
    )
    assert (
        client.patch(
            f"/api/runs/{rid}",
            json={"issue_url": "https://github.com/other/repo/issues/1"},
        ).status_code
        == 422
    )

    fallback = run(client, pid, issue_url=REPO + "/issues/5")
    assert client.get(f"/api/runs/{fallback}").json()["repository"] == REPO
    assert (
        client.patch(
            f"/api/runs/{rid}", json={"repository": "https://github.com/other/repo"}
        ).status_code
        == 422
    )
    no_repo = project(client)
    assert (
        client.post(
            f"/api/projects/{no_repo}/runs",
            json={
                "title": "Unscoped",
                "run_type": "simulation",
                "issue_url": REPO + "/issues/1",
            },
        ).status_code
        == 422
    )


def test_connected_pages_and_legacy_arrays(client):
    login(client)
    pid = project(client)
    project(client)
    rid = run(client, pid)
    for i in range(3):
        client.post(f"/api/runs/{rid}/parameters", json={"name": f"p{i}", "value": i})
    projects = client.get("/api/projects?format=page&limit=1&offset=1").json()
    assert projects["total"] == 2 and len(projects["items"]) == 1
    assert isinstance(client.get("/api/projects").json(), list)
    context = client.get(f"/api/runs/{rid}/context?format=page&limit=1&offset=1").json()
    assert context["groups"]["parameters"]["total"] == 3
    assert len(context["groups"]["parameters"]["items"]) == 1
    assert isinstance(client.get(f"/api/runs/{rid}/context").json()["parameters"], list)
    summary = client.get(f"/api/projects/{pid}/summary?format=page&limit=1").json()
    assert summary["groups"]["recent_runs"]["total"] == 1
    for endpoint in (
        "/api/projects?format=page",
        f"/api/runs/{rid}/context?format=page",
        f"/api/projects/{pid}/summary?format=page",
    ):
        assert client.get(endpoint + "&limit=101").status_code == 422


def test_current_blockers_scoped_paged_and_lifecycle(client):
    login(client)
    pid = project(client)
    rid = run(client, pid, status="blocked")
    task = client.post(
        f"/api/projects/{pid}/tasks",
        json={"title": "Blocked task", "status": "blocked"},
    ).json()
    foreign = run(client, project(client), status="blocked")
    page = client.get(f"/api/projects/{pid}/blockers?limit=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert foreign not in str(page)
    assert (
        client.patch(
            f"/api/lifecycle/runs/{rid}", json={"action": "archive"}
        ).status_code
        == 200
    )
    client.delete(f"/api/tasks/{task['id']}")
    assert client.get(f"/api/projects/{pid}/blockers").json()["total"] == 0
    assert client.get(f"/api/runs/{rid}/context?format=page").status_code == 404


def test_safe_artifact_registration_and_ai_write_boundaries(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    file = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("data.csv", b"x,1", "text/csv")},
        data={"category": "data"},
    ).json()
    foreign = client.post(
        f"/api/projects/{project(client)}/artifacts",
        files={"file": ("other.csv", b"x,2", "text/csv")},
        data={"category": "data"},
    ).json()
    token = client.post(
        "/api/auth/tokens",
        json={
            "name": "AI",
            "scopes": ["research:read", "research:write"],
            "actor_type": "codex",
        },
    ).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    endpoint = f"/api/runs/{rid}/artifacts/register"
    registered = client.post(endpoint, json={"file_id": file["id"]})
    assert registered.status_code == 200, registered.text
    assert registered.json()["artifact"]["id"] == file["id"]
    assert (
        client.post(endpoint, json={"file_id": file["id"]}).json()["already_linked"]
        is True
    )
    assert client.post(endpoint, json={"file_id": foreign["id"]}).status_code == 422
    assert (
        client.post(
            endpoint, json={"file_id": file["id"], "path": "C:/private.txt"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/runs/{rid}/parameters/batch",
            json={"parameters": [{"name": "bad", "is_confirmed": True}]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/runs/{rid}/metrics/batch",
            json={"metrics": [{"name": "bad", "status": "validated"}]},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/runs/{rid}/highlight", json={"is_highlighted": True}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/runs/{rid}/highlight",
            json={"is_highlighted": True, "user_requested": True},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{pid}/evidence",
            json={
                "title": "Proposal",
                "status": "proposed",
                "linked_artifact_id": file["id"],
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{pid}/evidence",
            json={"title": "Bad", "status": "validated"},
        ).status_code
        == 403
    )
    audit = client.get("/api/activity").json()
    assert any(
        a["action"] == "register_artifact" and a["actor_type"] == "codex" for a in audit
    )
