"""Synthetic local SQL metadata must never override signed membership history."""

import os
import sqlite3
from uuid import uuid4

import pytest
from researchhub.sync.secure.envelope import seal_record
from researchhub.sync.secure.nonce import NonceVault

from packages.secure_wire.canonical import canonical_bytes, digest
from tests.secure_sync.test_lifecycle import api, setup_project


def revoked_project(tmp_path):
    k, owner, b, kit, m1, store = setup_project(tmp_path)
    m2 = k.transition(m1, owner, add=b.member("writer", 1))
    store.accept(m2)
    key = os.urandom(32)
    vault = NonceVault(tmp_path / "nonce.sqlite")
    vault.register_new(key, 1)
    env = seal_record(
        {"SYNTHETIC": "writer"},
        key,
        b.signing_seed,
        vault,
        1,
        opaque_project_id=m1["opaque_project_id"],
        sender_device_id=b.device_id,
        membership_epoch=2,
        key_epoch=1,
        message_id=str(uuid4()),
    )
    m3 = k.transition(m2, owner, revoke=b.device_id)
    store.accept(m3)
    c = api("checkpoint")
    kit.update_anchor(m3, c.sign_checkpoint(m3, owner, 0, "0" * 64), store=store)
    assert k.classify_envelope(store, env)["status"] == "QUARANTINED"
    return k, owner, kit, m1, m2, m3, store, env


@pytest.mark.parametrize(
    "mutation", ["epoch", "digest", "project", "duplicate_bootstrap", "signature"]
)
def test_corrupt_history_rejects_all_authoritative_reads(tmp_path, mutation):
    k, _, kit, m1, _, m3, store, env = revoked_project(tmp_path)
    with sqlite3.connect(store.path) as db:
        if mutation == "duplicate_bootstrap":
            db.execute(
                "INSERT INTO manifests VALUES (?,?,?,?)",
                (m1["opaque_project_id"], "e" * 64, 4, canonical_bytes(m1)),
            )
        elif mutation == "signature":
            bad = {**m3, "signature": "A" * 86}
            db.execute(
                "UPDATE manifests SET digest=?,body=? WHERE epoch=3",
                (digest(bad), canonical_bytes(bad)),
            )
        else:
            value = {"epoch": 0, "digest": "f" * 64, "project": str(uuid4())}[mutation]
            db.execute(f"UPDATE manifests SET {mutation}=? WHERE epoch=3", (value,))
    restarted = k.TrustedStore(store.path)
    for read in [
        lambda: restarted.current(m1["opaque_project_id"]),
        lambda: restarted.history(m1["opaque_project_id"], 1),
        lambda: restarted.verified_current(m1["opaque_project_id"]),
        lambda: k.classify_envelope(restarted, env),
        lambda: restarted.accept(m3),
        lambda: k.RecoveryKit.restore_from_trusted_store(
            kit.signing_seed,
            kit.recipient_seed,
            device_id=kit.device_id,
            project=m1["opaque_project_id"],
            store=restarted,
        ),
    ]:
        with pytest.raises(ValueError):
            read()


def test_verified_membership_exact_retry_is_idempotent(tmp_path):
    _, _, _, m1, _, m3, store, _ = revoked_project(tmp_path)
    assert store.accept(m3) == m3
    assert store.current(m1["opaque_project_id"]) == m3
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM manifests").fetchone()[0] == 3


def test_future_sql_epoch_cannot_duplicate_bootstrap_as_retry(tmp_path):
    _, _, _, _, m1, store = setup_project(tmp_path)
    with sqlite3.connect(store.path) as db:
        db.execute(
            "INSERT INTO manifests VALUES (?,?,?,?)",
            (m1["opaque_project_id"], "e" * 64, 2, canonical_bytes(m1)),
        )
    with pytest.raises(ValueError):
        store.verified_current(m1["opaque_project_id"])


@pytest.mark.parametrize("operation", ["challenge", "consume", "receipt"])
def test_bad_signed_history_has_no_pairing_write_effects(tmp_path, operation):
    k, owner, b, _, initial, store = setup_project(tmp_path)
    p = api("pairing")
    challenge = p.create_challenge(store, owner, b.member("writer", 1), now=100)
    proof = p.answer_challenge(
        challenge, initial, b, confirmation=p.confirmation(challenge), now=101
    )
    key = os.urandom(32)
    if operation == "receipt":
        p.consume(store, owner, challenge, proof, key, now=102)
    current = store.current(initial["opaque_project_id"])
    bad = {**current, "signature": "A" * 86}
    with sqlite3.connect(store.path) as db:
        db.execute(
            "UPDATE manifests SET digest=?,body=? WHERE epoch=?",
            (digest(bad), canonical_bytes(bad), current["membership_epoch"]),
        )
        before = db.execute("SELECT * FROM challenges").fetchall()
    with pytest.raises(ValueError):
        if operation == "challenge":
            p.create_challenge(
                store, owner, k.Device.generate().member("reader", 2), now=103
            )
        elif operation == "consume":
            p.consume(store, owner, challenge, proof, key, now=103)
        else:
            p.retry_receipt(store, challenge, b.device_id)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM challenges").fetchall() == before
