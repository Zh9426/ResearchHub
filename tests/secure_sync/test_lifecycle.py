"""Generated, synthetic TEST ONLY lifecycle keys; secrets never logged."""

import copy
import importlib
import importlib.util
import os
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from researchhub.sync.secure.crypto import aes_decrypt, aes_encrypt

from packages.secure_wire.canonical import digest


def api(name="keys"):
    name = "researchhub.sync.secure." + name
    assert importlib.util.find_spec(name), "trusted lifecycle API not implemented"
    return importlib.import_module(name)


def setup_project(tmp_path):
    k = api()
    owner, recipient = k.Device.generate(), k.Device.generate()
    kit = k.RecoveryKit.generate()
    manifest = k.bootstrap(str(uuid4()), owner, kit)
    store = k.TrustedStore(tmp_path / "trusted.sqlite")
    store.bootstrap(manifest, owner.signing_public, kit.signing_public)
    return k, owner, recipient, kit, manifest, store


def test_transition_requires_previous_owner_and_keeps_prefix_history(tmp_path):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    new = k.transition(old, owner, add=b.member("writer", 1))
    store.accept(new)
    assert k.TrustedStore(store.path).current(old["opaque_project_id"]) == new
    attack = copy.deepcopy(new)
    attack["members"][0]["signing_public_key"] = b.signing_public
    attack = k.signed_manifest(attack, b.signing_seed)
    with pytest.raises(ValueError):
        store.accept(attack)
    removed = k.transition(new, owner, revoke=b.device_id)
    assert removed["key_epoch"] == 2
    store.accept(removed)
    with pytest.raises(ValueError):
        store.accept(k.transition(removed, owner, add=b.member("writer", 2)))
    c = k.Device.generate()
    with pytest.raises(ValueError):
        store.accept(k.transition(removed, owner, add=c.member("writer", 1)))
    assert store.current(old["opaque_project_id"]) == removed
    assert kit.signing_public == old["recovery_signing_public_key"]


def test_epoch_rotation_grants_only_active_members(tmp_path):
    k, owner, b, _, old, store = setup_project(tmp_path)
    paired = k.transition(old, owner, add=b.member("writer", 1))
    store.accept(paired)
    vault = k.TestOnlyKeyVault()
    old_key = vault.create(old["opaque_project_id"], 1)
    grant = k.make_grant(paired, owner, b.device_id, str(uuid4()), old_key)
    assert k.open_grant(grant, paired, b) == old_key
    revoked = k.transition(paired, owner, revoke=b.device_id)
    store.accept(revoked)
    new_key = vault.create(old["opaque_project_id"], 2)
    assert new_key != old_key
    with pytest.raises(ValueError, match="REVOKED_DEVICE"):
        k.make_grant(revoked, owner, b.device_id, str(uuid4()), new_key)
    with pytest.raises(ValueError):
        k.open_grant(grant, revoked, b)
    nonce = os.urandom(12)  # primitive-only probe; transport uses durable vault
    ciphertext = aes_encrypt(new_key, nonce, b"SYNTHETIC", b"epoch2")
    with pytest.raises(ValueError, match="DECRYPT_FAILED"):
        aes_decrypt(old_key, nonce, ciphertext, b"epoch2")
    c = k.Device.generate()
    latest = k.transition(revoked, owner, add=c.member("reader", 2))
    store.accept(latest)
    assert (
        k.open_grant(
            k.make_grant(latest, owner, c.device_id, str(uuid4()), new_key), latest, c
        )
        == new_key
    )


def test_recovery_pinned_root_latest_anchor_and_total_key_loss(tmp_path):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        k.recover(store, kit, b)
    kit.update_anchor(
        old, api("checkpoint").sign_checkpoint(old, owner, 0, "0" * 64), store=store
    )
    recovered = k.recover(store, kit, b)
    assert recovered["membership_epoch"] == recovered["key_epoch"] == 2
    assert recovered["members"][0]["status"] == "REVOKED"
    assert recovered["members"][1]["role"] == "owner"
    store.accept(recovered)
    assert kit.manifest_anchor == digest(recovered)
    with pytest.raises(ValueError, match="E2E_DATA_UNRECOVERABLE"):
        k.recover(store, None, owner)


def test_pending_persistent_no_key_then_activation(tmp_path):
    k, owner, b, _, old, store = setup_project(tmp_path)
    pending = k.transition(old, owner, add=b.member("writer", 1, status="PENDING"))
    store.accept(pending)
    with pytest.raises(ValueError, match="UNAUTHORIZED_DEVICE"):
        k.make_grant(pending, owner, b.device_id, str(uuid4()), os.urandom(32))
    active = k.transition(
        k.TrustedStore(store.path).current(old["opaque_project_id"]),
        owner,
        activate=b.device_id,
    )
    store.accept(active)
    assert active["members"][1]["status"] == "ACTIVE"


def test_recovery_backup_unwrap_with_latest_anchor_then_rotation(tmp_path):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    key = os.urandom(32)
    assert hasattr(k, "make_recovery_backup"), "recovery key backup not implemented"
    backup = k.make_recovery_backup(old, owner, kit, key)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        k.open_recovery_backup(backup, store, kit)
    checkpoint = api("checkpoint").sign_checkpoint(old, owner, 0, "0" * 64)
    kit.update_anchor(old, checkpoint, store=store)
    assert k.open_recovery_backup(backup, store, kit) == key
    wrong = k.RecoveryKit.generate()
    with pytest.raises(ValueError):
        wrong.update_anchor(old, checkpoint, store=store)
        k.open_recovery_backup(backup, store, wrong)
    forged = copy.deepcopy(backup)
    forged["context"]["key_epoch"] += 1
    with pytest.raises(ValueError):
        k.open_recovery_backup(forged, store, kit)
    latest = k.recover(store, kit, b)
    new_key = os.urandom(32)
    grant = k.make_grant(latest, b, b.device_id, str(uuid4()), new_key)
    assert k.open_grant(grant, latest, b) == new_key and new_key != key


def test_test_only_device_store_persists_uuid_and_separates_private_material(tmp_path):
    k = api()
    assert hasattr(k, "TestOnlyFileDeviceKeyStore"), (
        "persistent QA device key store missing"
    )
    first = k.TestOnlyFileDeviceKeyStore(tmp_path / "device.sqlite").load_or_create()
    second = k.TestOnlyFileDeviceKeyStore(tmp_path / "device.sqlite").load_or_create()
    assert first.device_id == second.device_id
    assert first.signing_public == second.signing_public
    assert first.recipient_public == second.recipient_public
    assert first.signing_seed != first.recipient_seed
    assert first.signing_seed.hex() not in repr(first)
    with pytest.raises(ValueError, match="QA_VAULT_PATH_REQUIRED"):
        k.TestOnlyFileDeviceKeyStore("fixtures/secret.sqlite")


def test_revoke_helper_rotates_key_and_grants_active_only(tmp_path):
    k, owner, b, _, old, store = setup_project(tmp_path)
    paired = k.transition(old, owner, add=b.member("writer", 1))
    store.accept(paired)
    vault = k.TestOnlyKeyVault()
    old_key = vault.create(old["opaque_project_id"], 1)
    assert hasattr(k, "revoke_and_rotate"), "fresh-key revoke operation missing"
    rotation = k.revoke_and_rotate(store, vault, owner, b.device_id)
    assert rotation.manifest["key_epoch"] == 2 and rotation.key != old_key
    assert set(rotation.grants) == {owner.device_id}
    assert (
        k.open_grant(rotation.grants[owner.device_id], rotation.manifest, owner)
        == rotation.key
    )


@pytest.mark.parametrize(
    "attack",
    [
        "self_authority",
        "skip_epoch",
        "old_key_epoch",
        "drop_member",
        "replace_key",
        "reuse_prefix",
        "new_recovery_root",
        "fork",
    ],
)
def test_even_validly_signed_transition_cannot_rewrite_pinned_history(tmp_path, attack):
    k, owner, b, kit, old, store = setup_project(tmp_path)
    new = k.transition(old, owner, add=b.member("writer", 1))
    bad = copy.deepcopy(new)
    signer = owner
    if attack == "self_authority":
        bad["authority_device_id"] = b.device_id
        bad["members"][1]["role"] = "owner"
        signer = b
    elif attack == "skip_epoch":
        bad["membership_epoch"] += 1
    elif attack == "old_key_epoch":
        bad["key_epoch"] += 1
    elif attack == "drop_member":
        bad["members"].pop(0)
        bad["members"][0]["role"] = "owner"
    elif attack == "replace_key":
        bad["members"][0] = b.member("owner", 0)
    elif attack == "reuse_prefix":
        bad["members"][1]["nonce_prefix"] = 0
    elif attack == "new_recovery_root":
        bad["recovery_signing_public_key"] = b.signing_public
    else:
        bad["membership_epoch"] = 1
    bad = k.signed_manifest(bad, signer.signing_seed)
    with pytest.raises(ValueError):
        store.accept(bad)
    assert store.current(old["opaque_project_id"]) == old
    assert kit.signing_public == old["recovery_signing_public_key"]


@given(
    st.sampled_from(
        [
            "key_epoch",
            "membership_epoch",
            "opaque_project_id",
            "wrapped_key",
            "role",
            "manifest_digest",
            "recipient_public_key",
        ]
    )
)
def test_whole_grant_scope_tampering_rejects(field):
    k = api()
    owner, b, kit = k.Device.generate(), k.Device.generate(), k.RecoveryKit.generate()
    old = k.bootstrap(str(uuid4()), owner, kit)
    new = k.transition(old, owner, add=b.member("writer", 1))
    grant = k.make_grant(new, owner, b.device_id, str(uuid4()), os.urandom(32))
    if field == "recipient_public_key":
        grant["context"][field] = "00" * 32
    elif field in grant["context"]:
        grant["context"][field] = 99 if "epoch" in field else str(uuid4())
    else:
        grant[field] = "reader" if field == "role" else "A" * 64
    with pytest.raises(ValueError):
        k.open_grant(grant, new, b)


def test_current_roles_and_pinned_historical_envelopes_quarantine(tmp_path):
    from researchhub.sync.secure.envelope import seal_record
    from researchhub.sync.secure.nonce import NonceVault

    from packages.secure_wire.membership import verify_active_envelope

    k, owner, b, _, old, store = setup_project(tmp_path)
    assert hasattr(k, "classify_envelope"), (
        "pinned historical quarantine helper missing"
    )
    current = k.transition(old, owner, add=b.member("reader", 1))
    store.accept(current)
    key = os.urandom(32)
    nonce = NonceVault(tmp_path / "nonce.sqlite")
    nonce.register_new(key, 1)
    env = seal_record(
        {"synthetic": "reader mutation"},
        key,
        b.signing_seed,
        nonce,
        1,
        opaque_project_id=old["opaque_project_id"],
        sender_device_id=b.device_id,
        membership_epoch=2,
        key_epoch=1,
        message_id=str(uuid4()),
    )
    with pytest.raises(ValueError, match="UNAUTHORIZED_DEVICE"):
        verify_active_envelope(env, current)
    nonce.register_new(key, 0)
    owner_env = seal_record(
        {"synthetic": "historical"},
        key,
        owner.signing_seed,
        nonce,
        0,
        opaque_project_id=old["opaque_project_id"],
        sender_device_id=owner.device_id,
        membership_epoch=2,
        key_epoch=1,
        message_id=str(uuid4()),
    )
    revoked = k.transition(current, owner, revoke=b.device_id)
    store.accept(revoked)
    assert k.classify_envelope(store, owner_env)["status"] == "QUARANTINED"
    tampered = copy.deepcopy(owner_env)
    tampered["signature"] = "A" * 86
    with pytest.raises(ValueError):
        k.classify_envelope(store, tampered)


@settings(max_examples=20, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["reader", "writer", "owner"]), st.booleans()),
        min_size=1,
        max_size=4,
    )
)
def test_generated_epoch_schedules_preserve_identity_and_revoke_forever(schedule):
    k = api()
    owner, kit = k.Device.generate(), k.RecoveryKit.generate()
    manifest = k.bootstrap(str(uuid4()), owner, kit)
    initial_project = manifest["opaque_project_id"]
    vault = k.TestOnlyKeyVault()
    key = vault.create(initial_project, 1)
    revoked = set()
    for role, revoke in schedule:
        device = k.Device.generate()
        prefix = max(m["nonce_prefix"] for m in manifest["members"]) + 1
        old_epoch = manifest["membership_epoch"]
        manifest = k.transition(manifest, owner, add=device.member(role, prefix))
        assert manifest["membership_epoch"] == old_epoch + 1
        grant = k.make_grant(manifest, owner, device.device_id, str(uuid4()), key)
        assert digest(k.open_grant(grant, manifest, device).hex()) == digest(key.hex())
        if revoke:
            previous_key = key
            manifest = k.transition(manifest, owner, revoke=device.device_id)
            key = vault.create(initial_project, manifest["key_epoch"])
            assert digest(key.hex()) != digest(previous_key.hex())
            revoked.add(device.device_id)
            with pytest.raises(ValueError):
                k.make_grant(manifest, owner, device.device_id, str(uuid4()), key)
        assert all(
            m["status"] == "REVOKED"
            for m in manifest["members"]
            if m["device_id"] in revoked
        )
        assert len({m["nonce_prefix"] for m in manifest["members"]}) == len(
            manifest["members"]
        )
