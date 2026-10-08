"""Synthetic public Kit anchors survive object recreation, never seed-only trust."""

import copy
import os
import sqlite3
from uuid import uuid4

import pytest

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from tests.secure_sync.test_lifecycle import api, setup_project


def anchored(tmp_path):
    k, owner, new_owner, kit, manifest, store = setup_project(tmp_path)
    c = api("checkpoint")
    cp0 = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    rows = [{"sequence": 1, "envelope_digest": "a" * 64}]
    cp1 = c.sign_checkpoint(manifest, owner, 1, c.extend_chain("0" * 64, 0, rows))
    kit.update_anchor(manifest, cp0, store=store)
    kit.update_anchor(manifest, cp1, store=store, rows=rows)
    return k, owner, new_owner, kit, manifest, store, cp0, cp1


def restore(k, kit, store, project=None, **changes):
    assert callable(getattr(k.RecoveryKit, "restore_from_trusted_store", None)), (
        "committed public Kit metadata restore API required"
    )
    args = {
        "signing_seed": kit.signing_seed,
        "recipient_seed": kit.recipient_seed,
        "device_id": kit.device_id,
        "project": project or kit.project,
        "store": store,
    }
    args.update(changes)
    return k.RecoveryKit.restore_from_trusted_store(**args)


def test_restart_kit_restores_latest_combination_then_unwraps_and_recovers(tmp_path):
    k, owner, new_owner, kit, manifest, store, cp0, cp1 = anchored(tmp_path)
    key = os.urandom(32)
    backup = k.make_recovery_backup(manifest, owner, kit, key)
    checkpoint_store = api("checkpoint").CheckpointStore(tmp_path / "checkpoint.sqlite")
    checkpoint_store.pin(manifest["opaque_project_id"])
    checkpoint_store.advance(cp0, manifest, [])
    checkpoint_store.advance(
        cp1, manifest, [{"sequence": 1, "envelope_digest": "a" * 64}]
    )
    assert (
        api("checkpoint")
        .CheckpointStore(tmp_path / "checkpoint.sqlite")
        .get(manifest["opaque_project_id"])
        == cp1
    )
    reopened = k.TrustedStore(store.path)
    loaded = restore(k, kit, reopened)
    assert loaded is not kit
    assert loaded.checkpoint_anchor == cp1
    assert k.open_recovery_backup(backup, reopened, loaded) == key
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        loaded.update_anchor(manifest, cp0, store=reopened)
    result = k.recover(reopened, loaded, new_owner)
    again = restore(k, loaded, k.TrustedStore(store.path))
    assert again.manifest_anchor == digest(result)
    assert again.checkpoint_anchor["cursor"] == 1
    assert again.checkpoint_anchor["key_epoch"] == 2


def test_recovery_checkpoint_failure_rolls_back_manifest(tmp_path, monkeypatch):
    k, _, new_owner, kit, manifest, store, _, _ = anchored(tmp_path)
    before = copy.deepcopy(kit.__dict__)

    def fail(*args):
        raise ValueError("SYNTHETIC_CHECKPOINT_FAILURE")

    monkeypatch.setattr(api("checkpoint"), "sign_checkpoint", fail)
    with pytest.raises(ValueError, match="SYNTHETIC_CHECKPOINT_FAILURE"):
        k.recover(store, kit, new_owner)
    assert digest(store.current(manifest["opaque_project_id"])) == digest(manifest)
    assert kit.__dict__ == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "partial",
        "signature",
        "old_checkpoint",
        "wrong_root",
        "wrong_recipient",
        "wrong_id",
        "foreign_project",
        "history_root",
        "missing_history",
        "revision_gap",
        "epoch_bool",
        "tail_loss",
        "complete_old_cp",
    ],
)
def test_restore_rejects_missing_corrupt_or_misbound_committed_metadata(
    tmp_path, mutation
):
    k, _, _, kit, _, store, cp0, _ = anchored(tmp_path)
    assert callable(getattr(k.RecoveryKit, "restore_from_trusted_store", None)), (
        "committed restore required"
    )
    kwargs = {}
    with sqlite3.connect(store.path) as db:
        if mutation == "missing":
            db.execute("DELETE FROM kit_anchors")
        elif mutation == "missing_history":
            db.execute("DELETE FROM manifests")
        elif mutation == "revision_gap":
            db.execute("DELETE FROM kit_anchors WHERE revision=1")
        elif mutation == "tail_loss":
            db.execute("DELETE FROM kit_anchors WHERE revision=2")
        elif mutation == "wrong_root":
            kwargs["signing_seed"] = os.urandom(32)
        elif mutation == "wrong_recipient":
            kwargs["recipient_seed"] = os.urandom(32)
        elif mutation == "wrong_id":
            kwargs["device_id"] = str(uuid4())
        elif mutation == "foreign_project":
            kwargs["project"] = str(uuid4())
        elif mutation == "history_root":
            db.execute(
                "UPDATE roots SET owner=?", (k.Device.generate().signing_public,)
            )
        else:
            row = db.execute(
                "SELECT revision,body FROM kit_anchors ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            body = strict_loads(row[1])
            if mutation == "partial":
                del body["checkpoint_digest"]
            elif mutation == "epoch_bool":
                body["key_epoch"] = True
            elif mutation == "signature":
                body["checkpoint"]["signature"] = "A" * 86
                body["checkpoint_digest"] = digest(body["checkpoint"])
            else:
                body["checkpoint"] = cp0
                body["checkpoint_digest"] = digest(cp0)
                if mutation == "complete_old_cp":
                    body["rows"] = []
            db.execute(
                "UPDATE kit_anchors SET body=? WHERE revision=?",
                (canonical_bytes(body), row[0]),
            )
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        restore(k, kit, k.TrustedStore(store.path), **kwargs)


@pytest.mark.parametrize("operation", ["update", "recover"])
@pytest.mark.parametrize("phase", ["journal_before", "head_before", "head_after"])
def test_anchor_insert_failure_rolls_back_public_records_and_memory(
    tmp_path, operation, phase
):
    k, owner, new_owner, kit, manifest, store, _, cp1 = anchored(tmp_path)
    assert callable(getattr(k.RecoveryKit, "restore_from_trusted_store", None)), (
        "committed restore required"
    )
    with sqlite3.connect(store.path) as db:
        before_rows = db.execute("SELECT * FROM kit_anchors").fetchall()
        before_head = db.execute("SELECT * FROM kit_anchor_heads").fetchall()
        timing, action, table = {
            "journal_before": ("BEFORE", "INSERT", "kit_anchors"),
            "head_before": ("BEFORE", "INSERT", "kit_anchor_heads"),
            "head_after": ("AFTER", "UPDATE", "kit_anchor_heads"),
        }[phase]
        db.execute(
            f"CREATE TRIGGER fail_anchor {timing} {action} ON {table} BEGIN SELECT RAISE(ABORT,'SYNTHETIC_ANCHOR_WRITE_FAILURE'); END"
        )
    before = copy.deepcopy(kit.__dict__)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        if operation == "recover":
            chain = [
                k.transition(
                    manifest, owner, add=k.Device.generate().member("reader", 1)
                )
            ]
            k.recover(store, kit, new_owner, chain=chain)
        else:
            rows = [{"sequence": 2, "envelope_digest": "b" * 64}]
            c = api("checkpoint")
            cp2 = c.sign_checkpoint(
                manifest, owner, 2, c.extend_chain(cp1["chain_digest"], 1, rows)
            )
            kit.update_anchor(manifest, cp2, store=store, rows=rows)
    assert kit.__dict__ == before
    assert store.current(manifest["opaque_project_id"]) == manifest
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM kit_anchors").fetchall() == before_rows
        assert db.execute("SELECT * FROM kit_anchor_heads").fetchall() == before_head
    loaded = restore(k, kit, k.TrustedStore(store.path))
    assert loaded.checkpoint_anchor == cp1
    assert loaded.manifest_anchor == digest(manifest)


def test_committed_kit_metadata_is_public_only(tmp_path):
    _, _, _, kit, _, store, _, _ = anchored(tmp_path)
    with sqlite3.connect(store.path) as db:
        bodies = db.execute("SELECT body FROM kit_anchors").fetchall()
    for (body,) in bodies:
        assert kit.signing_seed not in body and kit.recipient_seed not in body
        assert kit.signing_seed.hex().encode() not in body
        assert kit.recipient_seed.hex().encode() not in body
        assert set(strict_loads(body)) == {
            "version",
            "revision",
            "previous_digest",
            "device_id",
            "signing_public_key",
            "recipient_public_key",
            "project",
            "manifest_digest",
            "membership_epoch",
            "key_epoch",
            "checkpoint_digest",
            "checkpoint",
            "rows",
        }


def test_initial_anchor_cannot_persist_unvalidated_rows(tmp_path):
    _, owner, _, kit, manifest, store = setup_project(tmp_path)
    cp0 = api("checkpoint").sign_checkpoint(manifest, owner, 0, "0" * 64)
    with pytest.raises(ValueError, match="RECOVERY_FRESHNESS_UNVERIFIABLE"):
        kit.update_anchor(
            manifest, cp0, store=store, rows=[{"SYNTHETIC_UNVALIDATED": "qa"}]
        )
    assert kit.manifest_anchor is None
