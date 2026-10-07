"""Reject false positive host acceptance and verify temporary credential cleanup."""
import runpy
from pathlib import Path

import httpx

helpers = runpy.run_path(str(Path(__file__).parents[2] / "scripts/codex-acceptance.py"))


def test_zero_requires_numeric_value_and_synthetic_provenance():
    valid = {"value": 0, "unit": None, "source_kind": "synthetic", "status": "synthetic"}
    assert helpers["synthetic_zero"](valid)
    for change in ({"value": False}, {"source_kind": "simulation"}, {"unit": "Pa"}, {"status": "validated"}):
        assert not helpers["synthetic_zero"]({**valid, **change})
    parameter = {**valid, "value_type": "number", "is_confirmed": False}
    assert helpers["synthetic_zero"](parameter, parameter=True)
    assert not helpers["synthetic_zero"]({**parameter, "is_confirmed": True}, parameter=True)


def test_host_events_require_successful_completion_and_target_scope():
    item = {"tool": "get_run", "status": "completed", "arguments": {"run_id": "target"}}
    valid = {"type": "item.completed", "item": item}
    assert helpers["successful_tools"]([valid], "project", "target") == {"get_run"}
    invalid = [
        {**valid, "type": "item.started"},
        {**valid, "item": {**item, "status": "failed"}},
        {**valid, "item": {**item, "error": "cancelled"}},
        {**valid, "item": {**item, "arguments": {"run_id": "other"}}},
        {**valid, "item": {**item, "arguments": "not JSON"}},
        {**valid, "item": {**item, "tool": "create_run", "arguments": {"project_id": "other"}}},
    ]
    assert not helpers["successful_tools"](invalid, "project", "target")


def test_token_revocation_retries_and_reports_network_failure():
    attempts = []

    def transport(request):
        attempts.append(request)
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(base_url="http://qa.test", transport=httpx.MockTransport(transport)) as owner:
        revoked, errors = helpers["revoke_token"](owner, "temporary")
    assert not revoked and errors == ["ConnectError"] * 3
    assert len(attempts) == 3


def test_token_revocation_recovers_after_transient_failure():
    responses = iter([503, 200])
    with httpx.Client(base_url="http://qa.test", transport=httpx.MockTransport(
        lambda request: httpx.Response(next(responses))
    )) as owner:
        revoked, errors = helpers["revoke_token"](owner, "temporary")
    assert revoked and errors == ["HTTP 503"]
