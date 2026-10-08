"""Unit fault classification only; never a substitute for actual TLS tests."""

import ast
import asyncio
import json
from pathlib import Path

import pytest


def ingress():
    path = Path(__file__).resolve().parents[2] / "apps/relay/ingress/forward.py"
    tree = ast.parse(path.read_text())
    # Load the real definitions without starting the standalone server.
    tree.body = [n for n in tree.body if not isinstance(n, ast.Expr)]
    namespace = {"__name__": "ingress_test"}
    exec(compile(tree, str(path), "exec"), namespace)  # noqa: S102 -- fixed repository source only
    return namespace


class Writer:
    closed = False

    def close(self):
        self.closed = True

    def write(self, data):
        pass

    async def drain(self):
        pass


class Reader:
    def __init__(self, values):
        self.values = iter(values)

    async def read(self, _size):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        if value is None:
            await asyncio.Future()
        return value


@pytest.mark.parametrize(
    "reason", ["upstream_connect_timeout", "upstream_connect_error"]
)
def test_connect_failure_is_classified_without_exception_text(
    monkeypatch, capsys, reason
):
    module, writer = ingress(), Writer()

    async def fail(*args, **kwargs):
        error = TimeoutError if reason.endswith("timeout") else OSError
        raise error("PRIVATE_SENTINEL_NOT_FOR_LOGS")

    monkeypatch.setattr(asyncio, "open_connection", fail)
    asyncio.run(module["connection"](Reader([None]), writer))
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == reason
    assert result["client_to_upstream_bytes"] == 0
    assert result["upstream_to_client_bytes"] == 0
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert writer.closed and module["active"] == 0


@pytest.mark.parametrize("direction", ["client_to_upstream", "upstream_to_client"])
@pytest.mark.parametrize("failure", ["eof", "timeout", "error"])
def test_directional_close_reason_and_cleanup(monkeypatch, capsys, direction, failure):
    module, writer, upstream = ingress(), Writer(), Writer()
    end = {"eof": b"", "timeout": TimeoutError("SECRET"), "error": OSError("SECRET")}[
        failure
    ]
    failing = Reader([b"PRIVATE_BYTES", end])
    waiting = Reader([None])
    client, remote = (
        (failing, waiting) if direction == "client_to_upstream" else (waiting, failing)
    )

    async def connected(*args, **kwargs):
        return remote, upstream

    monkeypatch.setattr(asyncio, "open_connection", connected)
    asyncio.run(module["connection"](client, writer))
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == direction + "_read_" + failure
    assert result[direction + "_bytes"] == len(b"PRIVATE_BYTES")
    assert "SECRET" not in json.dumps(result) and "PRIVATE_BYTES" not in json.dumps(
        result
    )
    assert writer.closed and upstream.closed and module["active"] == 0


def test_capacity_rejection_is_identifiable(capsys):
    module, writer = ingress(), Writer()
    module["active"] = module["MAX_CONNECTIONS"]
    asyncio.run(module["connection"](Reader([None]), writer))
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == "capacity_rejected"
    assert writer.closed and module["active"] == module["MAX_CONNECTIONS"]


def test_connection_lifetime_is_distinct_and_cancels_both_directions(
    monkeypatch, capsys
):
    module, writer, upstream = ingress(), Writer(), Writer()
    timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda _seconds: timeout(0.01))

    async def connected(*args, **kwargs):
        return Reader([None]), upstream

    monkeypatch.setattr(asyncio, "open_connection", connected)
    asyncio.run(module["connection"](Reader([None]), writer))
    result = json.loads(capsys.readouterr().out)
    assert result["reason"] == "connection_lifetime_timeout"
    assert writer.closed and upstream.closed and module["active"] == 0


def test_export_refuses_extra_fields_and_untrusted_reason():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts/secure-relay-diagnostics.py"
    spec = importlib.util.spec_from_file_location("diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    good = {
        "event": "ingress_close",
        "reason": "upstream_connect_timeout",
        "elapsed_ms": 1,
        "time_ms": 2,
        "active": 0,
        "client_to_upstream_bytes": 0,
        "upstream_to_client_bytes": 0,
    }
    assert module.validate(json.dumps(good).encode()) == [good]
    for bad in (
        {**good, "payload": "PRIVATE"},
        {**good, "reason": "PRIVATE"},
        {**good, "active": True},
        {**good, "elapsed_ms": -1},
    ):
        with pytest.raises(ValueError, match="DIAGNOSTIC_SCHEMA_REJECTED"):
            module.validate(json.dumps(bad).encode())


def test_simultaneous_eof_does_not_claim_causal_order(monkeypatch, capsys):
    module, writer, upstream = ingress(), Writer(), Writer()

    async def connected(*args, **kwargs):
        return Reader([b""]), upstream

    monkeypatch.setattr(asyncio, "open_connection", connected)
    asyncio.run(module["connection"](Reader([b""]), writer))
    assert json.loads(capsys.readouterr().out)["reason"] == "multiple_directions_eof"


def test_get_failure_propagates_without_next_round_or_sensitive_trace(
    monkeypatch, tmp_path
):
    # Load the actual test function, avoiding unrelated network module imports.
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from uuid import UUID, uuid4

    path = Path(__file__).resolve().parents[2] / "tests/secure_relay/test_network.py"
    tree = ast.parse(path.read_text())
    tree.body = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "test_concurrent_first_get_snapshots_original_response"
    ]
    tree.body[0].decorator_list = []
    namespace = {
        "__file__": str(tmp_path / "a/b/test_network.py"),
        "Path": Path,
        "UUID": UUID,
        "uuid4": uuid4,
        "json": json,
        "time": time,
        "ThreadPoolExecutor": ThreadPoolExecutor,
    }
    exec(compile(tree, str(path), "exec"), namespace)  # noqa: S102 -- fixed repository test only
    prepared = []

    def prepare(*args, **kwargs):
        prepared.append(True)
        return {}

    def fail(**kwargs):
        kwargs["extensions"]["trace"](
            "connection.start_tls.failed", {"secret": "PRIVATE_INFO"}
        )
        raise RuntimeError("SYNTHETIC_HANDSHAKE_FAILURE")

    project = SimpleNamespace(
        prepare=prepare,
        network={
            "client": SimpleNamespace(request=fail),
            "state": {"run": str(uuid4())},
            "audit_context": {
                "trial": str(uuid4()),
                "invocation": str(uuid4()),
                "cohort": "direct",
            },
        },
    )
    with pytest.raises(RuntimeError, match="SYNTHETIC_HANDSHAKE_FAILURE"):
        namespace["test_concurrent_first_get_snapshots_original_response"](
            project, "pooled"
        )
    assert len(prepared) == 1
    files = list((tmp_path / "storage/runtime/tls-case-evidence").glob("*.json"))
    assert len(files) == 1
    raw = files[0].read_text()
    evidence = json.loads(raw)
    assert evidence["passed"] is False and evidence["round"] == 0
    assert evidence["operation"] == "concurrent_get"
    assert "PRIVATE_INFO" not in raw and "SYNTHETIC_HANDSHAKE_FAILURE" not in raw
