"""TEST ONLY SQLite nonce reservation with a separate durable rollback witness.

All validation happens under BEGIN IMMEDIATE; witness fsync precedes commit.
Losing or restoring every trusted file together is outside this rollback model.
"""

import hashlib
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from packages.secure_wire.envelope import canonical_bytes, safe_int, strict_loads

MAX_COUNTER = 9007199254740991


class NonceVault:
    def __init__(self, path):
        self.path = Path(path)
        self.witness_path = Path(str(path) + ".witness")
        self.anchor_path = Path(str(path) + ".anchor")

    def _identity(self, key, prefix):
        if type(key) is not bytes or len(key) != 32:
            raise ValueError("NONCE_STATE_INVALID")
        safe_int(prefix, 0, 4294967295)
        return hashlib.sha256(key).hexdigest() + ":" + str(prefix)

    def _initialize(self):
        present = [p.exists() for p in (self.path, self.witness_path, self.anchor_path)]
        if any(present):
            if not all(present):
                raise ValueError("NONCE_STATE_INVALID")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # An interrupted initialization leaves an anchor and cannot reset itself.
        fd = os.open(
            self.anchor_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            os.write(fd, b"RH-NONCE-1\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE nonces (identity TEXT PRIMARY KEY, counter INTEGER NOT NULL)"
            )
        fd = os.open(
            self.witness_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _connect(self):
        if not all(
            p.is_file() for p in (self.path, self.witness_path, self.anchor_path)
        ):
            raise ValueError("NONCE_STATE_INVALID")
        try:
            db = sqlite3.connect(
                f"file:{self.path.as_posix()}?mode=rw", uri=True, timeout=30
            )
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            return db
        except sqlite3.Error:
            raise ValueError("NONCE_STATE_INVALID") from None

    def _validate(self, db):
        if self.anchor_path.read_bytes() != b"RH-NONCE-1\n":
            raise ValueError("NONCE_STATE_INVALID")
        raw = self.witness_path.read_bytes()
        latest = {}
        if raw and not raw.endswith(b"\n"):
            raise ValueError("NONCE_STATE_INVALID")
        for line in raw.split(b"\n")[:-1]:
            value = strict_loads(line)
            if (
                type(value) is not dict
                or set(value) != {"identity", "counter"}
                or canonical_bytes(value) != line
            ):
                raise ValueError("NONCE_STATE_INVALID")
            identity = value["identity"]
            counter = value["counter"]
            if type(identity) is not str or not re.fullmatch(
                r"[0-9a-f]{64}:(0|[1-9][0-9]*)", identity
            ):
                raise ValueError("NONCE_STATE_INVALID")
            safe_int(int(identity.split(":")[1]), 0, 4294967295)
            safe_int(counter)
            if counter != latest.get(identity, -1) + 1:
                raise ValueError("NONCE_STATE_INVALID")
            latest[identity] = counter
        rows = dict(db.execute("SELECT identity,counter FROM nonces"))
        if rows != latest:
            raise ValueError("NONCE_STATE_INVALID")
        return rows

    def _append(self, identity, counter):
        fd = os.open(
            self.witness_path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0)
        )
        try:
            data = canonical_bytes({"identity": identity, "counter": counter}) + b"\n"
            written = os.write(fd, data)
            if written != len(data):
                raise ValueError("NONCE_STATE_INVALID")
            os.fsync(fd)
        finally:
            os.close(fd)

    def register_new(self, key, prefix):
        identity = self._identity(key, prefix)
        self._initialize()
        db = self._connect()
        try:
            rows = self._validate(db)
            if identity in rows:
                raise ValueError("NONCE_ALREADY_REGISTERED")
            db.execute("INSERT INTO nonces VALUES (?,0)", (identity,))
            self._append(identity, 0)
            db.commit()
        except sqlite3.Error:
            raise ValueError("NONCE_STATE_INVALID") from None
        finally:
            db.close()

    def reserve(self, key, prefix, *, crash_point=None):
        identity = self._identity(key, prefix)
        db = self._connect()
        try:
            rows = self._validate(db)
            if identity not in rows or rows[identity] >= MAX_COUNTER:
                raise ValueError("NONCE_STATE_INVALID")
            counter = rows[identity] + 1
            db.execute(
                "UPDATE nonces SET counter=? WHERE identity=?", (counter, identity)
            )
            self._append(identity, counter)
            if crash_point == "after_witness":
                raise RuntimeError("SYNTHETIC_CRASH_AFTER_WITNESS")
            db.commit()
            if crash_point == "after_commit":
                raise RuntimeError("SYNTHETIC_CRASH_AFTER_COMMIT")
            return prefix.to_bytes(4, "big") + counter.to_bytes(8, "big")
        except sqlite3.Error:
            raise ValueError("NONCE_STATE_INVALID") from None
        finally:
            db.close()
