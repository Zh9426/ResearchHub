"""Real HTTP budget boundaries; constants remain the frozen QA contract."""

import time
from uuid import uuid4

from researchhub_relay.models import Budget, Message, Project
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes
from packages.secure_wire.envelope import b64encode


def test_raw_envelope_batch_and_chunk_size_limits(project):
    request = project.prepare("POST", "/v1/hello", {})
    request["content"] = b"x" * 524289
    assert project.send(request).status_code == 413
    envelope = project.envelope()
    large = {**envelope, "ciphertext": b64encode(b"x" * 200000)}
    assert project.push([large]).json()["code"] == "MESSAGE_TOO_LARGE"
    assert project.push([envelope] * 17).json()["code"] == "BATCH_LIMIT"
    chunk = {
        "opaque_project_id": project.id,
        "opaque_locator": str(uuid4()),
        "key_epoch": 1,
        "index": 0,
        "total": 1,
        "size": 65537,
        "manifest_identity": "0" * 64,
        "nonce": "000000000000000000000001",
        "ciphertext": b64encode(b"x" * 65553),
    }
    assert project.request("POST", "/v1/chunks", chunk).status_code == 400
    assert project.pull(limit=101).status_code == 401


def test_actual_cipher_quota_includes_chunks_and_retry_is_free(project):
    chunk = {
        "opaque_project_id": project.id,
        "opaque_locator": str(uuid4()),
        "key_epoch": 1,
        "index": 0,
        "total": 1,
        "size": 65536,
        "manifest_identity": "0" * 64,
        "nonce": "000000000000000000000001",
        "ciphertext": b64encode(b"x" * 65552),
    }
    assert project.request("POST", "/v1/chunks", chunk).status_code == 200
    first = None
    for _ in range(100):
        envelope = project.envelope({"synthetic": "x" * 180000})
        response = project.push([envelope])
        if response.status_code != 200:
            assert response.json()["code"] == "CIPHER_QUOTA_EXCEEDED"
            break
        if first is None:
            first = (envelope, response.content)
    else:
        raise AssertionError("Actual 16 MiB quota did not reject")
    with Session(project.network["engine"]) as db:
        pending = db.get(Project, project.id).pending_bytes
        count = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.project == project.id)
        )
        assert 16777216 - 180100 < pending <= 16777216
        assert pending == 65552 + count * (
            180000 + len(canonical_bytes({"synthetic": ""})) + 16
        )
    assert project.push([first[0]]).content == first[1]
    assert project.request("POST", "/v1/chunks", chunk).status_code == 200
    with Session(project.network["engine"]) as db:
        assert db.get(Project, project.id).pending_bytes == pending


def test_response_cache_full_rejects_before_business_mutation(project):
    for _ in range(3):
        assert (
            project.push([project.envelope({"pad": "x" * 120000})]).status_code == 200
        )
    for _ in range(30):
        response = project.pull()
        if response.status_code != 200:
            assert response.json()["code"] == "CACHE_FULL"
            break
    else:
        raise AssertionError("8 MiB response cache was not bounded")
    assert project.push([project.envelope()]).json()["code"] == "CACHE_FULL"
    with Session(project.network["engine"]) as db:
        row = db.get(Project, project.id)
        assert row.sequence == 3 and row.cache_bytes <= 8388608


def test_rate_failed_retry_restart_rolling_window(project):
    for n in range(120):
        request = project.prepare("POST", "/v1/hello", {})
        if n < 60:
            request["content"] = b'{"invalid":1}'
        response = project.send(request)
        assert response.status_code == (401 if n < 60 else 200)
    assert project.request("POST", "/v1/hello", {}).status_code == 429
    q, state, config = (project.network[k] for k in ("lifecycle", "state", "config"))
    q.guard_state(state, config)
    q.docker("restart", state["containers"][q.RELAY])
    q.wait_tls(state)
    assert project.request("POST", "/v1/hello", {}).status_code == 429
    with Session(project.network["engine"]) as db:
        from packages.secure_wire.canonical import strict_loads

        events = strict_loads(
            db.get(Budget, project.id + ":" + project.owner.device_id).events
        )
        assert len(events) == 120
        deadline = max(events) + 61
    while time.time() < deadline:
        time.sleep(0.2)
    assert project.send(request).status_code == 401  # Previously cached proof expired.
    assert project.request("POST", "/v1/hello", {}).status_code == 200
