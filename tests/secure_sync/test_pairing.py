import copy
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packages.secure_wire.membership import challenge_sas
from tests.secure_sync.test_lifecycle import api, setup_project


def test_pairing_proves_both_private_keys_and_single_use_receipt(tmp_path):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("reader", 1), now=100)
    proof = p.answer_challenge(
        challenge, old, b, confirmation=p.confirmation(challenge), now=101
    )
    key = k.TestOnlyKeyVault().create(old["opaque_project_id"], 1)
    receipt = p.consume(store, owner, challenge, proof, key, now=102)
    assert k.open_grant(receipt["grant"], receipt["manifest"], b) == key
    with pytest.raises(ValueError, match="PAIRING_USED"):
        p.consume(store, owner, challenge, proof, key, now=102)
    assert (
        p.retry_receipt(k.TrustedStore(store.path), challenge, b.device_id) == receipt
    )
    revoked = k.transition(receipt["manifest"], owner, revoke=b.device_id)
    store.accept(revoked)
    with pytest.raises(ValueError, match="REVOKED_DEVICE"):
        p.retry_receipt(store, challenge, b.device_id)


@pytest.mark.parametrize("fault", ["before_commit", "after_commit"])
def test_pairing_transaction_crash_boundaries(tmp_path, fault):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("writer", 1), now=100)
    proof = p.answer_challenge(
        challenge, old, b, confirmation=p.confirmation(challenge), now=101
    )
    key = k.TestOnlyKeyVault().create(old["opaque_project_id"], 1)
    with pytest.raises(RuntimeError, match="SYNTHETIC_CRASH"):
        p.consume(store, owner, challenge, proof, key, now=102, crash_point=fault)
    restarted = k.TrustedStore(store.path)
    if fault == "before_commit":
        assert restarted.current(old["opaque_project_id"]) == old
        p.consume(restarted, owner, challenge, proof, key, now=102)
    else:
        assert (
            p.retry_receipt(restarted, challenge, b.device_id)["manifest"][
                "membership_epoch"
            ]
            == 2
        )


def test_pairing_expiry_bad_scope_and_attempt_limit_persist(tmp_path):
    _, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("reader", 1), now=100)
    with pytest.raises(ValueError, match="PAIRING_EXPIRED"):
        p.answer_challenge(
            challenge, old, b, confirmation=p.confirmation(challenge), now=401
        )
    proof = p.answer_challenge(
        challenge, old, b, confirmation=p.confirmation(challenge), now=101
    )
    bad = copy.deepcopy(proof)
    bad["challenge_response"] = "00" * 32
    for _ in range(5):
        with pytest.raises(ValueError):
            p.consume(store, owner, challenge, bad, bytes(32), now=102)
    with pytest.raises(ValueError, match="PAIRING_ATTEMPTS_EXCEEDED"):
        p.consume(
            api().TrustedStore(store.path), owner, challenge, proof, bytes(32), now=102
        )


@pytest.mark.parametrize(
    "scope",
    [
        "session_id",
        "opaque_project_id",
        "role",
        "device_id",
        "signing_public_key",
        "recipient_public_key",
        "fingerprint",
    ],
)
def test_even_valid_owner_signature_cannot_change_stored_pairing_scope(tmp_path, scope):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("reader", 1), now=100)
    changed = copy.deepcopy(challenge)
    if scope in ("session_id", "opaque_project_id"):
        changed[scope] = str(uuid4())
    elif scope == "role":
        changed["recipient"][scope] = "owner"
    elif scope == "device_id":
        changed["recipient"][scope] = str(uuid4())
    elif scope == "fingerprint":
        changed["recipient"][scope] = "a" * 64
    else:
        changed["recipient"][scope] = "a" * 64
    changed["sas"] = challenge_sas(changed)
    changed = k.signed_object("PairingChallenge", changed, owner.signing_seed)
    proof = p.answer_challenge(
        challenge, old, b, confirmation=p.confirmation(challenge), now=101
    )
    with pytest.raises(ValueError):
        p.consume(store, owner, changed, proof, bytes(32), now=102)


@given(st.sampled_from(["fingerprint", "opaque_project_id", "role", "sas"]))
def test_generated_confirmation_scope_mismatch_rejects(field):
    # Text confirmation is QA only but every security scope is binding.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        _, owner, b, _, old, store = setup_project(Path(tmp))
        p = api("pairing")
        challenge = p.create_challenge(store, owner, b.member("reader", 1), now=100)
        confirm = p.confirmation(challenge)
        confirm[field] = "wrong"
        with pytest.raises(ValueError):
            p.answer_challenge(challenge, old, b, confirmation=confirm, now=101)


def test_pairing_persistence_failure_after_manifest_write_rolls_back(
    tmp_path, monkeypatch
):
    _, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("writer", 1), now=100)
    proof = p.answer_challenge(
        challenge, old, b, confirmation=p.confirmation(challenge), now=101
    )
    accept = store.accept

    def failed_write(candidate, *, db=None):
        accept(candidate, db=db)
        raise ValueError("SYNTHETIC_PERSISTENCE_FAILURE")

    monkeypatch.setattr(store, "accept", failed_write)
    with pytest.raises(ValueError, match="SYNTHETIC_PERSISTENCE_FAILURE"):
        p.consume(store, owner, challenge, proof, bytes(32), now=102)
    assert store.current(old["opaque_project_id"]) == old


@pytest.mark.parametrize("fault", [None, "before_commit", "after_commit"])
def test_pending_pairing_activates_exact_identity_atomically(tmp_path, fault):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    pending = k.transition(old, owner, add=b.member("writer", 7, status="PENDING"))
    store.accept(pending)
    recipient = {**pending["members"][-1], "status": "ACTIVE"}
    challenge = p.create_challenge(store, owner, recipient, now=100)
    proof = p.answer_challenge(
        challenge, pending, b, confirmation=p.confirmation(challenge), now=101
    )
    key = k.TestOnlyKeyVault().create(old["opaque_project_id"], 1)
    if fault:
        with pytest.raises(RuntimeError, match="SYNTHETIC_CRASH"):
            p.consume(store, owner, challenge, proof, key, now=102, crash_point=fault)
        store = k.TrustedStore(store.path)
        if fault == "before_commit":
            assert store.current(old["opaque_project_id"]) == pending
            with store.transaction() as db:
                assert db.execute(
                    "SELECT attempts,used,receipt FROM challenges"
                ).fetchone() == (0, 0, None)
            receipt = p.consume(store, owner, challenge, proof, key, now=102)
        else:
            receipt = p.retry_receipt(store, challenge, b.device_id)
    else:
        receipt = p.consume(store, owner, challenge, proof, key, now=102)
    assert receipt["manifest"]["members"] == [pending["members"][0], recipient]
    assert receipt["manifest"]["membership_epoch"] == pending["membership_epoch"] + 1
    assert receipt["manifest"]["key_epoch"] == pending["key_epoch"]
    assert bool(k.open_grant(receipt["grant"], receipt["manifest"], b) == key)
    assert (
        p.retry_receipt(k.TrustedStore(store.path), challenge, b.device_id) == receipt
    )
    with pytest.raises(ValueError, match="PAIRING_USED"):
        p.consume(store, owner, challenge, proof, key, now=102)


@pytest.mark.parametrize(
    "change",
    [
        "ACTIVE",
        "REVOKED",
        "role",
        "nonce_prefix",
        "signing_public_key",
        "recipient_public_key",
        "granted_at",
    ],
)
def test_pending_pairing_rejects_existing_identity_changes(tmp_path, change):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    pending = k.transition(
        old,
        owner,
        add=b.member(
            "writer",
            7,
            status="PENDING" if change not in ("ACTIVE", "REVOKED") else "ACTIVE",
        ),
    )
    store.accept(pending)
    if change == "REVOKED":
        pending = k.transition(pending, owner, revoke=b.device_id)
        store.accept(pending)
    recipient = b.member("writer", 7)
    answerer = b
    if change in ("signing_public_key", "recipient_public_key"):
        other = k.Device.generate()
        # A valid proof for the proposed identity must still not replace pinned keys.
        answerer = k.Device(
            b.device_id,
            other.signing_seed if change == "signing_public_key" else b.signing_seed,
            other.recipient_seed
            if change == "recipient_public_key"
            else b.recipient_seed,
        )
        recipient = answerer.member("writer", 7)
    elif change == "role":
        recipient[change] = "reader"
    elif change == "nonce_prefix":
        recipient[change] = 8
    elif change == "granted_at":
        recipient[change] = 1
    challenge = p.create_challenge(store, owner, recipient, now=100)
    proof = p.answer_challenge(
        challenge, pending, answerer, confirmation=p.confirmation(challenge), now=101
    )
    with pytest.raises(ValueError):
        p.consume(store, owner, challenge, proof, bytes(32), now=102)
    assert store.current(old["opaque_project_id"]) == pending
    with store.transaction() as db:
        assert db.execute(
            "SELECT attempts,used,receipt FROM challenges"
        ).fetchone() == (1, 0, None)


@pytest.mark.parametrize("trigger", ["manifest", "receipt"])
def test_pending_pairing_sql_failure_rolls_back_all_state(tmp_path, trigger):
    k, owner, b, _, old, store = setup_project(tmp_path)
    p = api("pairing")
    pending = k.transition(old, owner, add=b.member("writer", 7, status="PENDING"))
    store.accept(pending)
    challenge = p.create_challenge(
        store, owner, {**pending["members"][-1], "status": "ACTIVE"}, now=100
    )
    proof = p.answer_challenge(
        challenge, pending, b, confirmation=p.confirmation(challenge), now=101
    )
    with store.transaction() as db:
        target = (
            "AFTER INSERT ON manifests"
            if trigger == "manifest"
            else "AFTER UPDATE OF receipt ON challenges"
        )
        db.execute(
            f"CREATE TRIGGER fail_pending {target} BEGIN SELECT RAISE(ABORT, 'SYNTHETIC_WRITE'); END"
        )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError, match="SYNTHETIC_WRITE"):
        p.consume(store, owner, challenge, proof, bytes(32), now=102)
    store = k.TrustedStore(store.path)
    assert store.current(old["opaque_project_id"]) == pending
    with store.transaction() as db:
        assert db.execute(
            "SELECT attempts,used,receipt FROM challenges"
        ).fetchone() == (0, 0, None)
        db.execute("DROP TRIGGER fail_pending")
    receipt = p.consume(store, owner, challenge, proof, bytes(32), now=102)
    assert p.retry_receipt(store, challenge, b.device_id) == receipt
