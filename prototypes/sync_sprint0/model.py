"""Strict synthetic business changes and shared immutable SQLite revision store."""

import json
import sqlite3
from dataclasses import asdict, dataclass
from hashlib import sha256
from uuid import UUID


class ProtocolError(ValueError):
    """Rejected protocol input; no silent replacement permitted."""


class MissingDependency(ProtocolError):
    """Retry only after causal dependencies become available."""


FIELDS = {
    "ResearchRun": {"title", "description", "parent_run_id"},
    "Parameter": {"name", "value", "unit", "run_id"},
    "Metric": {"name", "value", "unit", "run_id"},
    "Note": {"text", "human_conclusion", "run_id"},
    "HumanConclusion": {"text", "run_id"},
    "Artifact": {"filename", "sha256", "size", "key_epoch", "content_hex", "run_id"},
}


def canonical(value):
    """Python strict sorted JSON for this demo; deliberately not RFC 8785 JCS."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ProtocolError("noncanonical/invalid JSON") from exc


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ProtocolError(f"invalid JSON constant {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("invalid strict JSON") from exc


def uuid_check(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProtocolError("canonical UUID required") from exc


@dataclass(frozen=True)
class ChangeSet:
    change_id: str
    audit_id: str
    device_id: str
    project_id: str
    object_type: str
    object_id: str
    operation: str
    base_revision: str | None
    payload: dict
    created_at: str
    actor_type: str = "human"
    expected_heads: tuple[str, ...] = ()
    schema_version: int = 1
    protocol_version: int = 1
    encryption: str = "plaintext-simulator"

    @property
    def revision(self):
        return digest(asdict(self))

    @property
    def parents(self):
        return self.expected_heads if self.operation == "resolve" else (
            (self.base_revision,) if self.base_revision else ())

    def to_json(self):
        return canonical(asdict(self))

    @classmethod
    def from_json(cls, raw):
        data = strict_load(raw)
        try:
            data["expected_heads"] = tuple(data.get("expected_heads", ()))
            change = cls(**data)
            change.validate()
            return change
        except (TypeError, KeyError) as exc:
            raise ProtocolError("unknown/malformed ChangeSet fields") from exc

    def validate(self, principal_type=None):
        canonical(asdict(self))
        for value in (self.change_id, self.audit_id, self.device_id, self.project_id, self.object_id):
            uuid_check(value)
        if (type(self.schema_version) is not int or self.schema_version != 1
                or type(self.protocol_version) is not int or self.protocol_version != 1):
            raise ProtocolError("unsupported schema/protocol version")
        if self.object_type not in FIELDS:
            raise ProtocolError("unknown object type")
        if self.operation not in {"create", "update", "trash", "restore", "resolve"}:
            raise ProtocolError("unsupported operation; purge forbidden")
        if self.encryption != "plaintext-simulator":
            raise ProtocolError("unsupported encryption placeholder")
        if not isinstance(self.payload, dict) or set(self.payload) - FIELDS[self.object_type]:
            raise ProtocolError("unknown business fields")
        for key, value in self.payload.items():
            if key.endswith("_id"):
                uuid_check(value)
            elif key not in {"value", "size", "key_epoch"} and not isinstance(value, str):
                raise ProtocolError("business text field must be a string")
        if self.actor_type not in {"human", "ai"}:
            raise ProtocolError("unknown actor claim")
        if principal_type is not None and self.actor_type != principal_type:
            raise ProtocolError("actor claim does not match registered principal")
        authority = principal_type or self.actor_type
        if authority == "ai" and (self.object_type == "HumanConclusion"
                                  or "human_conclusion" in self.payload
                                  or self.operation in {"resolve", "restore"}):
            raise ProtocolError("human-only authority required")
        if self.operation == "create" and (self.base_revision or self.expected_heads):
            raise ProtocolError("create must have no parent")
        if self.operation != "create" and not self.base_revision:
            raise MissingDependency("base revision required")
        if self.operation == "resolve":
            if (len(self.expected_heads) < 2
                    or self.expected_heads != tuple(sorted(set(self.expected_heads)))
                    or self.base_revision not in self.expected_heads):
                raise ProtocolError("resolution requires exact sorted head set")
        elif self.expected_heads:
            raise ProtocolError("unexpected resolution heads")
        if (self.object_type in {"Parameter", "Metric"} and "value" in self.payload
                and type(self.payload["value"]) not in {int, float}):
            raise ProtocolError("scientific value must be a finite number")
        if (self.object_type == "Artifact" and self.operation in {"create", "resolve"}
                and not {"filename", "sha256", "size", "key_epoch"} <= set(self.payload)):
            raise ProtocolError("artifact metadata incomplete")
        if self.object_type == "Artifact":
            for key in ("size", "key_epoch"):
                if key in self.payload and (type(self.payload[key]) is not int
                                           or self.payload[key] < 0):
                    raise ProtocolError("invalid artifact size/key epoch")
            if "content_hex" in self.payload:
                try:
                    content = bytes.fromhex(self.payload["content_hex"])
                except (TypeError, ValueError) as exc:
                    raise ProtocolError("artifact checksum encoding") from exc
                if (sha256(content).hexdigest() != self.payload.get("sha256")
                        or len(content) != self.payload.get("size")):
                    raise ProtocolError("artifact checksum/size mismatch")


class RevisionStore:
    """One connection per simulator node; callers own atomic transactions."""

    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS revisions (
                revision TEXT PRIMARY KEY, change_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL, object_id TEXT NOT NULL,
                body TEXT NOT NULL, document TEXT NOT NULL, lifecycle TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                audit_id TEXT PRIMARY KEY, change_id TEXT UNIQUE NOT NULL, event TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS blobs (
                project_id TEXT, key_epoch INTEGER, checksum TEXT, content BLOB NOT NULL,
                PRIMARY KEY(project_id, key_epoch, checksum));
        """)

    def _rows(self, object_id):
        return {row[0]: (ChangeSet.from_json(row[1]), strict_load(row[2]), row[3])
                for row in self.db.execute(
                    "SELECT revision,body,document,lifecycle FROM revisions WHERE object_id=?",
                    (object_id,))}

    @staticmethod
    def _ancestors(revision, rows):
        found = {revision}
        for parent in rows[revision][0].parents:
            found |= RevisionStore._ancestors(parent, rows)
        return found

    def state(self, object_id):
        rows = self._rows(object_id)
        if not rows:
            return None
        consumed = {p for change, _, _ in rows.values() for p in change.parents}
        heads = sorted(set(rows) - consumed)
        common = set.intersection(*(self._ancestors(h, rows) for h in heads))
        # Ambiguous merge bases never select a scientific value by hash/order.
        while common:
            maximal = [r for r in common if not any(
                r != other and r in self._ancestors(other, rows) for other in common)]
            if len(maximal) == 1:
                projection = rows[maximal[0]][1]
                break
            common = set.intersection(*(self._ancestors(r, rows) - {r} for r in maximal))
        else:
            projection = {}
        lifecycles = {rows[h][2] for h in heads}
        return {"heads": heads, "conflict": len(heads) > 1, "projection": projection,
                "lifecycle": "trashed" if "trashed" in lifecycles else "active",
                "candidates": [{"revision": h, "document": rows[h][1],
                                "lifecycle": rows[h][2]} for h in heads]}

    def _insert(self, change, principal_type):
        change.validate(principal_type)
        old = self.db.execute("SELECT revision FROM revisions WHERE change_id=?",
                              (change.change_id,)).fetchone()
        if old:
            if old[0] != change.revision:
                raise ProtocolError("change identity collision")
            return
        rows = self._rows(change.object_id)
        if change.operation == "create" and rows:
            raise ProtocolError("object identity already exists")
        for parent in change.parents:
            if parent not in rows:
                raise MissingDependency("missing base revision dependency")
            if (rows[parent][0].project_id != change.project_id
                    or rows[parent][0].object_type != change.object_type):
                raise ProtocolError("parent identity/type/project mismatch")
        if change.operation == "resolve":
            for head in change.parents:
                if any(head != other and head in self._ancestors(other, rows)
                       for other in change.parents):
                    raise ProtocolError("resolution parents are not a head set")
        lifecycle, before = "active", {}
        if change.parents:
            before = rows[change.base_revision][1]
            lifecycle = "trashed" if any(rows[p][2] == "trashed" for p in change.parents) else "active"
        if lifecycle == "trashed" and change.operation == "update":
            raise ProtocolError("trashed object requires explicit restore")
        if change.operation == "trash":
            lifecycle = "trashed"
        elif change.operation == "restore":
            if lifecycle != "trashed":
                raise ProtocolError("restore requires trashed parent")
            lifecycle = "active"
        document = dict(before) if change.operation != "resolve" else {}
        document.update({k: v for k, v in change.payload.items() if k != "content_hex"})
        self.db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?)",
                        (change.revision, change.change_id, change.project_id, change.object_id,
                         change.to_json(), canonical(document), lifecycle))
        event = {"audit_id": change.audit_id, "device_id": change.device_id,
                 "actor_type": principal_type, "timestamp": change.created_at,
                 "object_id": change.object_id, "action": "resolve_sync_conflict"
                 if change.operation == "resolve" else change.operation,
                 "before": before, "after": document, "revision": change.revision}
        try:
            self.db.execute("INSERT INTO audit VALUES (?,?,?)",
                            (change.audit_id, change.change_id, canonical(event)))
        except sqlite3.IntegrityError as exc:
            raise ProtocolError("audit identity collision") from exc
        if "content_hex" in change.payload:
            self.db.execute("INSERT OR IGNORE INTO blobs VALUES (?,?,?,?)",
                            (change.project_id, change.payload["key_epoch"],
                             change.payload["sha256"], bytes.fromhex(change.payload["content_hex"])))

    def audit_count(self):
        return self.db.execute("SELECT count(*) FROM audit").fetchone()[0]

    def blob_count(self):
        return self.db.execute("SELECT count(*) FROM blobs").fetchone()[0]
