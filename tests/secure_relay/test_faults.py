"""Real connection loss and exact owned container process termination."""

import socket
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from researchhub_relay.models import Message, Project
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes


def socket_send(project, prepared, fraction=1):
    raw = socket.create_connection(("127.0.0.1", 38001), timeout=5)
    tls = project.network["tls"].wrap_socket(raw, server_hostname="127.0.0.1")
    body = prepared["content"]
    headers = {
        "Host": "127.0.0.1",
        "Content-Length": str(len(body)),
        "Connection": "close",
        **prepared["headers"],
    }
    prefix = (
        f"{prepared['method']} {prepared['url']} HTTP/1.1\r\n"
        + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        + "\r\n"
    )
    tls.sendall(prefix.encode() + body[: int(len(body) * fraction)])
    tls.close()


def test_half_upload_and_full_upload_disconnect_retry(project):
    envelope = project.envelope({"payload": "SYNTHETIC_PRIVATE_NOTE" * 3000})
    prepared = project.prepare("POST", "/v1/messages", {"envelopes": [envelope]})
    socket_send(project, prepared, 0.5)
    time.sleep(0.15)
    with Session(project.network["engine"]) as db:
        assert db.get(Message, (project.id, envelope["message_id"])) is None
    socket_send(project, prepared)
    response = project.send(prepared)
    assert response.status_code == 200
    with Session(project.network["engine"]) as db:
        row = db.get(Message, (project.id, envelope["message_id"]))
        assert row.body == canonical_bytes(envelope) and row.sequence == 1
    assert project.send(prepared).content == response.content


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_real_sigkill_at_durable_transaction_barrier(project, point):
    q, state, value = (project.network[k] for k in ("lifecycle", "state", "config"))
    q.guard_state(state, value)
    relay = state["containers"][q.RELAY]
    q.docker(
        "exec",
        relay,
        "python",
        "-c",
        "from pathlib import Path; p=Path('/fault'); [(p/n).unlink(missing_ok=True) for n in ('arm','reached','release')]; (p/'arm').write_text('"
        + point
        + "')",
    )
    envelope = project.envelope()
    prepared = project.prepare("POST", "/v1/messages", {"envelopes": [envelope]})
    with ThreadPoolExecutor(max_workers=1) as pool:
        response = pool.submit(project.send, prepared)
        deadline = time.monotonic() + 15
        while True:
            reached = (
                q.docker(
                    "exec",
                    relay,
                    "python",
                    "-c",
                    "from pathlib import Path; p=Path('/fault/reached'); print(p.read_text() if p.exists() else 'waiting')",
                )
                .decode()
                .strip()
            )
            if reached == point:
                break
            assert time.monotonic() < deadline, "Fault marker was not reached"
            time.sleep(0.1)
        with Session(project.network["engine"]) as db:
            row = db.get(Message, (project.id, envelope["message_id"]))
            assert (row is not None) == (point == "after_commit")
            original = row.receipt if row else None
        q.guard_state(state, value)
        q.docker("kill", "--signal", "KILL", relay)
        with pytest.raises(httpx.TransportError):
            response.result()
    q.guard_state(state, value)
    q.docker("start", relay)
    q.wait_tls(state)
    retry = project.send(prepared)
    assert retry.status_code == 200
    with Session(project.network["engine"]) as db:
        row = db.get(Message, (project.id, envelope["message_id"]))
        assert row.body == canonical_bytes(envelope) and row.sequence == 1
        if original is not None:
            assert row.receipt == original
        assert db.get(Project, project.id).sequence == 1


@pytest.mark.parametrize("service", ["relay", "pg", "ingress"])
def test_durable_ciphertext_survives_service_kill_and_restart(project, service):
    q, state, value = (project.network[k] for k in ("lifecycle", "state", "config"))
    envelope = project.envelope()
    prepared = project.prepare("POST", "/v1/messages", {"envelopes": [envelope]})
    receipt = project.send(prepared)
    assert receipt.status_code == 200
    name = {"relay": q.RELAY, "pg": q.PG, "ingress": q.INGRESS}[service]
    id_ = state["pg"]["id"] if service == "pg" else state["containers"][name]
    q.guard_state(state, value)
    q.docker("kill", "--signal", "KILL", id_)
    if service == "pg":
        assert project.pull().status_code == 503
    else:
        with pytest.raises(httpx.TransportError):
            project.pull()
    q.guard_state(state, value)
    q.docker("start", id_)
    q.readiness(value)
    q.wait_tls(state)
    assert project.send(prepared).content == receipt.content
    assert project.pull().json()["result"]["rows"][0]["envelope"] == envelope
