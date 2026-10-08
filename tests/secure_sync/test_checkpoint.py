import copy
import os
import sqlite3
from uuid import uuid4

import pytest
from researchhub.sync.secure.nonce import NonceVault

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.checkpoint import verify_advance
from packages.secure_wire.envelope import b64decode, b64encode
from tests.secure_sync.test_lifecycle import api, setup_project


def test_checkpoint_continuity_persists_and_rejects_rollback_fork_gap(tmp_path):
    _, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    anchor = c.CheckpointStore(tmp_path / "checkpoint.sqlite")
    anchor.pin(manifest["opaque_project_id"])
    rows = [
        {"sequence": 1, "envelope_digest": "a" * 64},
        {"sequence": 2, "envelope_digest": "b" * 64},
    ]
    chain = c.extend_chain("0" * 64, 0, rows)
    checkpoint = c.sign_checkpoint(manifest, owner, 2, chain)
    anchor.advance(checkpoint, manifest, rows)
    restarted = c.CheckpointStore(anchor.path)
    assert restarted.get(manifest["opaque_project_id"])["cursor"] == 2
    restarted.advance(checkpoint, manifest, [])
    with pytest.raises(ValueError, match="ROLLBACK_DETECTED"):
        restarted.advance(c.sign_checkpoint(manifest, owner, 1, "a" * 64), manifest, [])
    with pytest.raises(ValueError, match="ROLLBACK_DETECTED"):
        restarted.advance(c.sign_checkpoint(manifest, owner, 2, "b" * 64), manifest, [])
    with pytest.raises(ValueError, match="CURSOR_GAP"):
        restarted.advance(
            c.sign_checkpoint(manifest, owner, 4, "c" * 64),
            manifest,
            [{"sequence": 4, "envelope_digest": "d" * 64}],
        )
    forged = copy.deepcopy(checkpoint)
    forged["signature"] = "A" * 86
    with pytest.raises(ValueError):
        restarted.advance(forged, manifest, [])


def test_snapshot_inner_signature_and_encrypted_outer_binding(tmp_path):
    _, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    key = os.urandom(32)
    vault = NonceVault(tmp_path / "nonce.sqlite")
    vault.register_new(key, 0)
    checkpoint = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    state = {"SYNTHETIC_PRIVATE_NOTE": "opaque state"}
    env = c.seal_snapshot(
        state, "a" * 64, checkpoint, manifest, owner, key, vault, str(uuid4())
    )
    assert "SYNTHETIC_PRIVATE_NOTE" not in str(env)
    assert (
        c.open_snapshot(env, manifest, key, checkpoint, module_snapshot_hash="a" * 64)
        == state
    )
    with pytest.raises(ValueError):
        c.open_snapshot(env, manifest, key, checkpoint, module_snapshot_hash="b" * 64)
    value = c.snapshot_record(state, "a" * 64, checkpoint, manifest, owner)
    value["manifest"]["state_digest"] = digest({"bad": "state"})
    with pytest.raises(ValueError):
        c.verify_snapshot_record(
            value, manifest, checkpoint, module_snapshot_hash="a" * 64
        )


@pytest.mark.parametrize("field", ["key_epoch", "membership_epoch"])
def test_validly_signed_checkpoint_rejects_boolean_epoch(tmp_path, field):
    k, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    value = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    value[field] = True
    value = k.signed_object("Checkpoint", value, owner.signing_seed)
    with pytest.raises(ValueError):
        c.verify_checkpoint(value, manifest)


def test_all_genesis_chain_entry_points_require_zero_digest(tmp_path):
    k, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    with pytest.raises(ValueError):
        c.extend_chain("a" * 64, 0, [])
    bad = k.signed_object(
        "Checkpoint",
        {
            "version": 1,
            "opaque_project_id": manifest["opaque_project_id"],
            "membership_epoch": 1,
            "key_epoch": 1,
            "cursor": 0,
            "chain_digest": "a" * 64,
            "creator_device_id": owner.device_id,
        },
        owner.signing_seed,
    )
    with pytest.raises(ValueError):
        c.verify_checkpoint(bad, manifest)
    anchor = c.CheckpointStore(tmp_path / "checkpoint.sqlite")
    with pytest.raises(ValueError):
        anchor.pin(manifest["opaque_project_id"], chain_digest="a" * 64)


@pytest.mark.parametrize("growing", [False, True])
def test_checkpoint_signed_anchor_epochs_cannot_regress(tmp_path, growing):
    k, owner, b, _, m1, _ = setup_project(tmp_path)
    c = api("checkpoint")
    m2 = k.transition(m1, owner, add=b.member("writer", 1))
    m3 = k.transition(m2, owner, revoke=b.device_id)
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    chain = c.extend_chain("0" * 64, 0, rows)
    latest = c.sign_checkpoint(m3, owner, 1, chain)
    store = c.CheckpointStore(tmp_path / "cp.sqlite")
    store.pin(m1["opaque_project_id"])
    store.advance(latest, m3, rows)
    extra = [{"sequence": 2, "envelope_digest": "b" * 64}] if growing else []
    old = c.sign_checkpoint(m2, owner, 1 + len(extra), c.extend_chain(chain, 1, extra))
    with pytest.raises(ValueError):
        verify_advance(latest, old, m2, extra)
    with pytest.raises(ValueError):
        c.CheckpointStore(store.path).advance(old, m2, extra)
    assert store.get(m1["opaque_project_id"]) == latest
    store.advance(latest, m3, [])


@pytest.mark.parametrize(
    "mutation", ["drop_epoch", "drop_signature", "three_fields", "bool_epoch"]
)
def test_signed_checkpoint_cannot_degrade_to_bootstrap(tmp_path, mutation):
    _, owner, _, _, m1, _ = setup_project(tmp_path)
    c = api("checkpoint")
    cp = c.sign_checkpoint(m1, owner, 0, "0" * 64)
    store = c.CheckpointStore(tmp_path / "cp.sqlite")
    store.pin(m1["opaque_project_id"])
    store.advance(cp, m1, [])
    bad = copy.deepcopy(cp)
    if mutation == "drop_epoch":
        del bad["key_epoch"]
    elif mutation == "drop_signature":
        del bad["signature"]
    elif mutation == "bool_epoch":
        bad["membership_epoch"] = True
    else:
        bad = {f: bad[f] for f in ["opaque_project_id", "cursor", "chain_digest"]}
    with pytest.raises(ValueError):
        verify_advance(bad, cp, m1, [])
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE anchors SET body=?", (canonical_bytes(bad),))
    reopened = c.CheckpointStore(store.path)
    with pytest.raises(ValueError):
        reopened.advance(cp, m1, [])


@pytest.mark.parametrize("epoch", ["membership_epoch", "key_epoch"])
def test_public_advance_checks_each_anchor_epoch_independently(tmp_path, epoch):
    k, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    cp = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    # Public helper receives a previously authenticated anchor. Independently
    # exercise each lower bound rather than rely on both decreasing together.
    anchor = k.signed_object("Checkpoint", {**cp, epoch: 2}, owner.signing_seed)
    with pytest.raises(ValueError, match="ROLLBACK_DETECTED"):
        verify_advance(anchor, cp, manifest, [])


def test_public_advance_requires_explicit_bootstrap_boundary(tmp_path):
    _, owner, _, _, manifest, _ = setup_project(tmp_path)
    cp = api("checkpoint").sign_checkpoint(manifest, owner, 0, "0" * 64)
    initial = {f: cp[f] for f in ["opaque_project_id", "cursor", "chain_digest"]}
    with pytest.raises(ValueError):
        verify_advance(initial, cp, manifest, [])
    assert verify_advance(initial, cp, manifest, [], bootstrap=True) == cp


def test_legacy_checkpoint_store_without_kind_fails_closed(tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL)")
    with pytest.raises(ValueError, match="CHECKPOINT_STORE_KIND_REQUIRED"):
        api("checkpoint").CheckpointStore(path)


@pytest.mark.parametrize("mutation", ["signature_bit", "cursor_zero"])
@pytest.mark.parametrize("operation", ["get", "advance", "kit"])
def test_persisted_signed_checkpoint_requires_real_signature_on_read_and_advance(
    tmp_path, mutation, operation
):
    _, owner, _, kit, manifest, trusted = setup_project(tmp_path)
    c = api("checkpoint")
    store = c.CheckpointStore(tmp_path / "signed.sqlite")
    store.pin(manifest["opaque_project_id"])
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(manifest, owner, 1, c.extend_chain("0" * 64, 0, rows))
    store.advance(cp1, manifest, rows)
    bad = copy.deepcopy(cp1)
    if mutation == "signature_bit":
        signature = bytearray(b64decode(bad["signature"], 64))
        signature[0] ^= 1
        bad["signature"] = b64encode(signature)
        extra = [{"sequence": 2, "envelope_digest": "b" * 64}]
        next_cp = c.sign_checkpoint(
            manifest, owner, 2, c.extend_chain(cp1["chain_digest"], 1, extra)
        )
    else:
        bad.update(cursor=0, chain_digest="0" * 64)
        extra = []
        next_cp = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    with pytest.raises(ValueError):
        c.verify_checkpoint(bad, manifest)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE anchors SET body=?", (canonical_bytes(bad),))
        before = db.execute("SELECT * FROM anchors").fetchall()
    reopened = c.CheckpointStore(store.path)
    with pytest.raises(ValueError):
        if operation == "get":
            reopened.get(manifest["opaque_project_id"])
        elif operation == "advance":
            reopened.advance(next_cp, manifest, extra)
        else:
            kit.update_anchor(manifest, cp1, store=trusted, checkpoint_store=reopened)
    assert kit.manifest_anchor is None
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM anchors").fetchall() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "partial",
        "extra",
        "wrong_pub",
        "wrong_epoch",
        "wrong_digest",
        "digest_recomputed",
    ],
)
def test_signed_checkpoint_verification_context_fails_closed(tmp_path, mutation):
    k, owner, _, _, manifest, _ = setup_project(tmp_path)
    c = api("checkpoint")
    cp = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    store = c.CheckpointStore(tmp_path / "context.sqlite")
    store.pin(manifest["opaque_project_id"])
    store.advance(cp, manifest, [])
    with sqlite3.connect(store.path) as db:
        context = strict_loads(
            db.execute("SELECT verification FROM anchors").fetchone()[0]
        )
        if mutation == "missing":
            raw = None
        else:
            if mutation == "partial":
                del context["signing_public_key"]
            elif mutation == "extra":
                context["extra"] = "SYNTHETIC"
            elif mutation == "wrong_pub":
                context["signing_public_key"] = k.Device.generate().signing_public
            elif mutation == "wrong_epoch":
                context["membership_epoch"] += 1
            elif mutation == "wrong_digest":
                context["checkpoint_digest"] = "e" * 64
            else:
                bad = {**cp, "signature": "A" * 86}
                context["checkpoint_digest"] = digest(bad)
                db.execute("UPDATE anchors SET body=?", (canonical_bytes(bad),))
            raw = canonical_bytes(context)
        db.execute("UPDATE anchors SET verification=?", (raw,))
        before = db.execute("SELECT * FROM anchors").fetchall()
    reopened = c.CheckpointStore(store.path)
    with pytest.raises(ValueError):
        reopened.get(manifest["opaque_project_id"])
    with pytest.raises(ValueError):
        reopened.advance(cp, manifest, [])
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM anchors").fetchall() == before


def test_historical_checkpoint_creator_revocation_does_not_break_trusted_signature(
    tmp_path,
):
    k, owner, b, kit, m1, trusted = setup_project(tmp_path)
    c = api("checkpoint")
    m2 = k.transition(m1, owner, add=b.member("writer", 1))
    trusted.accept(m2)
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(m2, b, 1, c.extend_chain("0" * 64, 0, rows))
    store = c.CheckpointStore(tmp_path / "historical.sqlite")
    store.pin(m1["opaque_project_id"])
    store.advance(cp1, m2, rows)
    m3 = k.transition(m2, owner, revoke=b.device_id)
    trusted.accept(m3)
    reopened = c.CheckpointStore(store.path)
    assert reopened.get(m1["opaque_project_id"]) == cp1
    extra = [{"sequence": 2, "envelope_digest": "b" * 64}]
    cp2 = c.sign_checkpoint(m3, owner, 2, c.extend_chain(cp1["chain_digest"], 1, extra))
    reopened.advance(cp2, m3, extra)
    assert reopened.get(m1["opaque_project_id"]) == cp2
    kit.update_anchor(m3, cp2, store=trusted, checkpoint_store=reopened)
    assert kit.checkpoint_anchor == cp2


def test_legacy_checkpoint_without_verification_context_fails_closed(tmp_path):
    path = tmp_path / "legacy-kind.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL)"
        )
    with pytest.raises(ValueError, match="CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED"):
        api("checkpoint").CheckpointStore(path)
