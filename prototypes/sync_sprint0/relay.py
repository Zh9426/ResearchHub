"""SQLite synthetic relay: receipts do not accept scientific winners."""

from .model import (
    ProtocolError,
    RevisionStore,
    canonical,
    digest,
    strict_load,
    uuid_check,
)


class Relay(RevisionStore):
    def __init__(self, path):
        super().__init__(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, principal_type TEXT);
            CREATE TABLE IF NOT EXISTS batches (
                transaction_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL,
                UNIQUE(project_id, sequence));
        """)

    def register_device(self, device_id, principal_type):
        uuid_check(device_id)
        if principal_type not in {"human", "ai"}:
            raise ProtocolError("unknown principal")
        with self.db:
            prior = self.db.execute("SELECT principal_type FROM devices WHERE device_id=?",
                                    (device_id,)).fetchone()
            if prior and prior[0] != principal_type:
                raise ProtocolError("device principal identity collision")
            self.db.execute("INSERT OR IGNORE INTO devices VALUES (?,?)", (device_id, principal_type))

    def push(self, changes, transaction_id, principal_device_id, crash_after=None):
        uuid_check(transaction_id)
        principal = self.db.execute("SELECT principal_type FROM devices WHERE device_id=?",
                                    (principal_device_id,)).fetchone()
        if not principal:
            raise ProtocolError("unregistered simulator principal")
        if not changes or len({c.project_id for c in changes}) != 1:
            raise ProtocolError("batch must have one project and at least one change")
        if len({c.change_id for c in changes}) != len(changes):
            raise ProtocolError("duplicate change identity within batch")
        body = {"transaction_id": transaction_id, "project_id": changes[0].project_id,
                "principal_type": principal[0], "principal_device_id": principal_device_id,
                "changes": [strict_load(c.to_json()) for c in changes], "commit_marker": True}
        batch_digest = digest(body)
        with self.db:
            old = self.db.execute("SELECT digest,body FROM batches WHERE transaction_id=?",
                                  (transaction_id,)).fetchone()
            if old:
                if old[0] != batch_digest:
                    raise ProtocolError("transaction identity collision")
                return strict_load(old[1])
            for index, change in enumerate(changes, 1):
                if change.device_id != principal_device_id:
                    raise ProtocolError("principal device does not match change device")
                self._insert(change, principal[0])
                if crash_after == index:
                    raise RuntimeError("injected push halfway crash")
            sequence = self.db.execute(
                "SELECT coalesce(max(sequence),0)+1 FROM batches WHERE project_id=?",
                (changes[0].project_id,)).fetchone()[0]
            receipt = {**body, "sequence": sequence, "digest": batch_digest,
                       "ack": "transport-durable"}
            self.db.execute("INSERT INTO batches VALUES (?,?,?,?,?)",
                            (transaction_id, changes[0].project_id, sequence, batch_digest,
                             canonical(receipt)))
        return receipt

    def pull(self, project_id, cursor, limit=100):
        return [strict_load(row[0]) for row in self.db.execute(
            "SELECT body FROM batches WHERE project_id=? AND sequence>? ORDER BY sequence LIMIT ?",
            (project_id, cursor, limit))]
