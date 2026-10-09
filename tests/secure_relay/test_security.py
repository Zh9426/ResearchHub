"""Adversarial signed requests sent over real verified TLS, with direct PG checks."""

import hashlib
import time
from uuid import uuid4

import pytest
from conftest import device
from researchhub.sync.secure import keys, pairing
from researchhub_relay.models import PairSession, Project, RequestReceipt
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.envelope import b64decode, b64encode


@pytest.mark.parametrize(
    "field",
    [
        "version",
        "audience",
        "method",
        "path",
        "query",
        "opaque_project_id",
        "device_id",
        "membership_epoch",
        "key_epoch",
        "manifest_digest",
        "body_digest",
        "request_id",
        "issued_at",
        "signature",
    ],
)
def test_every_proof_field_is_bound(project, field):
    request = project.prepare("POST", "/v1/hello", {})
    proof = strict_loads(b64decode(request["headers"]["x-rh-proof"]))
    value = proof[field]
    proof[field] = (
        value + 1
        if type(value) is int
        else {"extra": 1}
        if type(value) is dict
        else ("A" if value[0] != "A" else "B") + value[1:]
    )
    request["headers"]["x-rh-proof"] = b64encode(canonical_bytes(proof))
    response = project.send(request)
    assert response.status_code == 401
    assert response.json() == {"ok": False, "code": "AUTH_REJECTED"}


def test_actual_method_path_query_body_and_duplicate_header_binding(project):
    for mutation in ("method", "url", "content", "headers"):
        request = project.prepare("POST", "/v1/hello", {})
        if mutation == "method":
            request[mutation] = "GET"
        elif mutation == "url":
            request[mutation] = "/v1/messages"
        elif mutation == "content":
            request[mutation] = b'{"x":1}'
        else:
            request[mutation] = [
                *request[mutation].items(),
                ("x-rh-proof", request["headers"]["x-rh-proof"]),
            ]
        assert project.send(request).status_code == 401
    for suffix in (
        "cursor=00&limit=100",
        "cursor=0&cursor=1&limit=100",
        "%63ursor=0&limit=100",
        "cursor=0&limit=100&unknown=1",
    ):
        request = project.prepare(
            "GET", "/v1/messages", query={"cursor": 0, "limit": 100}
        )
        request["url"] = "/v1/messages?" + suffix
        assert project.send(request).status_code == 401


def test_expired_revoked_epoch_requests_rejected_before_cache(project):
    reader = project.add()
    request = project.prepare(
        "GET", "/v1/messages", query={"cursor": 0, "limit": 100}, signer=reader
    )
    assert project.send(request).status_code == 200
    assert (
        project.pull(signer=reader, issued_at=int(time.time()) - 61).status_code == 401
    )
    # Real TLS checks an unambiguously future request. Exact +5/+6 boundaries
    # use a fixed verifier/service clock in the dedicated request-time tests:
    # a network request signed at client T+6 may reach the server at T+1.
    assert (
        project.pull(signer=reader, issued_at=int(time.time()) + 3600).status_code == 401
    )
    previous = project.manifest
    candidate = keys.transition(previous, project.owner, revoke=reader.device_id)
    assert (
        project.request("POST", "/v1/membership", {"manifest": candidate}).status_code
        == 200
    )
    project.manifest = candidate
    assert project.send(request).status_code == 401
    assert project.pull(signer=reader).status_code == 401
    assert project.pull(manifest=previous).status_code == 401


def test_reader_pending_recovery_cannot_push_or_self_register(project):
    reader = project.add()
    pending = project.add(status="PENDING")
    envelope = project.envelope()
    assert project.pull(signer=reader).status_code == 200
    for signer in (reader, pending, project.kit, device()):
        assert project.push([envelope], signer=signer).status_code == 401
    for signer in (pending, project.kit, device()):
        assert project.pull(signer=signer).status_code == 401
    assert (
        project.request("POST", "/v1/hello", {"manifest": project.manifest}).status_code
        == 400
    )


def test_seen_missing_response_and_collision_fail_closed(project):
    request = project.prepare("POST", "/v1/hello", {})
    assert project.send(request).status_code == 200
    proof = strict_loads(b64decode(request["headers"]["x-rh-proof"]))
    other = project.prepare(
        "GET",
        "/v1/messages",
        query={"cursor": 0, "limit": 100},
        request_id=proof["request_id"],
    )
    assert project.send(other).json()["code"] == "REQUEST_ID_COLLISION"
    with Session(project.network["engine"]) as db, db.begin():
        db.get(
            RequestReceipt, (project.id, project.owner.device_id, proof["request_id"])
        ).response = None
    assert project.send(request).json()["code"] == "RECEIPT_UNAVAILABLE"


def test_nonce_identity_and_old_epoch_durable_receipt(project):
    member = project.add()
    envelope = project.envelope()
    original = project.push([envelope])
    assert original.status_code == 200
    changed = {**envelope, "message_id": str(uuid4())}
    changed = keys.signed_object("SecureEnvelope", changed, project.owner.signing_seed)
    assert project.push([changed]).json()["code"] == "NONCE_REUSED"
    changed = {**envelope, "checkpoint_sequence": 10}
    assert project.push([changed]).json()["code"] == "MESSAGE_ID_COLLISION"
    candidate = keys.transition(
        project.manifest, project.owner, revoke=member.device_id
    )
    assert (
        project.request("POST", "/v1/membership", {"manifest": candidate}).status_code
        == 200
    )
    project.manifest = candidate
    assert project.push([envelope]).content == original.content
    assert project.push([{**envelope, "message_id": str(uuid4())}]).status_code == 400


def trusted_challenge(project, *, now=None):
    store = keys.TrustedStore(project.directory / (str(uuid4()) + ".sqlite"))
    store.bootstrap(
        project.manifest, project.owner.signing_public, project.kit.signing_public
    )
    recipient = device()
    now = int(time.time()) if now is None else now
    challenge = pairing.create_challenge(
        store, project.owner, recipient.member("reader", 1), now=now
    )
    return store, recipient, challenge


def test_owner_can_fetch_own_pairing_submissions(project):
    _, _recipient, challenge = trusted_challenge(project)
    assert (
        project.request(
            "POST", "/v1/pairing/challenge", {"challenge": challenge}
        ).status_code
        == 200
    )
    result = project.request(
        "GET", "/v1/pairing/challenge", query={"session_id": challenge["session_id"]}
    )
    assert result.status_code == 200
    assert result.json()["result"]["submissions"] == []


def test_pairing_five_unique_attempts_survive_restart(project):
    _, recipient, challenge = trusted_challenge(project)
    assert (
        project.request(
            "POST", "/v1/pairing/challenge", {"challenge": challenge}
        ).status_code
        == 200
    )
    for n in range(5):
        proof = keys.signed_object(
            "PairingProof",
            {
                "challenge_digest": digest(challenge),
                "challenge_response": hashlib.sha256(str(n).encode()).hexdigest(),
                "confirmation": pairing.confirmation(challenge),
            },
            recipient.signing_seed,
        )
        request = project.prepare(
            "POST",
            "/v1/pairing/submit",
            {"session_id": challenge["session_id"], "proof": proof},
            signer=recipient,
        )
        response = project.send(request)
        assert response.status_code == 200
        assert response.json()["result"] == {
            "state": "SUBMITTED",
            "attempts": n + 1,
            "x25519_possession_verified": False,
        }
        assert project.send(request).content == response.content
    q, state, config = (project.network[k] for k in ("lifecycle", "state", "config"))
    q.guard_state(state, config)
    q.docker("restart", state["containers"][q.RELAY])
    q.wait_tls(state)
    proof = keys.signed_object(
        "PairingProof",
        {
            "challenge_digest": digest(challenge),
            "challenge_response": "f" * 64,
            "confirmation": pairing.confirmation(challenge),
        },
        recipient.signing_seed,
    )
    assert (
        project.request(
            "POST",
            "/v1/pairing/submit",
            {"session_id": challenge["session_id"], "proof": proof},
            signer=recipient,
        ).json()["code"]
        == "PAIRING_ATTEMPTS_EXCEEDED"
    )


def test_pair_complete_receipt_and_expiry(project):
    store, recipient, challenge = trusted_challenge(project)
    assert (
        project.request(
            "POST", "/v1/pairing/challenge", {"challenge": challenge}
        ).status_code
        == 200
    )
    proof = pairing.answer_challenge(
        challenge,
        project.manifest,
        recipient,
        confirmation=pairing.confirmation(challenge),
        now=int(time.time()),
    )
    assert (
        project.request(
            "POST",
            "/v1/pairing/submit",
            {"session_id": challenge["session_id"], "proof": proof},
            signer=recipient,
        ).status_code
        == 200
    )
    receipt = pairing.consume(
        store, project.owner, challenge, proof, project.key, now=int(time.time())
    )
    prepared = project.prepare(
        "POST",
        "/v1/pairing/complete",
        {"session_id": challenge["session_id"], "receipt": receipt},
    )
    result = project.send(prepared)
    assert result.status_code == 200
    project.manifest = receipt["manifest"]
    assert project.send(prepared).status_code == 401
    found = project.request(
        "GET",
        "/v1/pairing/receipt",
        query={"session_id": challenge["session_id"]},
        signer=recipient,
    )
    assert found.status_code == 200 and found.json()["result"] == receipt
    assert (
        project.request(
            "GET",
            "/v1/grants",
            query={"session_id": challenge["session_id"]},
            signer=recipient,
        ).status_code
        == 200
    )


def test_expired_challenge_persists_public_expired_state(project):
    _, recipient, challenge = trusted_challenge(project, now=int(time.time()) - 299)
    assert (
        project.request(
            "POST", "/v1/pairing/challenge", {"challenge": challenge}
        ).status_code
        == 200
    )
    q, state, config = (project.network[k] for k in ("lifecycle", "state", "config"))
    q.guard_state(state, config)
    q.docker("restart", state["containers"][q.RELAY])
    q.wait_tls(state)
    deadline = challenge["expires_at"]
    while time.time() < deadline:
        time.sleep(0.05)
    assert (
        project.request(
            "GET",
            "/v1/pairing/challenge",
            query={"session_id": challenge["session_id"]},
            signer=recipient,
        ).status_code
        == 401
    )
    with Session(project.network["engine"]) as db:
        assert (
            db.get(PairSession, (project.id, challenge["session_id"])).state
            == "EXPIRED"
        )


def test_recovery_is_pinned_profile_and_cannot_read_messages(project):
    from researchhub.sync.secure.checkpoint import sign_checkpoint

    store = keys.TrustedStore(project.directory / "recovery.sqlite")
    store.bootstrap(
        project.manifest, project.owner.signing_public, project.kit.signing_public
    )
    project.kit.update_anchor(
        project.manifest,
        sign_checkpoint(project.manifest, project.owner, 0, "0" * 64),
        store=store,
    )
    new_owner = device()
    candidate = keys.recover(store, project.kit, new_owner)
    assert (
        project.request(
            "POST", "/v1/membership/recovery", {"manifest": candidate}, signer=new_owner
        ).status_code
        == 401
    )
    assert (
        project.request(
            "POST", "/v1/membership", {"manifest": candidate}, signer=project.kit
        ).status_code
        == 401
    )
    assert project.pull(signer=project.kit).status_code == 401
    assert (
        project.request(
            "POST",
            "/v1/membership/recovery",
            {"manifest": candidate},
            signer=project.kit,
        ).status_code
        == 200
    )
    project.manifest = candidate
    assert project.pull().status_code == 401
    assert project.pull(signer=new_owner).status_code == 200
    assert project.pull(signer=project.kit).status_code == 401


def test_device_ack_and_checkpoint_are_bound_signed_claims(project):
    from researchhub.sync.secure.checkpoint import sign_checkpoint

    reader = project.add()
    envelope = project.envelope()
    assert project.push([envelope]).status_code == 200
    for stage in (
        "DEVICE_RECEIVED",
        "DEVICE_DECRYPTED",
        "KERNEL_APPLIED",
        "SCIENTIFIC_ACCEPTED",
        "ARTIFACT_PRIMARY_DURABLE",
    ):
        ack = keys.signed_object(
            "RelayAck",
            {
                "version": 1,
                "opaque_project_id": project.id,
                "device_id": reader.device_id,
                "message_id": envelope["message_id"],
                "sequence": 1,
                "stage": stage,
                "retain_until_ack": True,
            },
            reader.signing_seed,
        )
        assert project.request("POST", "/v1/ack", ack, signer=reader).status_code == 200
        assert project.request("POST", "/v1/ack", ack).status_code == 400
    page = project.pull().json()["result"]
    checkpoint = sign_checkpoint(project.manifest, reader, 1, page["chain_digest"])
    assert (
        project.request(
            "POST", "/v1/checkpoints", {"checkpoint": checkpoint}, signer=reader
        ).status_code
        == 200
    )
    assert (
        project.request(
            "POST", "/v1/checkpoints", {"checkpoint": checkpoint}
        ).status_code
        == 400
    )
    assert project.request("GET", "/v1/checkpoints").json()["result"][
        "checkpoints"
    ] == [checkpoint]


def test_grant_get_cache_does_not_query_future_grant(project):
    reader = project.add()
    session = str(uuid4())
    prepared = project.prepare(
        "GET", "/v1/grants", query={"session_id": session}, signer=reader
    )
    before = project.send(prepared)
    assert before.status_code == 400
    grant = keys.make_grant(
        project.manifest, project.owner, reader.device_id, session, project.key
    )
    assert project.request("POST", "/v1/grants", {"grant": grant}).status_code == 200
    assert project.send(prepared).content == before.content
    assert (
        project.request(
            "GET", "/v1/grants", query={"session_id": session}, signer=reader
        ).json()["result"]
        == grant
    )


def test_pending_pairing_exception_is_own_session_only(project):
    genesis = project.manifest
    pending = project.add(status="PENDING")
    store = keys.TrustedStore(project.directory / "pending-trusted.sqlite")
    store.bootstrap(genesis, project.owner.signing_public, project.kit.signing_public)
    store.accept(project.manifest)
    member = next(
        m for m in project.manifest["members"] if m["device_id"] == pending.device_id
    )
    recipient = {**member, "status": "ACTIVE"}
    now = int(time.time())
    challenge = pairing.create_challenge(store, project.owner, recipient, now=now)
    session = challenge["session_id"]
    assert (
        project.request(
            "POST", "/v1/pairing/challenge", {"challenge": challenge}
        ).status_code
        == 200
    )
    assert (
        project.request(
            "GET",
            "/v1/pairing/challenge",
            query={"session_id": session},
            signer=pending,
        ).status_code
        == 200
    )
    assert (
        project.request(
            "GET",
            "/v1/pairing/challenge",
            query={"session_id": str(uuid4())},
            signer=pending,
        ).status_code
        == 401
    )
    proof = pairing.answer_challenge(
        challenge,
        project.manifest,
        pending,
        confirmation=pairing.confirmation(challenge),
        now=now,
    )
    assert (
        project.request(
            "POST",
            "/v1/pairing/submit",
            {"session_id": session, "proof": proof},
            signer=pending,
        ).status_code
        == 200
    )
    assert project.pull(signer=pending).status_code == 401
    previous = project.manifest
    receipt = pairing.consume(
        store, project.owner, challenge, proof, project.key, now=now
    )
    assert (
        project.request(
            "POST", "/v1/pairing/complete", {"session_id": session, "receipt": receipt}
        ).status_code
        == 200
    )
    project.manifest = receipt["manifest"]
    assert project.manifest["membership_epoch"] == previous["membership_epoch"] + 1
    assert project.manifest["key_epoch"] == previous["key_epoch"]
    assert project.manifest["members"] == [previous["members"][0], recipient]
    found = project.request(
        "GET", "/v1/pairing/receipt", query={"session_id": session}, signer=pending
    )
    assert found.status_code == 200 and found.json()["result"] == receipt
    grant = project.request(
        "GET", "/v1/grants", query={"session_id": session}, signer=pending
    )
    assert grant.status_code == 200
    assert bool(
        keys.open_grant(grant.json()["result"], project.manifest, pending)
        == project.key
    )
    assert project.pull(signer=pending).status_code == 200
    assert (
        project.push([project.envelope(signer=pending)], signer=pending).status_code
        == 401
    )
    assert (
        project.request(
            "POST", "/v1/membership", {"manifest": project.manifest}, signer=pending
        ).status_code
        == 401
    )


def test_request_expiry_is_rechecked_after_project_lock_wait(project):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    prepared = project.prepare("POST", "/v1/hello", {}, issued_at=int(time.time()) - 59)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(project.network["engine"]) as db, db.begin():
            db.scalar(select(Project).where(Project.id == project.id).with_for_update())
            response = pool.submit(project.send, prepared)
            time.sleep(2.2)
        assert response.result().status_code == 401


def test_unauthenticated_malformed_pairing_body_has_no_existence_oracle(project):
    stranger = device()
    for body in ([], None, "invalid", 1):
        response = project.request("POST", "/v1/pairing/submit", body, signer=stranger)
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_REJECTED"
