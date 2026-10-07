"""Durable offline replica; atomic inbox/domain/audit/cursor SQLite apply."""

from datetime import datetime, timezone
from uuid import uuid4

from .model import (
    ChangeSet,
    MissingDependency,
    ProtocolError,
    RevisionStore,
    canonical,
    digest,
    strict_load,
    uuid_check,
)


class Replica(RevisionStore):
    def __init__(self, path, project_id, principal_type="human"):
        super().__init__(path)
        uuid_check(project_id)
        self.project_id = project_id
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS outbox (
                transaction_id TEXT PRIMARY KEY, body TEXT NOT NULL, pushed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS inbox (
                transaction_id TEXT PRIMARY KEY, digest TEXT NOT NULL, sequence INTEGER UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS quarantine (
                transaction_id TEXT PRIMARY KEY, body TEXT NOT NULL, reason TEXT NOT NULL);
        """)
        with self.db:
            for key, value in (("device_id", str(uuid4())), ("project_id", project_id),
                               ("principal_type", principal_type), ("cursor", "0")):
                self.db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, value))
        settings = dict(self.db.execute("SELECT key,value FROM settings"))
        if settings["project_id"] != project_id or settings["principal_type"] != principal_type:
            raise ProtocolError("replica identity context mismatch")
        self.device_id = settings["device_id"]
        self.principal_type = settings["principal_type"]

    @property
    def cursor(self):
        return int(self.db.execute("SELECT value FROM settings WHERE key='cursor'").fetchone()[0])

    def _mutate(self, object_type, object_id, operation, base, payload, heads=()):
        change = ChangeSet(str(uuid4()), str(uuid4()), self.device_id, self.project_id,
                           object_type, object_id, operation, base, strict_load(canonical(payload)),
                           datetime.now(timezone.utc).isoformat(), self.principal_type, tuple(heads))
        with self.db:
            self._insert(change, self.principal_type)
            self.db.execute("INSERT INTO outbox(transaction_id,body) VALUES (?,?)",
                            (str(uuid4()), canonical([strict_load(change.to_json())])))
        return change

    def create(self, object_type, payload):
        return self._mutate(object_type, str(uuid4()), "create", None, payload)

    def _edit(self, object_id, operation, payload):
        state = self.state(object_id)
        if not state:
            raise ProtocolError("unknown object")
        if state["conflict"]:
            raise ProtocolError("conflict requires explicit resolution")
        parent = self._rows(object_id)[state["heads"][0]][0]
        return self._mutate(parent.object_type, object_id, operation, parent.revision, payload)

    def update(self, object_id, patch):
        return self._edit(object_id, "update", patch)

    def trash(self, object_id):
        return self._edit(object_id, "trash", {})

    def restore(self, object_id):
        return self._edit(object_id, "restore", {})

    def resolve(self, object_id, expected_heads, document):
        state = self.state(object_id)
        heads = tuple(sorted(expected_heads))
        if not state or list(heads) != state["heads"] or len(heads) < 2:
            raise ProtocolError("resolution expected head set differs from local heads")
        parent = self._rows(object_id)[heads[0]][0]
        return self._mutate(parent.object_type, object_id, "resolve", heads[0], document, heads)

    def push_pending(self, relay):
        receipts = []
        for tx, raw in self.db.execute(
                "SELECT transaction_id,body FROM outbox WHERE pushed=0 ORDER BY rowid").fetchall():
            receipt = relay.push([ChangeSet.from_json(canonical(c)) for c in strict_load(raw)],
                                 tx, self.device_id)
            with self.db:
                self.db.execute("UPDATE outbox SET pushed=1 WHERE transaction_id=?", (tx,))
            receipts.append(receipt)
        return receipts

    def apply_batch(self, batch, crash_after=None):
        if batch["project_id"] != self.project_id or batch.get("commit_marker") is not True:
            raise ProtocolError("project mismatch or missing commit marker")
        unsigned = {k: v for k, v in batch.items() if k not in {"sequence", "digest", "ack"}}
        if digest(unsigned) != batch["digest"]:
            raise ProtocolError("batch digest mismatch")
        tx = batch["transaction_id"]
        try:
            with self.db:
                prior = self.db.execute("SELECT digest,sequence FROM inbox WHERE transaction_id=?",
                                        (tx,)).fetchone()
                if prior:
                    if prior != (batch["digest"], batch["sequence"]):
                        raise ProtocolError("inbox transaction identity collision")
                    return True
                if batch["sequence"] != self.cursor + 1:
                    raise MissingDependency("missing earlier cursor batch")
                self.db.execute("INSERT INTO inbox VALUES (?,?,?)",
                                (tx, batch["digest"], batch["sequence"]))
                for index, data in enumerate(batch["changes"], 1):
                    change = ChangeSet.from_json(canonical(data))
                    if change.device_id != batch["principal_device_id"]:
                        raise ProtocolError("batch principal device mismatch")
                    self._insert(change, batch["principal_type"])
                    if crash_after == index:
                        raise RuntimeError("injected pull apply crash")
                self.db.execute("UPDATE settings SET value=? WHERE key='cursor'",
                                (str(batch["sequence"]),))
                self.db.execute("DELETE FROM quarantine WHERE transaction_id=?", (tx,))
            return True
        except MissingDependency as exc:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO quarantine VALUES (?,?,?)",
                                (tx, canonical(batch), str(exc)))
            return False

    def pull(self, relay, limit=100):
        for batch in relay.pull(self.project_id, self.cursor, limit):
            if not self.apply_batch(batch):
                break

    def inbox_count(self):
        return self.db.execute("SELECT count(*) FROM inbox").fetchone()[0]

    def quarantine_count(self):
        return self.db.execute("SELECT count(*) FROM quarantine").fetchone()[0]
