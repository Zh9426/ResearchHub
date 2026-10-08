"""Only real CA/hostname verified HTTPS against the disposable Relay container."""

import importlib.util
import json
import socket
import ssl
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from researchhub_relay.models import Message, Project
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, digest
from packages.secure_wire.checkpoint import extend_chain


def test_relay_network_service_is_implemented():
    assert importlib.util.find_spec("researchhub_relay.main"), (
        "HTTPS Relay API is missing"
    )


def test_real_https_ca_hostname_and_plaintext_rejection(network):
    # Positive TLS handshake first: connection refused never counts as rejection.
    with (
        socket.create_connection(("127.0.0.1", 38001), timeout=3) as raw,
        network["tls"].wrap_socket(raw, server_hostname="127.0.0.1") as tls,
    ):
        assert tls.version() in ("TLSv1.2", "TLSv1.3")
    with (
        pytest.raises(ssl.SSLCertVerificationError),
        socket.create_connection(("127.0.0.1", 38001), timeout=3) as raw,
    ):
        ssl.create_default_context().wrap_socket(raw, server_hostname="127.0.0.1")
    with (
        pytest.raises(ssl.SSLCertVerificationError),
        socket.create_connection(("127.0.0.1", 38001), timeout=3) as raw,
    ):
        network["tls"].wrap_socket(raw, server_hostname="wrong.synthetic.invalid")
    with socket.create_connection(("127.0.0.1", 38001), timeout=3) as raw:
        raw.sendall(
            b"GET /v1/messages?cursor=0&limit=100 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        )
        raw.settimeout(6)
        try:
            data = raw.recv(4096)
        except (ConnectionResetError, TimeoutError):
            data = b""
        assert b"200" not in data and b"RELAY_STORED" not in data


def test_push_pull_durable_pg_original_receipts_and_chain(project):
    envelope = project.envelope()
    prepared = project.prepare("POST", "/v1/messages", {"envelopes": [envelope]})
    first = project.send(prepared)
    assert first.status_code == 200, first.json().get("code")
    assert project.send(prepared).content == first.content
    assert project.push([envelope]).content == first.content
    page = project.pull().json()["result"]
    assert page["rows"][0]["envelope"] == envelope
    assert page["cursor"] == 1
    chain = extend_chain(
        "0" * 64, 0, [{"sequence": 1, "envelope_digest": digest(envelope)}]
    )
    assert page["chain_digest"] == chain
    with Session(project.network["engine"]) as db:
        message = db.get(Message, (project.id, envelope["message_id"]))
        assert message.body == canonical_bytes(envelope)
        assert message.sequence == 1 and message.chain == chain
        assert db.get(Project, project.id).pending_bytes > 16


def test_get_empty_page_is_immutable_even_after_new_messages(project):
    request = project.prepare("GET", "/v1/messages", query={"cursor": 0, "limit": 100})
    empty = project.send(request)
    assert empty.status_code == 200 and empty.json()["result"]["rows"] == []
    assert project.push([project.envelope()]).status_code == 200
    assert project.send(request).content == empty.content
    assert len(project.pull().json()["result"]["rows"]) == 1


def test_partial_page_and_out_of_order_retry_do_not_split_messages(project):
    values = [project.envelope({"n": n, "pad": "x" * 120000}) for n in range(4)]
    receipts = []
    for value in values:
        result = project.push([value])
        assert result.status_code == 200
        receipts.append(result.content)
    page = project.pull().json()["result"]
    assert 0 < len(page["rows"]) < 4
    assert len(canonical_bytes({"ok": True, "result": page})) <= 524288
    second = project.pull(page["cursor"]).json()["result"]
    assert [r["envelope"] for r in page["rows"] + second["rows"]] == values
    for n in (3, 1, 0, 2):
        assert project.push([values[n]]).content == receipts[n]
    with Session(project.network["engine"]) as db:
        assert db.scalar(select(Project.sequence).where(Project.id == project.id)) == 4


@pytest.mark.parametrize("connection_mode", ["pooled", "fresh"])
def test_concurrent_first_get_snapshots_original_response(project, connection_mode):
    from concurrent.futures import ThreadPoolExecutor

    context = project.network["audit_context"]
    assert context["cohort"] in {"relay", "client", "direct"}
    identity = {
        "run": str(UUID(project.network["state"]["run"])),
        **{key: str(UUID(context[key])) for key in ("trial", "invocation")},
        "cohort": context["cohort"],
        "case_id": str(uuid4()),
    }
    # Fixed workload, not retry-until-green. The first failing round fails pytest.
    for round_ in range(10):
        prepared = project.prepare(
            "GET", "/v1/messages", query={"cursor": 0, "limit": 100}
        )
        traces = [[] for _ in range(4)]
        started = time.time_ns() // 1000000
        passed = False
        operation = "concurrent_get"

        def send(index, prepared=prepared, traces=traces):
            def trace(event, _info):
                # _info can contain proof headers and exceptions; never serialize it.
                allowed = {
                    "connection.connect_tcp.started",
                    "connection.connect_tcp.complete",
                    "connection.connect_tcp.failed",
                    "connection.start_tls.started",
                    "connection.start_tls.complete",
                    "connection.start_tls.failed",
                    "http11.send_request_headers.started",
                    "http11.send_request_headers.complete",
                    "http11.send_request_headers.failed",
                    "http11.receive_response_headers.complete",
                    "http11.receive_response_headers.failed",
                    "http11.receive_response_body.started",
                    "http11.receive_response_body.complete",
                    "http11.receive_response_body.failed",
                }
                if event in allowed:
                    traces[index].append(
                        {"event": event, "time_ms": time.time_ns() // 1000000}
                    )

            if connection_mode == "fresh":
                # Explicit fresh CA/hostname-verified handshakes, in addition to
                # the original shared-pool schedule. No transport retries.
                with httpx.Client(
                    base_url="https://127.0.0.1:38001",
                    verify=project.network["tls"],
                    trust_env=False,
                    timeout=12,
                ) as client:
                    response = client.request(**prepared, extensions={"trace": trace})
            else:
                response = project.network["client"].request(
                    **prepared, extensions={"trace": trace}
                )
            assert response.status_code == 200
            return response.content

        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(send, range(4)))
            operation = "comparison"
            assert len(set(responses)) == 1
            operation = "push"
            assert project.push([project.envelope()]).status_code == 200
            operation = "replay"
            assert project.send(prepared).content == responses[0]
            passed = True
            operation = "complete"
        finally:
            # Persist before any further I/O. No request/proof/body/exception text.
            directory = (
                Path(__file__).resolve().parents[2]
                / "storage/runtime/tls-case-evidence"
            )
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (str(uuid4()) + ".json")).write_text(
                json.dumps(
                    {
                        **identity,
                        "case": "concurrent_first_get",
                        "connection_mode": connection_mode,
                        "operation": operation,
                        "round": round_,
                        "planned_rounds": 10,
                        "started_ms": started,
                        "passed": passed,
                        "traces": traces,
                    }
                ),
                encoding="utf-8",
            )
