"""Sprint 3 acceptance on explicit disposable real PostgreSQL/MinIO only."""

# ruff: noqa: F811

import asyncio
import uuid

import httpx
import pytest
from test_live_system import create, live  # noqa: F401

from apps.mcp.adapter import ResearchHubClient

REPO = "https://github.com/Zh9426/ResearchHub"


async def connected_workflow(url, token, pid, file_id):
    client = ResearchHubClient(url, token)
    projects = await client.get_projects(limit=1, q="SYNTHETIC connected")
    assert projects["total"] >= 1 and projects["limit"] == 1
    summary = await client.get_project_summary(pid, limit=1)
    assert summary["project"]["repository"] == REPO
    assert "groups" in summary
    parent = await client.create_run(
        pid,
        {
            "title": "SYNTHETIC connected baseline",
            "run_type": "simulation",
            "repository": REPO,
            "branch": "qa/connected",
            "commit_sha": "b" * 40,
            "issue_url": REPO + "/issues/1",
        },
    )
    rid = parent["id"]
    values = await client.upsert_run_parameters(
        rid,
        [
            {
                "name": f"qa_input_{i}",
                "value": i,
                "source_kind": "synthetic",
                "unit": None,
            }
            for i in range(3)
        ],
    )
    assert len(values) == 3
    await client.save_run_metrics(
        rid,
        [
            {
                "name": "qa_output",
                "value": 0.2,
                "status": "synthetic",
                "source_kind": "synthetic",
                "unit": None,
            }
        ],
    )
    await client.create_note(pid, "SYNTHETIC connected note", "QA only", rid)
    await client.create_task(pid, "SYNTHETIC connected followup")
    referenced = await client.register_artifact(rid, file_id)
    assert referenced["artifact"]["id"] == file_id
    assert (await client.register_artifact(rid, file_id))["already_linked"]
    evidence = await client.create_proposed_evidence(
        pid,
        {
            "title": "SYNTHETIC proposed support",
            "linked_run_id": rid,
            "linked_artifact_id": file_id,
        },
    )
    assert evidence["status"] == "proposed"
    with pytest.raises(PermissionError):
        await client.set_run_highlight(rid, True)
    highlighted = await client.set_run_highlight(
        rid, True, user_requested=True, note="SYNTHETIC explicit QA request"
    )
    assert highlighted["is_highlighted"]
    assert (await client.get_highlighted_runs(pid, limit=1))["items"][0]["id"] == rid
    context = await client.get_run(rid, limit=1, offset=1)
    assert context["groups"]["parameters"]["total"] == 3
    assert len(context["groups"]["parameters"]["items"]) == 1
    child = await client.clone_run(rid, {"title": "SYNTHETIC connected child"})
    assert child["commit_sha"] == "b" * 40 and not child["is_highlighted"]
    await client.upsert_run_parameters(
        child["id"],
        [{"name": "qa_input_2", "value": 9, "source_kind": "synthetic", "unit": None}],
    )
    differences = await client.compare_runs(child["id"], rid, limit=1)
    assert differences["groups"]["parameters"]["total"] == 1
    assert differences["groups"]["metrics"]["total"] == 1
    assert (await client.query_runs(pid, q="baseline", limit=1))["items"][0][
        "id"
    ] == rid
    assert (
        await client.search_research("connected", project_id=pid, kind="runs", limit=1)
    )["total"] == 2
    trace = await client.get_evidence_trace(pid, "runs", rid, limit=1)
    assert trace["groups"]["evidence"]["total"] == 1
    assert (await client.get_current_blockers(pid, limit=1))["total"] == 0
    with pytest.raises(PermissionError):
        await client.upsert_run_parameters(
            rid, [{"name": "bad", "value": 1, "is_confirmed": True}]
        )
    with pytest.raises(PermissionError):
        await client.save_run_metrics(
            rid, [{"name": "bad", "value": 1, "status": "validated"}]
        )
    with pytest.raises(PermissionError):
        await client.create_run(
            pid,
            {
                "title": "bad human conclusion",
                "run_type": "simulation",
                "human_conclusion": "AI assertion",
            },
        )
    return rid


def test_real_connected_provenance_artifact_and_ai_audit(live):
    assert live.get("/api/health").json()["database"] == "postgresql"
    project = create(
        live,
        "/api/projects",
        {
            "name": "SYNTHETIC connected " + uuid.uuid4().hex[:8],
            "module_id": "generic",
            "repository": REPO,
        },
    )
    pid = project["id"]
    payload = b"SYNTHETIC,1\n"
    uploaded = live.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("connected.csv", payload, "text/csv")},
        data={"category": "data"},
    )
    assert uploaded.status_code == 200, uploaded.text
    aid = uploaded.json()["id"]
    assert live.get(f"/api/artifacts/{aid}/download").content == payload
    token = create(
        live,
        "/api/auth/tokens",
        {
            "name": "SYNTHETIC connected",
            "scopes": ["research:read", "research:write"],
            "actor_type": "codex",
        },
    )
    try:
        rid = asyncio.run(
            connected_workflow(str(live.base_url).rstrip("/"), token["token"], pid, aid)
        )
        activity = live.get(
            "/api/activity", params={"project_id": pid, "format": "page", "limit": 100}
        ).json()["items"]
        for action in (
            "create_runs",
            "create_parameters",
            "create_metrics",
            "create_notes",
            "create_tasks",
            "register_artifact",
            "create_evidence",
            "set_run_highlight",
            "clone_run",
        ):
            assert any(
                item["action"] == action
                and item["actor_type"] == "codex"
                and item["source"] == "mcp"
                and item["request_id"]
                for item in activity
            ), action
        assert live.get(f"/api/runs/{rid}/context").json()["run"]["is_highlighted"]
        with httpx.Client(
            base_url=str(live.base_url),
            headers={"Authorization": "Bearer " + token["token"]},
            trust_env=False,
        ) as ai:
            assert (
                ai.post(
                    f"/api/runs/{rid}/artifacts/register",
                    json={"file_id": aid, "path": "/etc/passwd"},
                ).status_code
                == 422
            )
            assert (
                ai.post(
                    f"/api/projects/{pid}/evidence",
                    json={"title": "Forbidden", "status": "validated"},
                ).status_code
                == 403
            )
        assert (
            live.patch(
                f"/api/lifecycle/runs/{rid}", json={"action": "archive"}
            ).status_code
            == 200
        )
        ai_client = ResearchHubClient(str(live.base_url), token["token"])
        with pytest.raises(RuntimeError, match="404"):
            asyncio.run(ai_client.get_run(rid))
    finally:
        assert live.delete(f"/api/auth/tokens/{token['id']}").status_code == 200
