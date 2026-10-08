"""Behavioral regressions from independent Task 2 specification review."""

import copy
import os
from uuid import uuid4

import pytest

from packages.secure_wire.canonical import digest
from tests.secure_sync.test_lifecycle import api, setup_project


@pytest.mark.parametrize("operation", ["backup", "recover"])
def test_recovery_missing_checkpoint_is_freshness_error(tmp_path, operation):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    backup = k.make_recovery_backup(old, owner, kit, os.urandom(32))
    # Malicious/incomplete serialized kit: a manifest-only anchor is not enough.
    kit.manifest_anchor = digest(old)
    kit.project = old["opaque_project_id"]
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        if operation == "backup":
            k.open_recovery_backup(backup, store, kit)
        else:
            k.recover(store, kit, b)


@pytest.mark.parametrize(
    "mutation", ["project", "epoch", "bool_cursor", "chain", "signature"]
)
def test_recovery_rejects_untrusted_checkpoint_combination(tmp_path, mutation):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    c = api("checkpoint")
    checkpoint = c.sign_checkpoint(old, owner, 0, "0" * 64)
    kit.update_anchor(old, checkpoint, store=store)
    bad = copy.deepcopy(checkpoint)
    if mutation == "project":
        bad["opaque_project_id"] = str(uuid4())
    elif mutation == "epoch":
        bad["key_epoch"] += 1
    elif mutation == "bool_cursor":
        bad["cursor"] = True
    elif mutation == "chain":
        bad["chain_digest"] = "bad"
    else:
        bad["signature"] = "A" * 86
    if mutation != "signature":
        bad = k.signed_object("Checkpoint", bad, owner.signing_seed)
    kit.checkpoint_anchor = bad
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        k.recover(store, kit, b)


def test_kit_update_requires_trusted_local_store_and_monotone_checkpoint(tmp_path):
    _, owner, _, kit, old, store = setup_project(tmp_path)
    c = api("checkpoint")
    cp0 = c.sign_checkpoint(old, owner, 0, "0" * 64)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(old, cp0)
    kit.update_anchor(old, cp0, store=store)
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(old, owner, 1, c.extend_chain("0" * 64, 0, rows))
    kit.update_anchor(old, cp1, store=store, rows=rows)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(old, cp0, store=store)
    forged = {**cp1, "signature": "A" * 86}
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(old, forged, store=store)
    assert digest(kit.checkpoint_anchor) == digest(cp1)


def test_kit_first_nonzero_anchor_requires_verified_local_checkpoint_store(tmp_path):
    _, owner, _, kit, old, store = setup_project(tmp_path)
    c = api("checkpoint")
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(old, owner, 1, c.extend_chain("0" * 64, 0, rows))
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(old, cp1, store=store)
    checkpoint_store = c.CheckpointStore(tmp_path / "checkpoint.sqlite")
    checkpoint_store.pin(old["opaque_project_id"])
    checkpoint_store.advance(cp1, old, rows)
    kit.update_anchor(old, cp1, store=store, checkpoint_store=checkpoint_store)
    assert kit.checkpoint_anchor["cursor"] == 1


def test_cleared_kit_anchors_cannot_reset_initialization_or_unwrap_old_backup(tmp_path):
    k, owner, _, kit, old, store = setup_project(tmp_path)
    c = api("checkpoint")
    backup = k.make_recovery_backup(old, owner, kit, os.urandom(32))
    cp0 = c.sign_checkpoint(old, owner, 0, "0" * 64)
    kit.update_anchor(old, cp0, store=store)
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(old, owner, 1, c.extend_chain("0" * 64, 0, rows))
    kit.update_anchor(old, cp1, store=store, rows=rows)
    kit.manifest_anchor = kit.checkpoint_anchor = None
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(old, cp0, store=store)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        k.open_recovery_backup(backup, store, kit)


def test_imported_old_seeds_only_cannot_bootstrap_from_relay_old_genesis(tmp_path):
    k, owner, _, kit, old, store = setup_project(tmp_path)
    cp0 = api("checkpoint").sign_checkpoint(old, owner, 0, "0" * 64)
    imported = k.RecoveryKit(
        kit.signing_seed, kit.recipient_seed, device_id=kit.device_id
    )
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        imported.update_anchor(old, cp0, store=store)
    checkpoint_store = api("checkpoint").CheckpointStore(tmp_path / "checkpoint.sqlite")
    checkpoint_store.pin(old["opaque_project_id"])
    checkpoint_store.advance(cp0, old, [])
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        imported.update_anchor(old, cp0, store=store, checkpoint_store=checkpoint_store)
    with pytest.raises(ValueError, match="PUBLIC_TEST_ONLY_VECTOR_REQUIRED"):
        k.RecoveryKit.from_public_test_vectors(
            kit.signing_seed, kit.recipient_seed, device_id=kit.device_id
        )


@pytest.mark.parametrize("with_own", [False, True])
def test_recovery_chain_foreign_project_rolls_back_every_project(tmp_path, with_own):
    k, owner, recipient, kit, a, store = setup_project(tmp_path)
    b_owner, b_kit = k.Device.generate(), k.RecoveryKit.generate()
    b = k.bootstrap(str(uuid4()), b_owner, b_kit)
    store.bootstrap(b, b_owner.signing_public, b_kit.signing_public)
    cp0 = api("checkpoint").sign_checkpoint(a, owner, 0, "0" * 64)
    kit.update_anchor(a, cp0, store=store)
    own = k.transition(a, owner, add=recipient.member("reader", 1))
    foreign = k.transition(b, b_owner, add=k.Device.generate().member("writer", 1))
    anchor_before = kit.manifest_anchor, digest(kit.checkpoint_anchor)
    chain = [own, foreign] if with_own else [foreign]
    with pytest.raises(ValueError):
        k.recover(store, kit, k.Device.generate(), chain=chain)
    assert digest(store.current(a["opaque_project_id"])) == digest(a)
    assert digest(store.current(b["opaque_project_id"])) == digest(b)
    assert (kit.manifest_anchor, digest(kit.checkpoint_anchor)) == anchor_before
