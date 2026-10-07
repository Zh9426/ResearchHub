"""Real MCP subprocess + real HTTP API; isolated SQLite, no cloud integration."""

import asyncio
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.fixture
def live_api(tmp_path):
    from apps.api.researchhub.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'mcp-api.db'}", initialize=True
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        if not thread.is_alive():
            raise RuntimeError("Test API failed to start")
        time.sleep(0.05)
    assert server.started
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as owner:
            response = owner.post(
                "/api/auth/setup",
                json={
                    "email": "mcp@example.test",
                    "password": "mcp-test-password-safe",
                    "display_name": "MCP test",
                },
            )
            assert response.status_code == 200, response.text
            owner.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            project = owner.post(
                "/api/projects",
                json={"name": "SYNTHETIC protocol test", "module_id": "generic"},
            ).json()
            yield owner, project["id"], f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


async def protocol(url, token, project_id, writable):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "apps.mcp.server"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env={**os.environ, "RESEARCHHUB_API_URL": url, "RESEARCHHUB_API_TOKEN": token},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert len(tools.tools) == 21
        result = await session.call_tool("get_projects", {})
        assert not result.isError
        assert project_id in str(result)
        result = await session.call_tool(
            "get_project_summary", {"project_id": project_id, "limit": 1}
        )
        assert not result.isError and "groups" in str(result)
        result = await session.call_tool(
            "search_research", {"q": "SYNTHETIC", "project_id": project_id, "limit": 1}
        )
        assert not result.isError and "total" in str(result)
        result = await session.call_tool(
            "get_current_blockers", {"project_id": project_id, "limit": 1}
        )
        assert not result.isError and "total" in str(result)
        result = await session.call_tool(
            "create_note",
            {
                "project_id": project_id,
                "title": "Protocol note",
                "content": "SYNTHETIC MCP validation",
            },
        )
        assert bool(result.isError) is (not writable)
        if not writable:
            assert "403" in str(result)
        else:
            result = await session.call_tool(
                "create_run",
                {
                    "project_id": project_id,
                    "run": {"title": "Protocol run", "run_type": "simulation"},
                },
            )
            assert not result.isError, str(result)
            # Tool output has structured result with the SDK's dict envelope.
            payload = result.structuredContent
            if payload and "result" in payload:
                payload = payload["result"]
            if not payload:
                import json

                payload = json.loads(result.content[0].text)
            run_id = payload["id"]
            result = await session.call_tool(
                "upsert_run_parameters",
                {
                    "run_id": run_id,
                    "parameters": [
                        {
                            "name": "qa_input",
                            "value": 1,
                            "source_kind": "synthetic",
                            "unit": None,
                        }
                    ],
                },
            )
            assert not result.isError, str(result)
            result = await session.call_tool(
                "save_run_metrics",
                {
                    "run_id": run_id,
                    "metrics": [{"name": "synthetic_score", "value": 0.7}],
                },
            )
            assert not result.isError, str(result)
            result = await session.call_tool("get_run", {"run_id": run_id})
            assert not result.isError and "synthetic_score" in str(result)
            result = await session.call_tool(
                "upsert_run_parameters",
                {
                    "run_id": run_id,
                    "parameters": [
                        {"name": "confirmed_bad", "value": 1, "is_confirmed": True}
                    ],
                },
            )
            assert result.isError and "403" in str(result)
            result = await session.call_tool(
                "save_run_metrics",
                {
                    "run_id": run_id,
                    "metrics": [{"name": "validated_bad", "status": "validated"}],
                },
            )
            assert result.isError and "403" in str(result)
            result = await session.call_tool(
                "set_run_highlight", {"run_id": run_id, "is_highlighted": True}
            )
            assert result.isError and "explicit user" in str(result)
            result = await session.call_tool(
                "set_run_highlight",
                {
                    "run_id": run_id,
                    "is_highlighted": True,
                    "user_requested": True,
                    "note": "SYNTHETIC protocol user request",
                },
            )
            assert not result.isError, str(result)
            result = await session.call_tool(
                "get_highlighted_runs", {"project_id": project_id, "limit": 1}
            )
            assert not result.isError and run_id in str(result)
            result = await session.call_tool(
                "clone_run", {"run_id": run_id, "clone": {"title": "Child"}}
            )
            assert not result.isError, str(result)
            child = result.structuredContent
            if child and "result" in child:
                child = child["result"]
            if not child:
                import json

                child = json.loads(result.content[0].text)
            result = await session.call_tool(
                "compare_runs",
                {"run_id": child["id"], "other_run_id": run_id, "limit": 1},
            )
            assert not result.isError and "groups" in str(result)
            result = await session.call_tool(
                "query_runs", {"project_id": project_id, "q": "Protocol", "limit": 1}
            )
            assert not result.isError and run_id in str(result)
            result = await session.call_tool(
                "create_proposed_evidence",
                {
                    "project_id": project_id,
                    "evidence": {
                        "title": "SYNTHETIC proposal",
                        "linked_run_id": run_id,
                    },
                },
            )
            assert not result.isError and "proposed" in str(result)
            result = await session.call_tool(
                "get_evidence_trace",
                {
                    "project_id": project_id,
                    "kind": "runs",
                    "resource_id": run_id,
                    "limit": 1,
                },
            )
            assert not result.isError and "SYNTHETIC proposal" in str(result)
            result = await session.call_tool(
                "create_task", {"project_id": project_id, "title": "SYNTHETIC followup"}
            )
            assert not result.isError, str(result)


def test_stdio_mcp_read_only_cannot_write(live_api):
    owner, project_id, url = live_api
    response = owner.post(
        "/api/auth/tokens",
        json={"name": "read proof", "scopes": ["research:read"], "actor_type": "codex"},
    )
    assert response.status_code == 200, response.text
    asyncio.run(protocol(url, response.json()["token"], project_id, False))
    assert owner.get(f"/api/projects/{project_id}/notes").json() == []


def test_stdio_mcp_write_produces_codex_audit(live_api):
    owner, project_id, url = live_api
    response = owner.post(
        "/api/auth/tokens",
        json={
            "name": "write proof",
            "scopes": ["research:read", "research:write"],
            "actor_type": "codex",
        },
    )
    assert response.status_code == 200, response.text
    asyncio.run(protocol(url, response.json()["token"], project_id, True))
    activity = owner.get("/api/activity").json()
    assert any(
        item["actor_type"] == "codex"
        and item["action"] == "create_notes"
        and item["source"] == "mcp"
        and item["request_id"]
        for item in activity
    )
    assert any(
        item["actor_type"] == "codex"
        and item["action"] == "create_metrics"
        and item["source"] == "mcp"
        for item in activity
    )
