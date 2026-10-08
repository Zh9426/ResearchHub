"""Reproducible Hypothesis schedules and measured actual loopback transport."""

import copy
import json
import platform
import statistics
import time
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from researchhub.sync.models import Audit
from researchhub.sync.secure.transport_pg import Trust, advance_history
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_transport import sealed, transaction

from packages.secure_wire.canonical import canonical_bytes


@settings(
    max_examples=6,
    derandomize=True,
    database=None,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    schedule=st.lists(
        st.sampled_from(("retry", "duplicate", "bad_page", "new_wrapper")),
        min_size=1,
        max_size=5,
    )
)
def test_generated_real_network_client_atomicity_schedule(trusted, project, schedule):
    import pytest

    client, person = trusted
    with Session(client.engine) as db:
        start = db.get(Trust, project.id).cursor
        audits = db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.project_id == person["project_id"])
        )
    tx = transaction(person)
    env = sealed(project, tx)
    client.enqueue(canonical_bytes(env))
    client.push(env["message_id"])
    page = client.pull(start)
    result = client.receive(page, start)
    cursor = start + 1
    for action in schedule:
        if action == "retry":
            client.push(env["message_id"])
        elif action == "duplicate":
            assert client.receive(page, start) == result
        elif action == "bad_page":
            bad = copy.deepcopy(page)
            bad["rows"][0]["envelope"]["ciphertext_digest"] = "a" * 64
            with pytest.raises(ValueError):
                client.receive(bad, start)
        else:
            wrapper = sealed(project, tx)
            client.enqueue(canonical_bytes(wrapper))
            client.push(wrapper["message_id"])
            client.receive(client.pull(cursor), cursor)
            cursor += 1
    with Session(client.engine) as db:
        assert db.get(Trust, project.id).cursor == cursor
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == audits + 1
        )


def test_measured_100_push_100_pull_with_distinct_legal_devices(trusted, project):
    from researchhub.sync.secure.transport import SecureTransport

    client, person = trusted
    reader = project.add("reader")
    advance_history(client.engine, project.id, project.manifest)
    receiving = SecureTransport(
        client.engine,
        project.id,
        reader,
        project.network["state"]["tls_directory"] + "/ca.crt",
        {1: project.key},
    )
    values = [sealed(project, transaction(person)) for _ in range(100)]
    raw_bytes = sum(len(canonical_bytes(value)) for value in values)
    for value in values:
        client.enqueue(canonical_bytes(value))
    start = time.perf_counter()
    push_samples = []
    for value in values:
        before = time.perf_counter()
        client.push(value["message_id"])
        push_samples.append(time.perf_counter() - before)
    pushed = time.perf_counter()
    pages, pull_samples = [], []
    for i in range(100):
        before = time.perf_counter()
        pages.append(receiving.pull(i, 1))
        pull_samples.append(time.perf_counter() - before)
    pulled = time.perf_counter()
    for i, page in enumerate(pages):
        assert len(page["rows"]) == 1
        receiving.receive(page, i)
    committed = time.perf_counter()
    receiving.close()
    result = {
        "scope": "SYNTHETIC_LOOPBACK_ONLY",
        "machine": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "push_calls": 100,
        "push_messages": 100,
        "pull_calls": 100,
        "pull_messages": 100,
        "envelope_bytes": raw_bytes,
        "push_seconds": pushed - start,
        "pull_seconds": pulled - pushed,
        "push_mean_ms": 1000 * statistics.mean(push_samples),
        "push_p95_ms": 1000 * sorted(push_samples)[94],
        "pull_mean_ms": 1000 * statistics.mean(pull_samples),
        "pull_p95_ms": 1000 * sorted(pull_samples)[94],
        "client_pg_apply_seconds": committed - pulled,
        "rolling_device_limit": 120,
        "limitation": "single-host sequential HTTPS; not distributed throughput; setup/sealing excluded",
    }
    Path("storage/runtime/secure-client-performance.json").write_text(
        json.dumps(result)
    )
    print("CLIENT_NETWORK_PERFORMANCE", json.dumps(result))


def test_actual_small_artifact_through_secure_transport(trusted, project):
    from uuid import uuid4

    from conftest import PRIVATE_MATERIAL
    from researchhub.sync.secure.artifacts import (
        TestOnlyMemoryStagingSink,
        open_artifact,
        seal_artifact,
    )
    from researchhub.sync.secure.crypto import kw_unwrap
    from researchhub.sync.secure.envelope import open_record

    from packages.secure_wire.envelope import b64decode

    client, _ = trusted
    data = b"SYNTHETIC_ARTIFACT_FILE_3ea954.mat" * 5000
    data = data[: 128 * 1024]
    t0 = time.perf_counter()
    bundle = seal_artifact(
        [data[i : i + 32768] for i in range(0, len(data), 32768)],
        {
            "filename": "SYNTHETIC_ARTIFACT_FILE_3ea954.mat",
            "category": "SYNTHETIC_CATEGORY_a2d6c0",
            "run_title": "SYNTHETIC_RUN_TITLE_b9c7df",
        },
        project.manifest,
        project.owner,
        project.key,
        project.vault,
        str(uuid4()),
    )
    t1 = time.perf_counter()
    inner = open_record(
        bundle["manifest_envelope"],
        project.key,
        bytes.fromhex(project.owner.signing_public),
        opaque_project_id=project.id,
        sender_device_id=project.owner.device_id,
        membership_epoch=1,
        key_epoch=1,
        nonce_prefix=0,
        record_type="artifact_manifest",
    )
    PRIVATE_MATERIAL.append(kw_unwrap(project.key, b64decode(inner["wrapped_dek"])))
    client.enqueue(canonical_bytes(bundle["manifest_envelope"]))
    client.push(bundle["manifest_envelope"]["message_id"])
    for chunk in bundle["chunks"]:
        client.request("POST", "/v1/chunks", chunk)
    page = client.pull(0)
    chunks = [
        client.request(
            "GET",
            "/v1/chunks",
            query={"opaque_locator": c["opaque_locator"], "index": c["index"]},
        )
        for c in bundle["chunks"]
    ]
    t2 = time.perf_counter()
    sink = TestOnlyMemoryStagingSink()
    open_artifact(
        {"manifest_envelope": page["rows"][0]["envelope"], "chunks": chunks},
        project.manifest,
        project.key,
        sink,
    )
    t3 = time.perf_counter()
    assert sink.ready
    result = {
        "bytes": len(data),
        "seal_ms": 1000 * (t1 - t0),
        "network_and_local_outbox_ms": 1000 * (t2 - t1),
        "open_ms": 1000 * (t3 - t2),
        "manifest_push_calls": 1,
        "manifest_pull_calls": 1,
        "chunk_push_calls": len(chunks),
        "chunk_pull_calls": len(chunks),
        "scope": "SYNTHETIC_LOOPBACK_ONLY",
    }
    Path("storage/runtime/secure-client-artifact-performance.json").write_text(
        json.dumps(result)
    )
    print("CLIENT_ARTIFACT_PERFORMANCE", json.dumps(result))
