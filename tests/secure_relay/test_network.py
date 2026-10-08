"""Only real CA/hostname verified HTTPS against the disposable Relay container."""

import importlib.util
import socket
import ssl

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


def test_concurrent_first_get_snapshots_original_response(project):
    from concurrent.futures import ThreadPoolExecutor

    prepared = project.prepare("GET", "/v1/messages", query={"cursor": 0, "limit": 100})
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: project.send(prepared).content, range(4)))
    assert len(set(responses)) == 1
    assert project.push([project.envelope()]).status_code == 200
    assert project.send(prepared).content == responses[0]
