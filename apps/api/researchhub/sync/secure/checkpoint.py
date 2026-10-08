"""TEST ONLY monotone SQLite anchors and encrypted signed snapshot prototype."""

import sqlite3
from contextlib import closing
from pathlib import Path

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.checkpoint import (
    extend_chain,
    validate_anchor,
    verify_advance,
    verify_checkpoint,
)
from packages.secure_wire.envelope import hex_bytes, safe_int, uuid
from packages.secure_wire.membership import (
    fields,
    member_of,
    verify_active_envelope,
    verify_signed,
)

from .envelope import open_record, seal_record
from .keys import signed_object

__all__ = [
    "CheckpointStore",
    "extend_chain",
    "open_snapshot",
    "seal_snapshot",
    "sign_checkpoint",
    "snapshot_record",
    "verify_checkpoint",
    "verify_snapshot_record",
]


def sign_checkpoint(manifest, creator, cursor, chain_digest):
    result = signed_object(
        "Checkpoint",
        {
            "version": 1,
            "opaque_project_id": manifest["opaque_project_id"],
            "membership_epoch": manifest["membership_epoch"],
            "key_epoch": manifest["key_epoch"],
            "cursor": cursor,
            "chain_digest": chain_digest,
            "creator_device_id": creator.device_id,
        },
        creator.signing_seed,
    )
    return verify_checkpoint(result, manifest)


class CheckpointStore:
    """Replaceable client anchor storage. Task 3 PG atomic cursor adapter is separate."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('BOOTSTRAP','SIGNED')),verification BLOB)"
            )
            if "kind" not in {
                row[1] for row in db.execute("PRAGMA table_info(anchors)")
            }:
                raise ValueError("CHECKPOINT_STORE_KIND_REQUIRED")
            if "verification" not in {
                row[1] for row in db.execute("PRAGMA table_info(anchors)")
            }:
                raise ValueError("CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        return db

    def pin(self, project, *, cursor=0, chain_digest="0" * 64):
        from packages.secure_wire.envelope import uuid

        uuid(project)
        safe_int(cursor)
        hex_bytes(chain_digest, 32)
        if cursor == 0 and chain_digest != "0" * 64:
            raise ValueError("INVALID_GENESIS_CHAIN")
        value = {
            "opaque_project_id": project,
            "cursor": cursor,
            "chain_digest": chain_digest,
        }
        with closing(self._connect()) as db:
            try:
                db.execute(
                    "INSERT INTO anchors VALUES (?,?,'BOOTSTRAP',NULL)",
                    (project, canonical_bytes(value)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                raise ValueError("CHECKPOINT_ALREADY_PINNED") from None

    def get(self, project, *, db=None):
        if db is None:
            with closing(self._connect()) as connection:
                return self.get(project, db=connection)
        return self._anchor(project, db)[0]

    def _anchor(self, project, db):
        row = db.execute(
            "SELECT body,kind,verification FROM anchors WHERE project=?", (project,)
        ).fetchone()
        if row is None:
            raise ValueError("CHECKPOINT_ANCHOR_REQUIRED")
        if row[1] not in ("BOOTSTRAP", "SIGNED"):
            raise ValueError("INVALID_CHECKPOINT_KIND")
        anchor = strict_loads(row[0])
        validate_anchor(anchor, bootstrap=row[1] == "BOOTSTRAP")
        if anchor["opaque_project_id"] != project:
            raise ValueError("CHECKPOINT_BINDING_MISMATCH")
        if row[1] == "BOOTSTRAP":
            if row[2] is not None:
                raise ValueError("INVALID_CHECKPOINT_VERIFICATION_CONTEXT")
        else:
            if row[2] is None:
                raise ValueError("CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED")
            context = strict_loads(row[2])
            fields(
                context,
                frozenset(
                    (
                        "version",
                        "opaque_project_id",
                        "membership_epoch",
                        "key_epoch",
                        "creator_device_id",
                        "signing_public_key",
                        "checkpoint_digest",
                    )
                ),
            )
            safe_int(context["version"], 1, 1)
            safe_int(context["membership_epoch"], 1)
            safe_int(context["key_epoch"], 1)
            uuid(context["opaque_project_id"])
            uuid(context["creator_device_id"])
            for name in ("signing_public_key", "checkpoint_digest"):
                hex_bytes(context[name], 32)
            if any(
                context[name] != anchor[name]
                for name in (
                    "opaque_project_id",
                    "membership_epoch",
                    "key_epoch",
                    "creator_device_id",
                )
            ):
                raise ValueError("CHECKPOINT_BINDING_MISMATCH")
            # Retain the creator key authenticated at commit, even after revocation.
            verify_signed("Checkpoint", anchor, context["signing_public_key"])
            if context["checkpoint_digest"] != digest(anchor):
                raise ValueError("CHECKPOINT_BINDING_MISMATCH")
        return anchor, row[1]

    def advance(self, checkpoint, manifest, rows):
        with closing(self._connect()) as db:
            previous, kind = self._anchor(checkpoint["opaque_project_id"], db)
            verify_advance(
                previous, checkpoint, manifest, rows, bootstrap=kind == "BOOTSTRAP"
            )
            context = {
                "version": 1,
                "opaque_project_id": checkpoint["opaque_project_id"],
                "membership_epoch": checkpoint["membership_epoch"],
                "key_epoch": checkpoint["key_epoch"],
                "creator_device_id": checkpoint["creator_device_id"],
                "signing_public_key": member_of(
                    manifest, checkpoint["creator_device_id"]
                )["signing_public_key"],
                "checkpoint_digest": digest(checkpoint),
            }
            db.execute(
                "UPDATE anchors SET body=?,kind='SIGNED',verification=? WHERE project=?",
                (
                    canonical_bytes(checkpoint),
                    canonical_bytes(context),
                    checkpoint["opaque_project_id"],
                ),
            )
            db.commit()
        return checkpoint


def snapshot_record(state, module_snapshot_hash, checkpoint, manifest, creator):
    verify_checkpoint(checkpoint, manifest)
    hex_bytes(module_snapshot_hash, 32)
    inner = {
        "version": 1,
        "opaque_project_id": manifest["opaque_project_id"],
        "snapshot_cursor": checkpoint["cursor"],
        "checkpoint_digest": digest(checkpoint),
        "module_snapshot_hash": module_snapshot_hash,
        "state_digest": digest(state),
        "key_epoch": manifest["key_epoch"],
        "creator_device_id": creator.device_id,
    }
    return {
        "manifest": signed_object("SnapshotManifest", inner, creator.signing_seed),
        "state": state,
    }


def verify_snapshot_record(record, manifest, checkpoint, *, module_snapshot_hash):
    fields(record, frozenset(("manifest", "state")))
    inner = record["manifest"]
    fields(
        inner,
        frozenset(
            [
                "version",
                "opaque_project_id",
                "snapshot_cursor",
                "checkpoint_digest",
                "module_snapshot_hash",
                "state_digest",
                "key_epoch",
                "creator_device_id",
                "signature",
            ]
        ),
    )
    safe_int(inner["version"], 1, 1)
    safe_int(inner["snapshot_cursor"])
    safe_int(inner["key_epoch"], 1)
    verify_checkpoint(checkpoint, manifest)
    if (
        inner["opaque_project_id"] != manifest["opaque_project_id"]
        or inner["snapshot_cursor"] != checkpoint["cursor"]
        or inner["checkpoint_digest"] != digest(checkpoint)
        or inner["key_epoch"] != manifest["key_epoch"]
        or inner["module_snapshot_hash"] != module_snapshot_hash
        or inner["state_digest"] != digest(record["state"])
    ):
        raise ValueError("SNAPSHOT_BINDING_MISMATCH")
    hex_bytes(module_snapshot_hash, 32)
    creator = member_of(manifest, inner["creator_device_id"])
    verify_signed("SnapshotManifest", inner, creator["signing_public_key"])
    return record["state"]


def seal_snapshot(
    state, module_snapshot_hash, checkpoint, manifest, creator, key, vault, message_id
):
    member = member_of(manifest, creator.device_id, roles=("owner", "writer"))
    return seal_record(
        snapshot_record(state, module_snapshot_hash, checkpoint, manifest, creator),
        key,
        creator.signing_seed,
        vault,
        member["nonce_prefix"],
        opaque_project_id=manifest["opaque_project_id"],
        sender_device_id=creator.device_id,
        membership_epoch=manifest["membership_epoch"],
        key_epoch=manifest["key_epoch"],
        message_id=message_id,
        checkpoint_sequence=checkpoint["cursor"],
        record_type="snapshot",
    )


def open_snapshot(envelope, manifest, key, checkpoint, *, module_snapshot_hash):
    verify_active_envelope(envelope, manifest)
    member = member_of(manifest, envelope["sender_device_id"])
    if envelope["checkpoint_sequence"] != checkpoint["cursor"]:
        raise ValueError("SNAPSHOT_BINDING_MISMATCH")
    record = open_record(
        envelope,
        key,
        bytes.fromhex(member["signing_public_key"]),
        opaque_project_id=manifest["opaque_project_id"],
        sender_device_id=member["device_id"],
        membership_epoch=manifest["membership_epoch"],
        key_epoch=manifest["key_epoch"],
        nonce_prefix=member["nonce_prefix"],
        record_type="snapshot",
    )
    if record["manifest"]["creator_device_id"] != member["device_id"]:
        raise ValueError("SNAPSHOT_BINDING_MISMATCH")
    return verify_snapshot_record(
        record, manifest, checkpoint, module_snapshot_hash=module_snapshot_hash
    )
