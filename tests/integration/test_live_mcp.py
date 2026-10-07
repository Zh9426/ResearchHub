"""Opt-in MCP stdio acceptance against the real disposable PostgreSQL API."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def exercise(url, token, project_id, writable):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "apps.mcp.server"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env={**os.environ, "RESEARCHHUB_API_URL": url, "RESEARCHHUB_API_TOKEN": token},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        assert len((await session.list_tools()).tools) == 21
        projects = await session.call_tool("get_projects", {})
        assert not projects.isError and project_id in str(projects)
        note = await session.call_tool("create_note", {
            "project_id": project_id, "title": "SYNTHETIC live MCP note",
            "content": "Disposable PostgreSQL acceptance record.",
        })
        assert bool(note.isError) is (not writable)
        if not writable:
            assert "403" in str(note)


@pytest.mark.parametrize("writable", [False, True])
def test_real_postgresql_mcp_protocol_scopes_and_audit(writable):
    url = os.getenv("HUB_LIVE_URL")
    credentials_file = os.getenv("HUB_QA_CREDENTIALS_FILE")
    if not url or not credentials_file:
        pytest.skip("Requires explicit disposable real PostgreSQL deployment")
    credentials = json.loads(Path(credentials_file).read_text(encoding="utf-8-sig"))
    with httpx.Client(base_url=url, trust_env=False, timeout=30) as owner:
        login = owner.post("/api/auth/login", json=credentials)
        assert login.status_code == 200
        owner.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        project = owner.post("/api/projects", json={
            "name": "SYNTHETIC live MCP acceptance", "module_id": "generic",
        }).json()
        token = owner.post("/api/auth/tokens", json={
            "name": "SYNTHETIC live MCP token",
            "scopes": ["research:read", "research:write"] if writable else ["research:read"],
            "actor_type": "codex",
        }).json()
        try:
            asyncio.run(exercise(url, token["token"], project["id"], writable))
            notes = owner.get(f"/api/projects/{project['id']}/notes").json()
            assert len(notes) == (1 if writable else 0)
            if writable:
                entries = owner.get(f"/api/projects/{project['id']}/context").json()["activity"]
                assert any(a["actor_type"] == "codex" and a["source"] == "mcp"
                           and a["action"] == "create_notes" and a["request_id"] for a in entries)
        finally:
            assert owner.delete(f"/api/auth/tokens/{token['id']}").status_code == 200
