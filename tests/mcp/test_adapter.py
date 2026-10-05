import asyncio
import importlib
from uuid import uuid4

import httpx
import pytest


def adapter():
    module = importlib.import_module('apps.mcp.adapter')
    return module.ResearchHubClient


def test_adapter_exists_and_requires_token():
    with pytest.raises(ValueError, match='token'):
        adapter()('http://localhost:8000', '')


def test_bearer_read_and_write_forbidden_by_real_http_response():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer read-token'
        if request.method == 'POST':
            return httpx.Response(403, json={'detail': 'write scope required'})
        return httpx.Response(200, json=[{'id': str(uuid4()), 'name': 'private'}])
    client = adapter()('http://localhost:8000', 'read-token', transport=httpx.MockTransport(handler))
    assert asyncio.run(client.get_projects())[0]['name'] == 'private'
    with pytest.raises(PermissionError, match='403'):
        asyncio.run(client.create_note(str(uuid4()), 'title', 'content'))
    assert len(calls) == 2


def test_invalid_id_never_becomes_arbitrary_path():
    calls = []
    client = adapter()('http://localhost:8000', 'token', transport=httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(ValueError):
        asyncio.run(client.get_project('../auth/tokens'))
    assert calls == []


def test_write_payload_and_backend_errors_do_not_leak_credentials():
    run_id = str(uuid4())
    def handler(request):
        assert request.url.path == f'/api/runs/{run_id}/metrics/batch'
        return httpx.Response(500, text='password=secret token=top-secret')
    client = adapter()('http://localhost:8000', 'top-secret', transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match='500') as error:
        asyncio.run(client.save_run_metrics(run_id, [{'name': 'IoU', 'value': .7}]))
    assert 'secret' not in str(error.value)


def test_only_nine_mcp_tools_registered():
    server = importlib.import_module('apps.mcp.server').build_server(adapter()('http://localhost:8000', 'token'))
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {'get_projects', 'get_project', 'get_project_context', 'list_runs', 'get_run', 'create_run', 'save_run_metrics', 'create_note', 'create_task'}
