import asyncio
import importlib
from uuid import uuid4

import httpx
import pytest


def adapter():
    module = importlib.import_module("apps.mcp.adapter")
    return module.ResearchHubClient


def test_adapter_exists_and_requires_token():
    with pytest.raises(ValueError, match="token"):
        adapter()("http://localhost:8000", "")


def test_bearer_read_and_write_forbidden_by_real_http_response():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer read-token"
        if request.method == "POST":
            return httpx.Response(403, json={"detail": "write scope required"})
        return httpx.Response(
            200,
            json={
                "items": [{"id": str(uuid4()), "name": "private"}],
                "total": 1,
                "limit": 50,
                "offset": 0,
            },
        )

    client = adapter()(
        "http://localhost:8000", "read-token", transport=httpx.MockTransport(handler)
    )
    assert asyncio.run(client.get_projects())["items"][0]["name"] == "private"
    with pytest.raises(PermissionError, match="403"):
        asyncio.run(client.create_note(str(uuid4()), "title", "content"))
    assert len(calls) == 2


def test_invalid_id_never_becomes_arbitrary_path():
    calls = []
    client = adapter()(
        "http://localhost:8000",
        "token",
        transport=httpx.MockTransport(lambda r: calls.append(r)),
    )
    with pytest.raises(ValueError):
        asyncio.run(client.get_project("../auth/tokens"))
    assert calls == []


def test_write_payload_and_backend_errors_do_not_leak_credentials():
    run_id = str(uuid4())

    def handler(request):
        assert request.url.path == f"/api/runs/{run_id}/metrics/batch"
        return httpx.Response(500, text="password=secret token=top-secret")

    client = adapter()(
        "http://localhost:8000", "top-secret", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(RuntimeError, match="500") as error:
        asyncio.run(client.save_run_metrics(run_id, [{"name": "IoU", "value": 0.7}]))
    assert "secret" not in str(error.value)


def test_only_explicit_semantic_mcp_tools_registered():
    server = importlib.import_module("apps.mcp.server").build_server(
        adapter()("http://localhost:8000", "token")
    )
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {
        "get_projects",
        "get_project",
        "get_project_context",
        "list_runs",
        "get_run",
        "create_run",
        "save_run_metrics",
        "create_note",
        "create_task",
        "get_project_summary",
        "search_research",
        "query_runs",
        "compare_runs",
        "get_highlighted_runs",
        "get_current_blockers",
        "get_evidence_trace",
        "clone_run",
        "upsert_run_parameters",
        "register_artifact",
        "create_proposed_evidence",
        "set_run_highlight",
    }


def test_bounded_queries_and_filter_scope_injection_rejected_locally():
    calls = []
    client = adapter()(
        "http://localhost:8000",
        "token",
        transport=httpx.MockTransport(lambda r: calls.append(r)),
    )
    for limit, offset in ((0, 0), (101, 0), (1, -1), (True, 0)):
        with pytest.raises(ValueError):
            asyncio.run(client.get_projects(limit, offset))
    with pytest.raises(ValueError, match="filter"):
        asyncio.run(
            client.query_runs(str(uuid4()), filters={"project_id": str(uuid4())})
        )
    with pytest.raises(ValueError):
        asyncio.run(client.get_evidence_trace(str(uuid4()), "../auth", str(uuid4())))
    with pytest.raises(PermissionError):
        asyncio.run(client.set_run_highlight(str(uuid4()), True))
    with pytest.raises(ValueError):
        asyncio.run(
            client.create_proposed_evidence(
                str(uuid4()), {"title": "Bad", "status": "validated"}
            )
        )
    with pytest.raises(ValueError):
        asyncio.run(client.register_artifact(str(uuid4()), "C:/private.txt"))
    assert calls == []


def test_query_text_pagination_and_filters_are_url_encoded():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"items": [], "total": 0, "limit": 1, "offset": 2}
        )

    client = adapter()(
        "http://localhost:8000", "token", transport=httpx.MockTransport(handler)
    )
    pid = str(uuid4())
    asyncio.run(
        client.query_runs(
            pid,
            q="a&project_id=other",
            filters={"is_highlighted": True},
            limit=1,
            offset=2,
        )
    )
    assert calls[0].url.path == f"/api/projects/{pid}/runs/query"
    assert calls[0].url.params["q"] == "a&project_id=other"
    assert calls[0].url.params["is_highlighted"] == "true"
    assert calls[0].url.params["active_only"] == "true"
