"""Trusted client against actual TLS Relay and independent S1 PostgreSQL."""

import copy
import importlib.util
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def transaction(person):
    identity = str(uuid4())
    tx = {k: person[k] for k in ("project_id", "device_id", "actor_id", "actor_type")}
    tx.update(
        transaction_id=identity,
        idempotency_key=identity,
        protocol_version=1,
        schema_version=1,
        created_at="2026-10-07T01:02:03.004Z",
        dependencies=[],
    )
    change = {
        k: tx[k]
        for k in (
            "project_id",
            "device_id",
            "actor_id",
            "actor_type",
            "transaction_id",
            "schema_version",
            "created_at",
        )
    }
    change.update(
        change_id=str(uuid4()),
        audit_id=str(uuid4()),
        object_id=str(uuid4()),
        object_type="Parameter",
        operation="create",
        parents=[],
        payload={
            "name": "SYNTHETIC_PARAMETER_a6e841",
            "value_type": "decimal",
            "value": "1.400",
        },
        module_snapshot_hash="a" * 64,
    )
    tx.update(changes=[change], ordered_change_ids=[change["change_id"]])
    return tx


def sealed(project, tx):
    from researchhub.sync.secure.envelope import seal_transaction

    return seal_transaction(
        tx,
        project.key,
        project.owner.signing_seed,
        project.vault,
        0,
        opaque_project_id=project.id,
        sender_device_id=project.owner.device_id,
        membership_epoch=project.manifest["membership_epoch"],
        key_epoch=project.manifest["key_epoch"],
        message_id=str(uuid4()),
    )


def test_trusted_transport_implementation_exists():
    assert importlib.util.find_spec("researchhub.sync.secure.transport"), (
        "Task3B trusted transport is missing"
    )


def test_real_transport_cached_outbox_duplicate_page_and_new_wrapper(trusted, project):
    from researchhub.sync.models import Audit, ProjectState

    from packages.secure_wire.canonical import canonical_bytes

    client, person = trusted
    tx = transaction(person)
    envelope = sealed(project, tx)
    client.enqueue(canonical_bytes(envelope))
    assert client.push(envelope["message_id"]) == client.push(envelope["message_id"])
    page = client.pull(0)
    result = client.receive(page, 0)
    assert client.receive(page, 0) == result
    wrapper = sealed(project, tx)
    client.enqueue(canonical_bytes(wrapper))
    client.push(wrapper["message_id"])
    client.receive(client.pull(1), 1)
    with Session(client.engine) as db:
        assert db.get(ProjectState, person["project_id"]).received_cursor == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == 1
        )
    changed = copy.deepcopy(page)
    changed["rows"][0]["chain_digest"] = "a" * 64
    with pytest.raises(ValueError):
        client.receive(changed, 0)


def test_entire_page_failure_rolls_back_real_kernel(trusted, project):
    from researchhub.sync.models import ProjectState

    client, person = trusted
    envelopes = [sealed(project, transaction(person)) for _ in range(2)]
    assert project.push(envelopes).status_code == 200
    page = client.pull(0)
    page["rows"][1]["envelope"]["signature"] = page["rows"][0]["envelope"]["signature"]
    with pytest.raises(ValueError):
        client.receive(page, 0)
    with Session(client.engine) as db:
        assert db.get(ProjectState, person["project_id"]).received_cursor == 0


def test_ack_and_checkpoint_are_persisted_verified_and_monotone(trusted, project):
    from researchhub.sync.secure.checkpoint import sign_checkpoint
    from researchhub.sync.secure.transport_pg import Trust

    from packages.secure_wire.canonical import strict_loads

    client, person = trusted
    assert project.push([sealed(project, transaction(person))]).status_code == 200
    page = client.pull(0)
    client.receive(page, 0)
    assert client.ack(1)
    with Session(client.engine) as db:
        cp = strict_loads(db.get(Trust, project.id).checkpoint)
    assert client.accept_checkpoint(cp) == cp
    for bad in (
        sign_checkpoint(project.manifest, project.owner, 0, "0" * 64),
        sign_checkpoint(project.manifest, project.owner, 1, "a" * 64),
    ):
        with pytest.raises(ValueError):
            client.accept_checkpoint(bad)


@pytest.mark.parametrize(
    "mutation",
    [
        "gap",
        "missing",
        "cursor",
        "extra",
        "order",
        "signature",
        "digest",
        "aead",
        "inner_project",
        "inner_device",
        "dependencies",
        "unknown_epoch",
        "wrong_key_epoch",
    ],
)
@pytest.mark.parametrize("historical", [False, True])
def test_bad_whole_page_never_commits(trusted, project, mutation, historical):
    from researchhub.sync.models import Audit, ProjectState
    from researchhub.sync.secure.crypto import sign
    from researchhub.sync.secure.envelope import seal_record
    from researchhub.sync.secure.transport_pg import Received, Trust

    from packages.secure_wire.canonical import digest
    from packages.secure_wire.checkpoint import extend_chain
    from packages.secure_wire.envelope import b64encode, signature_preimage

    client, person = trusted
    txs = [transaction(person) for _ in range(2)]
    assert project.push([sealed(project, t) for t in txs]).status_code == 200
    if historical:
        from researchhub.sync.secure.transport_pg import advance_history

        project.add()
        advance_history(client.engine, project.id, project.manifest)
    page = client.pull(0)
    env = page["rows"][1]["envelope"]
    if mutation == "gap":
        page["rows"][1]["sequence"] = 3
    elif mutation == "missing":
        page["rows"].pop(0)
    elif mutation == "cursor":
        page["cursor"] += 1
    elif mutation == "extra":
        page["extra"] = True
    elif mutation == "order":
        page["rows"].reverse()
    elif mutation == "signature":
        env["signature"] = page["rows"][0]["envelope"]["signature"]
    elif mutation == "digest":
        env["semantic_transaction_digest"] = "a" * 64
    elif mutation == "unknown_epoch":
        env["membership_epoch"] = 9
    elif mutation == "wrong_key_epoch":
        env["key_epoch"] = 9
    elif mutation == "aead":
        env["nonce"] = env["nonce"][:-2] + "ff"
    else:
        tx = txs[1]
        if mutation == "inner_project":
            tx["project_id"] = str(uuid4())
        elif mutation == "inner_device":
            tx["device_id"] = str(uuid4())
        elif mutation == "dependencies":
            tx["dependencies"] = [str(uuid4())]
        page["rows"][1]["envelope"] = seal_record(
            tx,
            project.key,
            project.owner.signing_seed,
            project.vault,
            0,
            opaque_project_id=project.id,
            sender_device_id=project.owner.device_id,
            membership_epoch=1,
            key_epoch=1,
            message_id=str(uuid4()),
            record_type="transaction",
        )
    if mutation in ("digest", "aead", "unknown_epoch", "wrong_key_epoch"):
        env["signature"] = b64encode(
            sign(project.owner.signing_seed, signature_preimage(env))
        )
    # A hostile Relay can consistently recompute its unauthenticated outer chain.
    if mutation not in ("gap", "missing", "cursor", "extra", "order"):
        chain = "0" * 64
        for row in page["rows"]:
            row["envelope_digest"] = digest(row["envelope"])
            chain = extend_chain(
                chain,
                row["sequence"] - 1,
                [
                    {
                        "sequence": row["sequence"],
                        "envelope_digest": row["envelope_digest"],
                    }
                ],
            )
            row["chain_digest"] = chain
        page["chain_digest"] = chain
    with pytest.raises(ValueError):
        client.receive(page, 0)
    with Session(client.engine) as db:
        assert db.get(ProjectState, person["project_id"]).received_cursor == 0
        assert db.get(Trust, project.id).cursor == 0
        for model in (Received,):
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project == project.id)
                )
                == 0
            )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == 0
        )


def test_historical_durable_page_quarantines_and_unknown_history_rejects(
    trusted, project
):
    from researchhub.sync.models import ProjectState
    from researchhub.sync.secure.transport_pg import advance_history

    client, person = trusted
    assert project.push([sealed(project, transaction(person))]).status_code == 200
    project.add()
    advance_history(client.engine, project.id, project.manifest)
    page = client.pull(0)
    assert client.receive(page, 0)[0]["state"] == "TRANSPORT_QUARANTINED"
    with Session(client.engine) as db:
        assert db.get(ProjectState, person["project_id"]).received_cursor == 0


def test_wire_human_cannot_override_registered_ai(trusted, project):
    client, person = trusted
    tx = transaction(person)
    tx["actor_type"] = tx["changes"][0]["actor_type"] = "human"
    assert project.push([sealed(project, tx)]).status_code == 200
    with pytest.raises(ValueError, match="wire identity differs"):
        client.receive(client.pull(0), 0)


def test_bad_server_database_url_rejected_before_connect(monkeypatch):
    from researchhub.sync.secure.transport_pg import client_engine

    monkeypatch.setenv("HUB_SYNC_QA", "1")
    for url in (
        "postgresql+psycopg://researchhub_sync_qa@127.0.0.1:35434/researchhub_sync_kernel_qa",
        "postgresql+psycopg://researchhub_sync_qa@example.invalid:35433/researchhub_sync_kernel_qa",
    ):
        monkeypatch.setenv("HUB_SYNC_QA_URL", url)
        with pytest.raises(RuntimeError):
            client_engine()


@pytest.mark.parametrize(
    "suffix",
    ["?host=example.invalid", "?port=5432", "?dbname=product", "?service=personal", ""],
)
def test_driver_overrides_and_missing_password_rejected_without_connection(
    monkeypatch, suffix
):
    from researchhub.sync.secure.transport_pg import guard
    from sqlalchemy import create_engine

    monkeypatch.setenv("HUB_SYNC_QA", "1")
    auth = (
        "researchhub_sync_qa:TEST_ONLY_NEVER_CONNECTED"
        if suffix
        else "researchhub_sync_qa"
    )
    engine = create_engine(
        "postgresql+psycopg://"
        + auth
        + "@127.0.0.1:35433/researchhub_sync_kernel_qa"
        + suffix
    )
    with pytest.raises(RuntimeError):
        guard(engine)


def test_human_grant_and_atomic_kernel_barrier(trusted, project):
    from researchhub.sync.authority import TrustedContext, issue_grant
    from researchhub.sync.models import Audit, Principal, ProjectState

    client, person = trusted
    with Session(client.engine) as db, db.begin():
        db.get(Principal, person["principal_id"]).actor_type = "human"
    person["actor_type"] = "human"
    tx = transaction(person)
    tx["changes"][0]["payload"]["is_confirmed"] = True
    assert project.push([sealed(project, tx)]).status_code == 200
    page = client.pull(0)
    with pytest.raises(ValueError):
        client.receive(page, 0)
    with Session(client.engine) as db, db.begin():
        assert db.get(ProjectState, person["project_id"]).received_cursor == 0
        grant = issue_grant(db, TrustedContext(person["principal_id"]), tx)
    assert (
        client.receive(page, 0, grants={tx["transaction_id"]: grant})[0]["state"]
        == "ACCEPTED"
    )
    assert client.receive(page, 0)[0]["state"] == "ACCEPTED"
    with Session(client.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == 1
        )


def test_kernel_failure_after_first_item_rolls_back_all_tables(trusted, project):
    from researchhub.sync.models import (
        AcceptedProjection,
        Audit,
        ObjectRevision,
        ProjectState,
    )
    from researchhub.sync.secure.transport_pg import Trust

    client, person = trusted
    good, bad = transaction(person), transaction(person)
    bad["dependencies"] = [str(uuid4())]
    assert (
        project.push([sealed(project, good), sealed(project, bad)]).status_code == 200
    )
    with pytest.raises(ValueError):
        client.receive(client.pull(0), 0)
    with Session(client.engine) as db:
        for model in (Audit, ObjectRevision, AcceptedProjection):
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project_id == person["project_id"])
                )
                == 0
            )
        assert db.get(ProjectState, person["project_id"]).received_cursor == 0
        assert db.get(Trust, project.id).checkpoint is None


def test_partial_pages_out_of_order_and_outbox_identity_collision(trusted, project):
    from packages.secure_wire.canonical import canonical_bytes

    client, person = trusted
    values = [sealed(project, transaction(person)) for _ in range(3)]
    client.enqueue(canonical_bytes(values[0]))
    changed = sealed(project, transaction(person))
    changed["message_id"] = values[0]["message_id"]
    from researchhub.sync.secure.crypto import sign

    from packages.secure_wire.envelope import b64encode, signature_preimage

    changed["signature"] = b64encode(
        sign(project.owner.signing_seed, signature_preimage(changed))
    )
    with pytest.raises(ValueError, match="OUTBOX_IDENTITY_COLLISION"):
        client.enqueue(canonical_bytes(changed))
    assert project.push(values).status_code == 200
    with pytest.raises(ValueError, match="CURSOR_GAP"):
        client.receive(client.pull(1, 1), 1)
    for i in range(3):
        assert len(client.receive(client.pull(i, 1), i)) == 1


def test_checkpoint_corruption_is_reverified_on_every_receive(trusted, project):
    from researchhub.sync.secure.transport_pg import Trust

    from packages.secure_wire.canonical import canonical_bytes, strict_loads

    client, person = trusted
    assert project.push([sealed(project, transaction(person))]).status_code == 200
    page = client.pull(0)
    client.receive(page, 0)
    with Session(client.engine) as db, db.begin():
        row = db.get(Trust, project.id)
        cp = strict_loads(row.checkpoint)
        cp["signature"] = page["rows"][0]["envelope"]["signature"]
        row.checkpoint = canonical_bytes(cp)
    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        client.receive(page, 0)


def test_trusted_history_update_waits_for_receive_transaction(trusted, project):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from researchhub.sync.secure.transport_pg import Trust, advance_history

    from packages.secure_wire.canonical import strict_loads

    client, person = trusted
    assert project.push([sealed(project, transaction(person))]).status_code == 200
    page = client.pull(0)
    project.add()
    entered, release, attempted = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def barrier(point):
        if point == "before_commit":
            entered.set()
            assert release.wait(8)

    def rotate():
        attempted.set()
        advance_history(client.engine, project.id, project.manifest)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receiving = pool.submit(client.receive, page, 0, barrier=barrier)
        assert entered.wait(8)
        rotation = pool.submit(rotate)
        assert attempted.wait(8)
        assert not rotation.done()
        release.set()
        receiving.result(timeout=8)
        rotation.result(timeout=8)
    with Session(client.engine) as db:
        history = strict_loads(db.get(Trust, project.id).history)
        assert history[-1] == project.manifest
    assert client.receive(
        page, 0
    )  # Original checkpoint remains verified after authority changes.


def test_revoked_writer_cannot_push_and_durable_historical_is_quarantined(
    trusted, project
):
    from researchhub.sync.secure import keys
    from researchhub.sync.secure.envelope import seal_transaction
    from researchhub.sync.secure.nonce import NonceVault
    from researchhub.sync.secure.transport import SecureTransport
    from researchhub.sync.secure.transport_pg import advance_history

    from packages.secure_wire.canonical import canonical_bytes

    client, person = trusted
    writer = project.add("writer")
    advance_history(client.engine, project.id, project.manifest)
    writer_client = SecureTransport(
        client.engine,
        project.id,
        writer,
        project.network["state"]["tls_directory"] + "/ca.crt",
        {1: project.key},
    )
    vault = NonceVault(project.directory / "writer-nonce.sqlite")
    vault.register_new(project.key, 1)
    person = {**person, "device_id": writer.device_id}
    env = seal_transaction(
        transaction(person),
        project.key,
        writer.signing_seed,
        vault,
        1,
        opaque_project_id=project.id,
        sender_device_id=writer.device_id,
        membership_epoch=2,
        key_epoch=1,
        message_id=str(uuid4()),
    )
    writer_client.enqueue(canonical_bytes(env))
    writer_client.push(env["message_id"])
    candidate = keys.transition(
        project.manifest, project.owner, revoke=writer.device_id
    )
    assert (
        project.request("POST", "/v1/membership", {"manifest": candidate}).status_code
        == 200
    )
    project.manifest = candidate
    advance_history(client.engine, project.id, candidate)
    with pytest.raises(ValueError, match="REVOKED_DEVICE"):
        writer_client.push(env["message_id"])
    assert client.receive(client.pull(0), 0)[0]["state"] == "TRANSPORT_QUARANTINED"
    writer_client.close()


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_real_client_process_kill_at_commit_boundary(trusted, project, point):
    import json
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    from researchhub.sync.models import Audit, ProjectState
    from researchhub.sync.secure.transport_pg import Trust

    client, person = trusted
    assert (
        project.push(
            [sealed(project, transaction(person)) for _ in range(2)]
        ).status_code
        == 200
    )
    directory = Path("storage/runtime/secure-client-crash") / str(uuid4())
    directory.mkdir(parents=True)
    barrier = directory / "barrier"
    config = {
        "project": project.id,
        "device": project.owner.device_id,
        "signing": project.owner.signing_seed.hex(),
        "recipient": project.owner.recipient_seed.hex(),
        "key": project.key.hex(),
        "ca": project.network["state"]["tls_directory"] + "/ca.crt",
        "point": point,
        "barrier": str(barrier.resolve()),
    }
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("transport_worker.py"))],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        process.stdin.write(json.dumps(config).encode())
        process.stdin.close()
        deadline = time.monotonic() + 30
        while (
            not barrier.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert barrier.exists(), (
            "Child did not reach the exact PG barrier; details suppressed"
        )
        process.kill()
        process.wait(timeout=10)
        assert process.returncode != 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    committed = 2 if point == "after_commit" else 0
    with Session(client.engine) as db:
        assert db.get(ProjectState, person["project_id"]).received_cursor == committed
        assert db.get(Trust, project.id).cursor == committed
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == committed
        )
    page = client.pull(0)
    first = client.receive(page, 0)
    assert client.receive(page, 0) == first
    assert client.ack(2)["stage"] == "DEVICE_DECRYPTED"
    with Session(client.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.project_id == person["project_id"])
            )
            == 2
        )


def test_scientific_candidate_can_ack_without_acceptance(trusted, project):
    from researchhub.sync.models import ProjectState

    client, person = trusted
    first, second = transaction(person), transaction(person)
    second["changes"][0]["object_id"] = first["changes"][0]["object_id"]
    assert (
        project.push([sealed(project, first), sealed(project, second)]).status_code
        == 200
    )
    result = client.receive(client.pull(0), 0)
    assert result[-1]["state"] == "CANDIDATE"
    assert client.ack(2)["stage"] == "DEVICE_DECRYPTED"
    with Session(client.engine) as db:
        state = db.get(ProjectState, person["project_id"])
        assert state.received_cursor == 2 and state.accepted_watermark == 0
