"""GitHub 检查脚本的可见性策略与只读边界；不访问真实凭据或网络。"""

import runpy
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/check-github.py"
REPO_URL = "https://api.github.com/repos/Zh9426/ResearchHub"
TEST_TOKEN = "synthetic-credential-do-not-print"


@pytest.fixture
def github_check(monkeypatch):
    requests = []
    commands = []
    state = {"visibility": "public", "password": TEST_TOKEN, "runs": []}
    original_client = httpx.Client

    def transport(request):
        requests.append(request)
        if request.url.path.endswith("/actions/runs"):
            return httpx.Response(200, json={"workflow_runs": state["runs"]})
        return httpx.Response(200, json={
            "private": state["visibility"] == "private",
            "visibility": state["visibility"],
        })

    def run(command, **kwargs):
        commands.append(command)
        if command == ["git", "credential", "fill"]:
            return subprocess.CompletedProcess(command, 0, f"password={state['password']}\n", "")
        assert command == ["git", "branch", "--show-current"]
        return subprocess.CompletedProcess(command, 0, "codex/release\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(transport)
    ))

    def invoke(*arguments, run_name="__main__"):
        monkeypatch.setattr(sys, "argv", [str(SCRIPT), *arguments])
        try:
            runpy.run_path(str(SCRIPT), run_name=run_name)
        except (RuntimeError, SystemExit) as error:
            return error
        return None

    return invoke, state, requests, commands


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_visibility_is_informational_without_expectation(github_check, capsys, visibility):
    invoke, state, requests, _ = github_check
    state["visibility"] = visibility

    assert invoke() is None
    output = capsys.readouterr()
    assert f"visibility={visibility}" in output.out
    assert TEST_TOKEN not in output.out + output.err
    assert [(request.method, str(request.url)) for request in requests] == [("GET", REPO_URL)]


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_matching_expected_visibility_passes_read_only(github_check, visibility):
    invoke, state, requests, _ = github_check
    state["visibility"] = visibility

    assert invoke("--expect-visibility", visibility) is None
    assert [request.method for request in requests] == ["GET"]


@pytest.mark.parametrize("actual,expected", [("public", "private"), ("private", "public")])
def test_expected_visibility_mismatch_fails_without_mutation(github_check, capsys, actual, expected):
    invoke, state, requests, _ = github_check
    state["visibility"] = actual

    error = invoke("--expect-visibility", expected)

    assert isinstance(error, RuntimeError)
    assert actual in str(error) and expected in str(error)
    assert [request.method for request in requests] == ["GET"]
    output = capsys.readouterr()
    assert TEST_TOKEN not in str(error) + output.out + output.err


def test_import_has_no_credential_or_network_side_effects(github_check):
    invoke, state, requests, commands = github_check
    state["visibility"] = "private"

    assert invoke(run_name="github_visibility_check") is None
    assert commands == []
    assert requests == []


def test_removed_ensure_private_option_cannot_mutate_repository(github_check):
    invoke, _, requests, commands = github_check

    error = invoke("--ensure-private")

    assert isinstance(error, SystemExit) and error.code == 2
    assert commands == []
    assert requests == []


def test_ci_reads_current_branch_runs_for_public_repository(github_check, capsys):
    invoke, state, requests, commands = github_check
    state["runs"] = [{
        "head_sha": "synthetic-sha",
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/Zh9426/ResearchHub/actions/runs/123",
    }]

    assert invoke("--ci", "--expect-visibility", "public") is None
    assert [request.method for request in requests] == ["GET", "GET"]
    assert dict(requests[1].url.params) == {"branch": "codex/release", "per_page": "3"}
    assert commands[-1] == ["git", "branch", "--show-current"]
    output = capsys.readouterr()
    assert "CI: synthetic-sha completed success" in output.out
    assert TEST_TOKEN not in output.out + output.err


def test_missing_credential_fails_before_network_access(github_check):
    invoke, state, requests, _ = github_check
    state["password"] = ""

    error = invoke()

    assert isinstance(error, RuntimeError)
    assert "认证不可用" in str(error)
    assert requests == []
