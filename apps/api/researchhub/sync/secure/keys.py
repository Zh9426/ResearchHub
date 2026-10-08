"""Trusted-client TEST ONLY key stores and pinned public lifecycle state.

No production keystore: secret stores are ephemeral in memory. SQLite stores
only signed public manifests/challenges/receipts, never plaintext Project Keys.
"""

import copy
import os
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.envelope import b64decode, b64encode
from packages.secure_wire.membership import (
    ZERO,
    fields,
    fingerprint,
    member_of,
    preimage,
    validate_manifest,
    verify_active_envelope,
    verify_bootstrap,
    verify_grant,
    verify_historical_envelope,
    verify_signed,
    verify_transition,
)

from .crypto import recipient_public, sign, signing_public, unwrap_key, wrap_key


@dataclass
class Device:
    device_id: str
    signing_seed: bytes = field(repr=False)
    recipient_seed: bytes = field(repr=False)

    @classmethod
    def generate(cls):
        return cls(str(uuid4()), os.urandom(32), os.urandom(32))

    @property
    def signing_public(self):
        return signing_public(self.signing_seed).hex()

    @property
    def recipient_public(self):
        return recipient_public(self.recipient_seed).hex()

    def member(self, role, prefix, *, status="ACTIVE", now=0):
        return {
            "device_id": self.device_id,
            "signing_public_key": self.signing_public,
            "recipient_public_key": self.recipient_public,
            "fingerprint": fingerprint(self.signing_public, self.recipient_public),
            "role": role,
            "status": status,
            "nonce_prefix": prefix,
            "granted_at": now,
            "revoked_at": None,
        }


class DeviceKeyStore(Protocol):
    def load_or_create(self) -> Device: ...


class TestOnlyMemoryDeviceKeyStore:
    """UUID/private material remain stable for this test-store lifetime only."""

    def __init__(self):
        self._device = Device.generate()

    def load_or_create(self):
        return self._device

    def __repr__(self):
        return "TestOnlyMemoryDeviceKeyStore(TEST ONLY; redacted)"


class TestOnlyFileDeviceKeyStore:
    """UNPROTECTED QA ONLY SQLite secrets. Use ignored runtime/temporary paths.

    Exercises stable UUID/private identity across restart. This is explicitly
    not Windows protected storage or a production browser vault.
    """

    def __init__(self, path):
        self.path = Path(path).resolve()
        runtime = Path(__file__).resolve().parents[5] / "storage" / "runtime"
        if not any(
            self.path.is_relative_to(root.resolve())
            for root in (runtime, Path(tempfile.gettempdir()))
        ):
            raise ValueError("QA_VAULT_PATH_REQUIRED")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_or_create(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS qa_device(singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL,signing BLOB NOT NULL,recipient BLOB NOT NULL)"
            )
            row = db.execute(
                "SELECT id,signing,recipient FROM qa_device WHERE singleton=1"
            ).fetchone()
            if row is not None:
                return Device(*row)
            device = Device.generate()
            db.execute(
                "INSERT INTO qa_device VALUES (1,?,?,?)",
                (device.device_id, device.signing_seed, device.recipient_seed),
            )
            return device

    def __repr__(self):
        return "TestOnlyFileDeviceKeyStore(UNPROTECTED TEST ONLY; redacted)"


class KeyVault(Protocol):
    def create(self, project: str, epoch: int) -> bytes: ...

    def get(self, project: str, epoch: int) -> bytes: ...


class TestOnlyKeyVault:
    def __init__(self):
        self._keys = {}

    def create(self, project, epoch):
        if (project, epoch) in self._keys:
            raise ValueError("KEY_EPOCH_ALREADY_EXISTS")
        self._keys[project, epoch] = os.urandom(32)
        return self._keys[project, epoch]

    def get(self, project, epoch):
        if (project, epoch) not in self._keys:
            raise ValueError("UNKNOWN_KEY_EPOCH")
        return self._keys[project, epoch]

    def __repr__(self):
        return "TestOnlyKeyVault(TEST ONLY; redacted)"


@dataclass
class RecoveryKit:
    signing_seed: bytes = field(repr=False)
    recipient_seed: bytes = field(repr=False)
    manifest_anchor: str | None = None
    project: str | None = None
    checkpoint_anchor: dict | None = None
    device_id: str = field(default_factory=lambda: str(uuid4()))
    _checkpoint_digest: str | None = field(default=None, repr=False, init=False)
    _bootstrap_allowed: bool = field(default=False, repr=False, init=False)

    @classmethod
    def generate(cls):
        kit = cls(os.urandom(32), os.urandom(32))
        kit._bootstrap_allowed = True
        return kit

    @classmethod
    def from_public_test_vectors(cls, signing_seed, recipient_seed, *, device_id):
        """§66 PUBLIC TEST ONLY vectors, never runtime imported secrets."""
        if signing_seed != bytes(range(128, 160)) or recipient_seed != bytes(
            range(160, 192)
        ):
            raise ValueError("PUBLIC_TEST_ONLY_VECTOR_REQUIRED")
        kit = cls(signing_seed, recipient_seed, device_id=device_id)
        kit._bootstrap_allowed = True
        return kit

    @property
    def signing_public(self):
        return signing_public(self.signing_seed).hex()

    @property
    def recipient_public(self):
        return recipient_public(self.recipient_seed).hex()

    @classmethod
    def restore_from_trusted_store(
        cls, signing_seed, recipient_seed, *, device_id, project, store
    ):
        """TEST ONLY: restore only previously committed public local metadata."""
        kit = cls(signing_seed, recipient_seed, device_id=device_id)
        try:
            with store.transaction() as db:
                record = store.kit_anchor(kit, project, db=db)
                if record is None:
                    raise ValueError("MISSING_TRUSTED_METADATA")
                kit._install_anchor(record)
                _verify_kit_anchor(kit, store, db=db)
            return kit
        except (ValueError, KeyError, TypeError, AttributeError, sqlite3.DatabaseError):
            raise ValueError("RECOVERY_FRESHNESS_UNVERIFIABLE") from None

    def _install_anchor(self, record):
        self.manifest_anchor = record["manifest_digest"]
        self.project = record["project"]
        self.checkpoint_anchor = copy.deepcopy(record["checkpoint"])
        self._checkpoint_digest = record["checkpoint_digest"]
        self._bootstrap_allowed = False

    def update_anchor(
        self,
        verified_manifest,
        checkpoint=None,
        *,
        store=None,
        rows=(),
        checkpoint_store=None,
    ):
        """Require pinned continuous local history + authenticated monotone checkpoint.

        First anchor is signed cursor-0 genesis, or an existing verified local
        CheckpointStore. A higher cursor requires all continuous chain rows.
        """
        try:
            if store is None or checkpoint is None:
                raise ValueError("MISSING_TRUSTED_ANCHOR")
            with store.transaction() as db:
                record = self._stage_anchor(
                    verified_manifest,
                    checkpoint,
                    store,
                    list(rows),
                    checkpoint_store,
                    db,
                )
            self._install_anchor(record)
        except (ValueError, KeyError, TypeError, AttributeError, sqlite3.DatabaseError):
            raise ValueError("RECOVERY_FRESHNESS_UNVERIFIABLE") from None

    def _stage_anchor(
        self, verified_manifest, checkpoint, store, rows, checkpoint_store, db
    ):
        """Stage public state only; caller must install memory after its commit."""
        from packages.secure_wire.checkpoint import verify_advance, verify_checkpoint

        try:
            current = store.verified_current(
                verified_manifest["opaque_project_id"], db=db
            )
            if (
                digest(current) != digest(verified_manifest)
                or current["recovery_signing_public_key"] != self.signing_public
                or current["recovery_recipient_public_key"] != self.recipient_public
                or current["recovery_device_id"] != self.device_id
            ):
                raise ValueError("UNTRUSTED_RECOVERY_ROOT")
            verify_checkpoint(checkpoint, current)
            committed = store.kit_anchor(self, current["opaque_project_id"], db=db)
            if self._checkpoint_digest is None and self.manifest_anchor is None:
                if not self._bootstrap_allowed or committed is not None:
                    raise ValueError("IMPORTED_KIT_MISSING_TRUSTED_METADATA")
                if rows:
                    raise ValueError("INITIAL_ANCHOR_ROWS_MUST_BE_EMPTY")
                if checkpoint["cursor"] != 0 and (
                    checkpoint_store is None
                    or digest(checkpoint_store.get(current["opaque_project_id"]))
                    != digest(checkpoint)
                ):
                    raise ValueError("UNTRUSTED_INITIAL_CHECKPOINT")
            else:
                _verify_kit_anchor(self, store, require_current=False, db=db)
                if self.project != current["opaque_project_id"]:
                    raise ValueError("ANCHOR_PROJECT_MISMATCH")
                verify_advance(self.checkpoint_anchor, checkpoint, current, list(rows))
            record = {
                "version": 1,
                "revision": 1 if committed is None else committed["revision"] + 1,
                "previous_digest": ZERO if committed is None else digest(committed),
                "device_id": self.device_id,
                "signing_public_key": self.signing_public,
                "recipient_public_key": self.recipient_public,
                "project": current["opaque_project_id"],
                "manifest_digest": digest(current),
                "membership_epoch": current["membership_epoch"],
                "key_epoch": current["key_epoch"],
                "checkpoint_digest": digest(checkpoint),
                "checkpoint": copy.deepcopy(checkpoint),
                "rows": copy.deepcopy(rows),
            }
            store._save_kit_anchor(record, db=db)
            return record
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("RECOVERY_FRESHNESS_UNVERIFIABLE") from None


def _verify_kit_anchor(kit, store, *, require_current=True, db=None):
    from packages.secure_wire.checkpoint import verify_checkpoint

    try:
        if (
            kit.manifest_anchor is None
            or kit.project is None
            or kit.checkpoint_anchor is None
            or kit._checkpoint_digest is None
        ):
            raise ValueError("MISSING_TRUSTED_ANCHOR")
        if db is None:
            with store.transaction() as connection:
                return _verify_kit_anchor(
                    kit, store, require_current=require_current, db=connection
                )
        current = store.verified_current(kit.project, db=db)
        anchored = store.history(
            kit.project, kit.checkpoint_anchor["membership_epoch"], db=db
        )
        committed = store.kit_anchor(kit, kit.project, db=db)
        if (
            committed is None
            or committed["manifest_digest"] != kit.manifest_anchor
            or committed["checkpoint_digest"] != kit._checkpoint_digest
            or digest(anchored) != kit.manifest_anchor
            or digest(kit.checkpoint_anchor) != kit._checkpoint_digest
            or (require_current and digest(current) != kit.manifest_anchor)
        ):
            raise ValueError("ANCHOR_MISMATCH")
        if (
            anchored["recovery_signing_public_key"] != kit.signing_public
            or anchored["recovery_recipient_public_key"] != kit.recipient_public
            or anchored["recovery_device_id"] != kit.device_id
        ):
            raise ValueError("UNTRUSTED_RECOVERY_ROOT")
        verify_checkpoint(kit.checkpoint_anchor, anchored)
        return current
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("RECOVERY_FRESHNESS_UNVERIFIABLE") from None


def signed_object(kind, value, seed):
    result = copy.deepcopy(value)
    result.pop("signature", None)
    result["signature"] = b64encode(sign(seed, preimage(kind, result)))
    return result


def signed_manifest(value, seed):
    return signed_object("Membership", value, seed)


def bootstrap(project, owner, kit):
    value = {
        "version": 1,
        "opaque_project_id": project,
        "membership_epoch": 1,
        "key_epoch": 1,
        "previous_digest": ZERO,
        "operation": "bootstrap",
        "authority_device_id": owner.device_id,
        "recovery_device_id": kit.device_id,
        "recovery_signing_public_key": kit.signing_public,
        "recovery_recipient_public_key": kit.recipient_public,
        "members": [owner.member("owner", 0)],
    }
    result = signed_manifest(value, owner.signing_seed)
    return verify_bootstrap(result, owner.signing_public, kit.signing_public)


def transition(previous, owner, *, add=None, revoke=None, activate=None, now=0):
    if sum(v is not None for v in (add, revoke, activate)) != 1:
        raise ValueError("INVALID_TRANSITION_REQUEST")
    authority = member_of(previous, owner.device_id, roles=("owner",))
    if authority["signing_public_key"] != owner.signing_public:
        raise ValueError("DEVICE_KEY_MISMATCH")
    value = copy.deepcopy(previous)
    value.update(
        previous_digest=digest(previous),
        membership_epoch=previous["membership_epoch"] + 1,
        authority_device_id=owner.device_id,
    )
    if add is not None:
        value["operation"] = "grant"
        value["members"].append(copy.deepcopy(add))
    elif activate is not None:
        value["operation"] = "grant"
        target = next((m for m in value["members"] if m["device_id"] == activate), None)
        if target is None or target["status"] != "PENDING":
            raise ValueError("UNAUTHORIZED_DEVICE")
        target["status"] = "ACTIVE"
    else:
        value["operation"] = "revoke"
        value["key_epoch"] += 1
        target = member_of(previous, revoke)
        for member in value["members"]:
            if member["device_id"] == target["device_id"]:
                member.update(
                    status="REVOKED", revoked_at=max(now, member["granted_at"])
                )
    result = signed_manifest(value, owner.signing_seed)
    return verify_transition(previous, result, previous["recovery_signing_public_key"])


def grant_context(manifest, recipient, session):
    return {
        "opaque_project_id": manifest["opaque_project_id"],
        "recipient_device_id": recipient["device_id"],
        "key_epoch": manifest["key_epoch"],
        "membership_epoch": manifest["membership_epoch"],
        "session_id": session,
        "recipient_signing_public_key": recipient["signing_public_key"],
        "recipient_public_key": recipient["recipient_public_key"],
    }


def make_grant(manifest, owner, recipient_id, session, key):
    target = member_of(manifest, recipient_id)
    authority = member_of(manifest, owner.device_id, roles=("owner",))
    if authority["signing_public_key"] != owner.signing_public:
        raise ValueError("DEVICE_KEY_MISMATCH")
    context = grant_context(manifest, target, session)
    wrapped = wrap_key(bytes.fromhex(target["recipient_public_key"]), key, context)
    result = signed_object(
        "ProjectGrant",
        {
            "version": 1,
            "authority_device_id": owner.device_id,
            "context": context,
            "role": target["role"],
            "manifest_digest": digest(manifest),
            "wrapped_key": b64encode(wrapped),
        },
        owner.signing_seed,
    )
    return verify_grant(result, manifest)


def open_grant(grant, manifest, device):
    verify_grant(grant, manifest)  # MUST authenticate authority/context before unwrap
    context = grant["context"]
    if (
        context["recipient_device_id"] != device.device_id
        or context["recipient_signing_public_key"] != device.signing_public
        or context["recipient_public_key"] != device.recipient_public
    ):
        raise ValueError("RECIPIENT_MISMATCH")
    return unwrap_key(
        device.recipient_seed, b64decode(grant["wrapped_key"], 80), context
    )


def make_recovery_backup(manifest, owner, kit, project_key):
    if (
        member_of(manifest, owner.device_id, roles=("owner",))["signing_public_key"]
        != owner.signing_public
        or manifest["recovery_device_id"] != kit.device_id
        or manifest["recovery_recipient_public_key"] != kit.recipient_public
        or manifest["recovery_signing_public_key"] != kit.signing_public
    ):
        raise ValueError("UNTRUSTED_RECOVERY_ROOT")
    target = {
        "device_id": kit.device_id,
        "signing_public_key": kit.signing_public,
        "recipient_public_key": kit.recipient_public,
    }
    context = grant_context(manifest, target, str(uuid4()))
    return signed_object(
        "RecoveryBackup",
        {
            "version": 1,
            "authority_device_id": owner.device_id,
            "manifest_digest": digest(manifest),
            "context": context,
            "wrapped_key": b64encode(
                wrap_key(bytes.fromhex(kit.recipient_public), project_key, context)
            ),
        },
        owner.signing_seed,
    )


def open_recovery_backup(backup, store, kit):
    if kit is None:
        raise ValueError("E2E_DATA_UNRECOVERABLE")
    manifest = _verify_kit_anchor(kit, store)
    fields(
        backup,
        frozenset(
            [
                "version",
                "authority_device_id",
                "manifest_digest",
                "context",
                "wrapped_key",
                "signature",
            ]
        ),
    )
    from packages.secure_wire.envelope import safe_int
    from packages.secure_wire.membership import validate_context

    safe_int(backup["version"], 1, 1)
    validate_context(backup["context"])
    c = backup["context"]
    if (
        backup["version"] != 1
        or backup["manifest_digest"] != digest(manifest)
        or c["opaque_project_id"] != kit.project
        or any(c[f] != manifest[f] for f in ("key_epoch", "membership_epoch"))
        or c["recipient_device_id"] != kit.device_id
        or manifest["recovery_device_id"] != kit.device_id
        or c["recipient_signing_public_key"] != kit.signing_public
        or manifest["recovery_signing_public_key"] != kit.signing_public
        or c["recipient_public_key"] != kit.recipient_public
        or manifest["recovery_recipient_public_key"] != kit.recipient_public
    ):
        raise ValueError("RECOVERY_BACKUP_BINDING_MISMATCH")
    authority = member_of(manifest, backup["authority_device_id"], roles=("owner",))
    verify_signed("RecoveryBackup", backup, authority["signing_public_key"])
    return unwrap_key(kit.recipient_seed, b64decode(backup["wrapped_key"], 80), c)


@dataclass
class Rotation:
    manifest: dict
    grants: dict
    key: bytes = field(repr=False)


def revoke_and_rotate(store, vault, owner, target, *, now=0):
    with store.transaction() as db:
        project = db.execute("SELECT project FROM roots").fetchall()
        if len(project) != 1:
            raise ValueError("PROJECT_SELECTION_REQUIRED")
        previous = store.current(project[0][0], db=db)
        candidate = transition(previous, owner, revoke=target, now=now)
        # Fresh CSPRNG key. Failed public commit leaves an unused epoch key;
        # retry must use a fresh QA vault, never silently reuse old material.
        key = vault.create(candidate["opaque_project_id"], candidate["key_epoch"])
        grants = {
            m["device_id"]: make_grant(
                candidate, owner, m["device_id"], str(uuid4()), key
            )
            for m in candidate["members"]
            if m["status"] == "ACTIVE"
        }
        store.accept(candidate, db=db)
    return Rotation(candidate, grants, key)


def classify_envelope(store, envelope):
    from packages.secure_wire.envelope import validate_envelope

    validate_envelope(envelope)
    with store.transaction() as db:
        current = store.verified_current(envelope["opaque_project_id"], db=db)
        if envelope["membership_epoch"] < current["membership_epoch"]:
            historical = store.history(
                envelope["opaque_project_id"], envelope["membership_epoch"], db=db
            )
            return verify_historical_envelope(envelope, historical, current)
        verify_active_envelope(envelope, current)
    return {"status": "AUTHORIZED", "envelope_digest": digest(envelope)}


class TrustedStore:
    """PUBLIC TEST ONLY SQLite pinned-history store. Same transaction pairs state."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS roots(project TEXT PRIMARY KEY, owner TEXT NOT NULL, recovery TEXT NOT NULL); CREATE TABLE IF NOT EXISTS manifests(project TEXT NOT NULL, digest TEXT PRIMARY KEY, epoch INTEGER NOT NULL, body BLOB NOT NULL, UNIQUE(project,epoch)); CREATE TABLE IF NOT EXISTS challenges(session TEXT PRIMARY KEY, body BLOB NOT NULL, response_digest TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0, receipt BLOB);"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS kit_anchors(kit_id TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL,body BLOB NOT NULL,PRIMARY KEY(kit_id,project,revision))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS kit_anchor_heads(kit_id TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(kit_id,project))"
            )

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def current(self, project, *, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.current(project, db=connection)
        return self._verified_history(project, db)[-1]

    def bootstrap(self, manifest, owner_public, recovery_public):
        verify_bootstrap(manifest, owner_public, recovery_public)
        with self.transaction() as db:
            if db.execute(
                "SELECT 1 FROM roots WHERE project=?", (manifest["opaque_project_id"],)
            ).fetchone():
                raise ValueError("BOOTSTRAP_ALREADY_PINNED")
            db.execute(
                "INSERT INTO roots VALUES (?,?,?)",
                (manifest["opaque_project_id"], owner_public, recovery_public),
            )
            self._save(db, manifest)

    def _save(self, db, manifest):
        db.execute(
            "INSERT INTO manifests VALUES (?,?,?,?)",
            (
                manifest["opaque_project_id"],
                digest(manifest),
                manifest["membership_epoch"],
                canonical_bytes(manifest),
            ),
        )

    def accept(self, candidate, *, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.accept(candidate, db=connection)
        project = candidate["opaque_project_id"]
        previous = self.current(project, db=db)
        root = db.execute(
            "SELECT recovery FROM roots WHERE project=?", (project,)
        ).fetchone()[0]
        verify_transition(previous, candidate, root)
        if digest(previous) != digest(candidate):
            self._save(db, candidate)
        return candidate

    def history(self, project, membership_epoch, *, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.history(project, membership_epoch, db=connection)
        from packages.secure_wire.envelope import safe_int

        safe_int(membership_epoch, 1)
        history = self._verified_history(project, db)
        if membership_epoch > len(history):
            raise ValueError("UNPINNED_MEMBERSHIP_HISTORY")
        return history[membership_epoch - 1]

    def verified_current(self, project, *, db=None):
        """Recheck stored chain from separately pinned bootstrap roots on restart."""
        if db is None:
            with self.transaction() as connection:
                return self.verified_current(project, db=connection)
        return self._verified_history(project, db)[-1]

    def _verified_history(self, project, db):
        """SQL columns are untrusted indexes; validate every row before selecting.

        Scanning all public metadata also detects a target row whose SQL project
        was moved out of this project's query. QA scope, not a production index.
        """
        roots = db.execute(
            "SELECT owner,recovery FROM roots WHERE project=?", (project,)
        ).fetchone()
        rows = db.execute(
            "SELECT project,digest,epoch,body FROM manifests ORDER BY project,epoch"
        ).fetchall()
        histories = {}
        for sql_project, sql_digest, sql_epoch, raw in rows:
            manifest = strict_loads(raw)
            validate_manifest(manifest)
            history = histories.setdefault(sql_project, [])
            if (
                sql_project != manifest["opaque_project_id"]
                or sql_digest != digest(manifest)
                or type(sql_epoch) is not int
                or sql_epoch != manifest["membership_epoch"]
                or sql_epoch != len(history) + 1
                or manifest["previous_digest"]
                != (ZERO if not history else digest(history[-1]))
            ):
                raise ValueError("MEMBERSHIP_STORAGE_INTEGRITY")
            history.append(manifest)
        history = histories.get(project, [])
        if roots is None or not history:
            raise ValueError("UNTRUSTED_PROJECT")
        previous = history[0]
        verify_bootstrap(previous, roots[0], roots[1])
        for manifest in history[1:]:
            previous = verify_transition(previous, manifest, roots[1])
        return history

    def kit_anchor(self, kit, project, *, db):
        """Revalidate the complete committed PUBLIC metadata journal."""
        from packages.secure_wire.checkpoint import verify_advance, verify_checkpoint
        from packages.secure_wire.envelope import safe_int

        self.verified_current(project, db=db)
        rows = db.execute(
            "SELECT revision,body FROM kit_anchors WHERE kit_id=? AND project=? ORDER BY revision",
            (kit.device_id, project),
        ).fetchall()
        head = db.execute(
            "SELECT revision,digest FROM kit_anchor_heads WHERE kit_id=? AND project=?",
            (kit.device_id, project),
        ).fetchone()
        previous = None
        for expected, (revision, raw) in enumerate(rows, 1):
            record = strict_loads(raw)
            fields(
                record,
                frozenset(
                    [
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
                    ]
                ),
            )
            safe_int(record["version"], 1, 1)
            safe_int(record["revision"], 1)
            safe_int(record["membership_epoch"], 1)
            safe_int(record["key_epoch"], 1)
            if (
                revision != expected
                or record["revision"] != expected
                or record["previous_digest"]
                != (ZERO if previous is None else digest(previous))
                or record["device_id"] != kit.device_id
                or record["project"] != project
                or record["signing_public_key"] != kit.signing_public
                or record["recipient_public_key"] != kit.recipient_public
            ):
                raise ValueError("KIT_METADATA_BINDING_MISMATCH")
            manifest = self.history(project, record["membership_epoch"], db=db)
            if (
                digest(manifest) != record["manifest_digest"]
                or manifest["key_epoch"] != record["key_epoch"]
                or manifest["recovery_device_id"] != kit.device_id
                or manifest["recovery_signing_public_key"] != kit.signing_public
                or manifest["recovery_recipient_public_key"] != kit.recipient_public
                or digest(record["checkpoint"]) != record["checkpoint_digest"]
            ):
                raise ValueError("KIT_METADATA_BINDING_MISMATCH")
            verify_checkpoint(record["checkpoint"], manifest)
            if type(record["rows"]) is not list:
                raise ValueError("INVALID_CHECKPOINT_PAGE")
            if previous is None and record["rows"]:
                raise ValueError("INITIAL_ANCHOR_ROWS_MUST_BE_EMPTY")
            if previous is not None:
                if (
                    record["membership_epoch"] < previous["membership_epoch"]
                    or record["key_epoch"] < previous["key_epoch"]
                ):
                    raise ValueError("ROLLBACK_DETECTED")
                verify_advance(
                    previous["checkpoint"],
                    record["checkpoint"],
                    manifest,
                    record["rows"],
                )
            previous = record
        if (head is None) != (previous is None) or (
            previous is not None and head != (previous["revision"], digest(previous))
        ):
            raise ValueError("KIT_METADATA_HEAD_MISMATCH")
        return previous

    def _save_kit_anchor(self, record, *, db):
        db.execute(
            "INSERT INTO kit_anchors VALUES (?,?,?,?)",
            (
                record["device_id"],
                record["project"],
                record["revision"],
                canonical_bytes(record),
            ),
        )
        db.execute(
            "INSERT INTO kit_anchor_heads VALUES (?,?,?,?) ON CONFLICT(kit_id,project) DO UPDATE SET revision=excluded.revision,digest=excluded.digest",
            (
                record["device_id"],
                record["project"],
                record["revision"],
                digest(record),
            ),
        )


def recover(store, kit, new_owner, *, chain=(), now=0):
    if kit is None:
        raise ValueError("E2E_DATA_UNRECOVERABLE")
    _verify_kit_anchor(kit, store)
    chain = list(chain)
    if any(
        type(candidate) is not dict or candidate.get("opaque_project_id") != kit.project
        for candidate in chain
    ):
        raise ValueError("RECOVERY_CHAIN_PROJECT_MISMATCH")
    # A continuous verified chain can advance an existing trusted anchor; it
    # cannot prove that Relay has not hidden another unanchored update.
    with store.transaction() as db:
        _verify_kit_anchor(kit, store, db=db)
        if digest(store.current(kit.project, db=db)) != kit.manifest_anchor:
            raise ValueError("RECOVERY_FRESHNESS_UNVERIFIABLE")
        for candidate in chain:
            store.accept(candidate, db=db)
        previous = store.current(kit.project, db=db)
        prefix = max(m["nonce_prefix"] for m in previous["members"]) + 1
        if prefix > 4294967295:
            raise ValueError("PREFIX_EXHAUSTED")
        value = copy.deepcopy(previous)
        for member in value["members"]:
            if member["status"] != "REVOKED":
                member.update(
                    status="REVOKED", revoked_at=max(now, member["granted_at"])
                )
        value["members"].append(new_owner.member("owner", prefix, now=now))
        value.update(
            operation="recovery",
            authority_device_id=new_owner.device_id,
            previous_digest=digest(previous),
            membership_epoch=previous["membership_epoch"] + 1,
            key_epoch=previous["key_epoch"] + 1,
        )
        result = signed_manifest(value, kit.signing_seed)
        store.accept(result, db=db)
        from .checkpoint import sign_checkpoint

        checkpoint = sign_checkpoint(
            result,
            new_owner,
            kit.checkpoint_anchor["cursor"],
            kit.checkpoint_anchor["chain_digest"],
        )
        record = kit._stage_anchor(result, checkpoint, store, [], None, db)
    kit._install_anchor(record)
    return result
