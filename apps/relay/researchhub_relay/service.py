"""PUBLIC-only durable Relay transactions. Authentication always precedes caches."""

import os
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.checkpoint import extend_chain, verify_checkpoint
from packages.secure_wire.envelope import TRANSACTION_VERSION_PAIRS, b64decode, hex_bytes, safe_int, uuid
from packages.secure_wire.membership import (
    fields,
    member_of,
    verify_active_envelope,
    verify_bootstrap,
    verify_challenge,
    verify_grant,
    verify_signed,
    verify_transition,
)
from packages.secure_wire.request import verify_request

from .models import (
    Base,
    Budget,
    Chunk,
    Message,
    PairSession,
    Project,
    PublicObject,
    RequestReceipt,
)

MAX_RESPONSE = 524288
MAX_CIPHER = 16777216
MAX_CACHE = 8388608
STAGES = (
    "DEVICE_RECEIVED",
    "DEVICE_DECRYPTED",
    "KERNEL_APPLIED",
    "SCIENTIFIC_ACCEPTED",
    "ARTIFACT_PRIMARY_DURABLE",
)
ERRORS = frozenset(
    (
        "AUTH_REJECTED",
        "INVALID_REQUEST",
        "REQUEST_TOO_LARGE",
        "RATE_LIMITED",
        "CACHE_FULL",
        "REQUEST_ID_COLLISION",
        "RECEIPT_UNAVAILABLE",
        "MESSAGE_ID_COLLISION",
        "NONCE_REUSED",
        "CIPHER_QUOTA_EXCEEDED",
        "MESSAGE_TOO_LARGE",
        "BATCH_LIMIT",
        "CURSOR_GAP",
        "PAIRING_EXPIRED",
        "PAIRING_USED",
        "PAIRING_ATTEMPTS_EXCEEDED",
        "PAIRING_SCOPE_MISMATCH",
        "PAIRING_RETRY_STALE_EPOCH",
        "NOT_FOUND",
        "OBJECT_COLLISION",
        "METADATA_QUOTA_EXCEEDED",
        "MEMBERSHIP_CAS_MISMATCH",
        "MEMBERSHIP_FORK",
        "EPOCH_TRANSITION_INVALID",
        "INVALID_SIGNATURE",
        "INVALID_ENVELOPE",
        "STALE_MEMBERSHIP_OR_KEY_EPOCH",
        "NONCE_BINDING_MISMATCH",
        "UNSUPPORTED_SUITE",
        "ACK_BINDING_MISMATCH",
        "CHUNK_BINDING_MISMATCH",
        "SERVICE_UNAVAILABLE",
        "TIMEOUT",
    )
)


def error_code(exc):
    value = str(exc)
    return value if value in ERRORS else "INVALID_REQUEST"


def initialize(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        if db.get(Budget, "global") is None:
            db.add(Budget(id="global", events=b"[]"))


def pin_bootstrap(engine, manifest, owner_public, recovery_public):
    """Trusted local admin only; never exposed through HTTP."""
    verify_bootstrap(manifest, owner_public, recovery_public)
    with Session(engine) as db, db.begin():
        existing = db.get(Project, manifest["opaque_project_id"])
        if existing:
            if existing.manifest != canonical_bytes(manifest):
                raise ValueError("OBJECT_COLLISION")
            return
        if db.scalar(select(func.count()).select_from(Project)) >= 64:
            raise ValueError("METADATA_QUOTA_EXCEEDED")
        db.add(
            Project(
                id=manifest["opaque_project_id"], manifest=canonical_bytes(manifest)
            )
        )
        db.add(
            PublicObject(
                project=manifest["opaque_project_id"],
                kind="manifest",
                id=digest(manifest),
                body=canonical_bytes(manifest),
            )
        )


def charge(engine, proof=None, *, now=None):
    """Independent commit makes rejected requests and retries consume rate budget.

    Global has one fixed bucket. Per-device buckets can only be allocated for
    pinned members, pinned recovery, or a bounded verified pairing session.
    """
    now = int(time.time()) if now is None else now
    safe_int(now, 1)
    rejected = False
    with Session(engine) as db, db.begin():
        global_bucket = db.scalar(
            select(Budget).where(Budget.id == "global").with_for_update()
        )
        events = [v for v in strict_loads(global_bucket.events) if v > now - 60]
        if len(events) >= 2400:
            rejected = True
        else:
            events.append(now)
        global_bucket.events = canonical_bytes(events)
        if proof is not None and not rejected:
            project = db.get(Project, proof.get("opaque_project_id"))
            device = proof.get("device_id")
            known = False
            if project:
                m = strict_loads(project.manifest)
                # Expiry is a clock transition, committed independently of an
                # expired request's rejected authorization and response cache.
                sessions = db.scalars(
                    select(PairSession).where(PairSession.project == project.id)
                ).all()
                for session in sessions:
                    if (
                        session.state in ("OPEN", "SUBMITTED")
                        and now >= strict_loads(session.challenge)["expires_at"]
                    ):
                        session.state = "EXPIRED"
                known = device == m["recovery_device_id"] or any(
                    v["device_id"] == device for v in m["members"]
                )
                if not known:
                    known = any(
                        strict_loads(s.challenge)["recipient"]["device_id"] == device
                        for s in sessions
                    )
            if known:
                identity = project.id + ":" + device
                bucket = db.get(Budget, identity)
                if bucket is None:
                    bucket = Budget(id=identity, events=b"[]")
                    db.add(bucket)
                events = [v for v in strict_loads(bucket.events) if v > now - 60]
                if len(events) >= 120:
                    rejected = True
                else:
                    events.append(now)
                bucket.events = canonical_bytes(events)
    if rejected:
        raise ValueError("RATE_LIMITED")


def authorize(db, project, proof, method, path, query, body, now):
    manifest = strict_loads(project.manifest)
    if any(
        proof[f] != manifest[f]
        for f in ("opaque_project_id", "membership_epoch", "key_epoch")
    ) or proof["manifest_digest"] != digest(manifest):
        raise ValueError("AUTH_REJECTED")
    if path == "/v1/membership/recovery" and method == "POST":
        if proof["device_id"] != manifest["recovery_device_id"]:
            raise ValueError("AUTH_REJECTED")
        public = manifest["recovery_signing_public_key"]
    elif path in ("/v1/pairing/challenge", "/v1/pairing/submit") and (
        method == "GET" or path.endswith("submit")
    ):
        parsed = strict_loads(body) if method == "POST" else query
        if type(parsed) is not dict:
            raise ValueError("AUTH_REJECTED")
        session_id = parsed.get("session_id")
        session = db.get(PairSession, (project.id, session_id))
        if session is None:
            raise ValueError("AUTH_REJECTED")
        challenge = strict_loads(session.challenge)
        # Any explicitly REVOKED member is ineligible for the pairing exception.
        member = next(
            (m for m in manifest["members"] if m["device_id"] == proof["device_id"]),
            None,
        )
        if member is not None and member["status"] == "REVOKED":
            raise ValueError("AUTH_REJECTED")
        verify_challenge(challenge, manifest, now)
        if method == "GET" and proof["device_id"] == challenge["authority_device_id"]:
            public = member_of(manifest, proof["device_id"], roles=("owner",))[
                "signing_public_key"
            ]
        elif proof["device_id"] == challenge["recipient"]["device_id"]:
            public = challenge["recipient"]["signing_public_key"]
        else:
            raise ValueError("AUTH_REJECTED")
    else:
        roles = (
            ("owner", "writer")
            if method == "POST" and path in ("/v1/messages", "/v1/chunks")
            else ("owner",)
            if method == "POST"
            and path
            in (
                "/v1/membership",
                "/v1/grants",
                "/v1/pairing/challenge",
                "/v1/pairing/complete",
            )
            else None
        )
        member = member_of(manifest, proof["device_id"], roles=roles)
        public = member["signing_public_key"]
    verify_request(proof, public, method, path, query, body, now)
    return manifest


def fault_barrier(point):
    """QA-only fixed Docker-exec marker barrier. No HTTP fault control."""
    if os.environ.get("HUB_RELAY_QA_FAULT_DIR") != "/fault":
        return
    directory = Path("/fault")
    arm = directory / "arm"
    if not arm.exists() or arm.read_text() != point:
        return
    arm.unlink()
    (directory / "reached").write_text(point)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if (directory / "release").exists():
            (directory / "release").unlink()
            return
        time.sleep(0.02)
    raise ValueError("TIMEOUT")


def execute(engine, proof, method, path, query, body, *, now=None):
    response = None
    with Session(engine) as db, db.begin():
        project = db.scalar(
            select(Project)
            .where(Project.id == proof["opaque_project_id"])
            .with_for_update()
        )
        # A request may cross its expiry while waiting on the project lock.
        now = int(time.time()) if now is None else now
        try:
            if project is None:
                raise ValueError("AUTH_REJECTED")
            manifest = authorize(db, project, proof, method, path, query, body, now)
        except (ValueError, TypeError, KeyError):
            raise ValueError("AUTH_REJECTED") from None
        if method == "POST" and path == "/v1/chunks":
            # Reject malformed numeric/schema types before allocating even an
            # error response receipt or changing any project quota/cache.
            validate_chunk_body(strict_loads(body))
        key = (project.id, proof["device_id"], proof["request_id"])
        existing = db.get(RequestReceipt, key)
        if existing:
            if existing.digest != digest(proof):
                raise ValueError("REQUEST_ID_COLLISION")
            if existing.response is None:
                raise ValueError("RECEIPT_UNAVAILABLE")
            return existing.response
        # Admission is before operation; no eviction of still-live or old UUIDs.
        if (
            project.cache_bytes + MAX_RESPONSE > MAX_CACHE
            or project.cache_count >= 4096
        ):
            raise ValueError("CACHE_FULL")
        try:
            with db.begin_nested():
                value = dispatch(
                    db,
                    project,
                    manifest,
                    proof,
                    method,
                    path,
                    query,
                    strict_loads(body) if body else {},
                    now,
                )
                response = canonical_bytes({"ok": True, "result": value})
                if len(response) > MAX_RESPONSE:
                    raise ValueError("REQUEST_TOO_LARGE")
                db.flush()
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            response = canonical_bytes({"ok": False, "code": error_code(exc)})
        project.cache_bytes += len(response)
        project.cache_count += 1
        db.add(
            RequestReceipt(
                project=key[0],
                device=key[1],
                id=key[2],
                digest=digest(proof),
                response=response,
            )
        )
        if method == "POST" and path == "/v1/messages":
            fault_barrier("before_commit")
    if method == "POST" and path == "/v1/messages":
        fault_barrier("after_commit")
    return response


def object_put(db, project, kind, id_, value):
    raw = canonical_bytes(value)
    existing = db.get(PublicObject, (project.id, kind, id_))
    if existing:
        if existing.body != raw:
            raise ValueError("OBJECT_COLLISION")
    else:
        count = db.scalar(
            select(func.count())
            .select_from(PublicObject)
            .where(PublicObject.project == project.id)
        )
        size = db.scalar(
            select(
                func.coalesce(func.sum(func.octet_length(PublicObject.body)), 0)
            ).where(PublicObject.project == project.id)
        )
        if count >= 4096 or size + len(raw) > MAX_CIPHER or len(raw) > 262144:
            raise ValueError("METADATA_QUOTA_EXCEEDED")
        db.add(PublicObject(project=project.id, kind=kind, id=id_, body=raw))
    return value


def object_get(db, project, kind, id_):
    row = db.get(PublicObject, (project.id, kind, id_))
    if row is None:
        raise ValueError("NOT_FOUND")
    return strict_loads(row.body)


def push_messages(db, project, manifest, device, body):
    fields(body, frozenset(("envelopes",)))
    values = body["envelopes"]
    if type(values) is not list or not 1 <= len(values) <= 16:
        raise ValueError("BATCH_LIMIT")
    results = []
    for envelope in values:
        raw = canonical_bytes(envelope)
        message_id = envelope.get("message_id")
        uuid(message_id)
        old = db.get(Message, (project.id, message_id))
        if old:
            if old.body != raw:
                raise ValueError("MESSAGE_ID_COLLISION")
            results.append(strict_loads(old.receipt))
            continue
        verify_active_envelope(envelope, manifest)
        if envelope["sender_device_id"] != device:
            raise ValueError("AUTH_REJECTED")
        if db.scalar(
            select(Message).where(
                Message.project == project.id,
                Message.key_epoch == envelope["key_epoch"],
                Message.nonce == envelope["nonce"],
            )
        ):
            raise ValueError("NONCE_REUSED")
        size = len(b64decode(envelope["ciphertext"]))
        if project.pending_bytes + size > MAX_CIPHER:
            raise ValueError("CIPHER_QUOTA_EXCEEDED")
        project.pending_bytes += size
        project.sequence += 1
        identity = digest(envelope)
        project.chain = extend_chain(
            project.chain,
            project.sequence - 1,
            [{"sequence": project.sequence, "envelope_digest": identity}],
        )
        receipt = {
            "stage": "RELAY_STORED",
            "message_id": message_id,
            "sequence": project.sequence,
            "envelope_digest": identity,
            "chain_digest": project.chain,
        }
        db.add(
            Message(
                project=project.id,
                id=message_id,
                body=raw,
                digest=identity,
                key_epoch=envelope["key_epoch"],
                nonce=envelope["nonce"],
                sequence=project.sequence,
                chain=project.chain,
                receipt=canonical_bytes(receipt),
            )
        )
        db.flush()
        results.append(receipt)
    return {"receipts": results}


def pull_messages(db, project, query):
    cursor = query["cursor"]
    if cursor > project.sequence:
        raise ValueError("CURSOR_GAP")
    previous = (
        "0" * 64
        if cursor == 0
        else db.scalar(
            select(Message.chain).where(
                Message.project == project.id, Message.sequence == cursor
            )
        )
    )
    if previous is None:
        raise ValueError("CURSOR_GAP")
    page = {
        "rows": [],
        "cursor": cursor,
        "chain_digest": previous,
        "has_more": cursor < project.sequence,
    }
    rows = db.scalars(
        select(Message)
        .where(Message.project == project.id, Message.sequence > cursor)
        .order_by(Message.sequence)
        .limit(query["limit"])
    ).all()
    for row in rows:
        entry = {
            "sequence": row.sequence,
            "envelope_digest": row.digest,
            "chain_digest": row.chain,
            "envelope": strict_loads(row.body),
        }
        candidate = {
            "rows": [*page["rows"], entry],
            "cursor": row.sequence,
            "chain_digest": row.chain,
            "has_more": row.sequence < project.sequence,
        }
        if len(canonical_bytes({"ok": True, "result": candidate})) > MAX_RESPONSE:
            break
        page = candidate
    return page


def membership_update(db, project, previous, candidate, *, recovery):
    if (candidate.get("operation") == "recovery") != recovery:
        raise ValueError("AUTH_REJECTED")
    verify_transition(previous, candidate, previous["recovery_signing_public_key"])
    if digest(candidate) == digest(previous):
        raise ValueError("MEMBERSHIP_CAS_MISMATCH")
    object_put(db, project, "manifest", digest(candidate), candidate)
    project.manifest = canonical_bytes(candidate)
    return {
        "manifest_digest": digest(candidate),
        "membership_epoch": candidate["membership_epoch"],
        "key_epoch": candidate["key_epoch"],
    }


def pairing_dispatch(db, project, manifest, proof, method, path, query, body, now):
    if method == "POST" and path == "/v1/pairing/challenge":
        fields(body, frozenset(("challenge",)))
        challenge = body["challenge"]
        verify_challenge(challenge, manifest, now)
        if challenge["authority_device_id"] != proof["device_id"]:
            raise ValueError("AUTH_REJECTED")
        old = db.get(PairSession, (project.id, challenge["session_id"]))
        if old:
            if old.challenge != canonical_bytes(challenge):
                raise ValueError("OBJECT_COLLISION")
            return {"state": old.state}
        if (
            db.scalar(
                select(func.count())
                .select_from(PairSession)
                .where(PairSession.project == project.id)
            )
            >= 128
        ):
            raise ValueError("METADATA_QUOTA_EXCEEDED")
        db.add(
            PairSession(
                project=project.id,
                id=challenge["session_id"],
                challenge=canonical_bytes(challenge),
            )
        )
        return {"state": "OPEN"}
    session_id = query.get("session_id") if method == "GET" else body.get("session_id")
    uuid(session_id)
    session = db.get(PairSession, (project.id, session_id))
    if session is None:
        raise ValueError("NOT_FOUND")
    challenge = strict_loads(session.challenge)
    if path == "/v1/pairing/receipt":
        if (
            session.state != "OWNER_COMPLETED"
            or session.receipt is None
            or proof["device_id"] != challenge["recipient"]["device_id"]
        ):
            raise ValueError("PAIRING_SCOPE_MISMATCH")
        receipt = strict_loads(session.receipt)
        if member_of(manifest, proof["device_id"]) != challenge["recipient"]:
            raise ValueError("PAIRING_SCOPE_MISMATCH")
        if receipt["manifest"]["key_epoch"] != manifest["key_epoch"]:
            raise ValueError("PAIRING_RETRY_STALE_EPOCH")
        return receipt
    verify_challenge(challenge, manifest, now)
    if path == "/v1/pairing/challenge" and method == "GET":
        return {
            "challenge": challenge,
            "state": session.state,
            "submissions": strict_loads(session.submissions),
        }
    if session.state == "OWNER_COMPLETED":
        raise ValueError("PAIRING_USED")
    if path == "/v1/pairing/submit":
        fields(body, frozenset(("session_id", "proof")))
        value = body["proof"]
        fields(
            value,
            frozenset(
                ("challenge_digest", "challenge_response", "confirmation", "signature")
            ),
        )
        hex_bytes(value["challenge_response"], 32)
        expected = {
            "fingerprint": challenge["recipient"]["fingerprint"],
            "opaque_project_id": project.id,
            "role": challenge["recipient"]["role"],
            "sas": challenge["sas"],
        }
        if (
            value["challenge_digest"] != digest(challenge)
            or value["confirmation"] != expected
        ):
            raise ValueError("PAIRING_SCOPE_MISMATCH")
        verify_signed(
            "PairingProof", value, challenge["recipient"]["signing_public_key"]
        )
        submissions = strict_loads(session.submissions)
        if value not in submissions:
            if len(submissions) >= 5:
                raise ValueError("PAIRING_ATTEMPTS_EXCEEDED")
            submissions.append(value)
            session.submissions = canonical_bytes(submissions)
        session.state = "SUBMITTED"
        return {
            "state": session.state,
            "attempts": len(submissions),
            "x25519_possession_verified": False,
        }
    fields(body, frozenset(("session_id", "receipt")))
    receipt = body["receipt"]
    fields(receipt, frozenset(("challenge_digest", "manifest", "grant")))
    candidate = receipt["manifest"]
    if (
        receipt["challenge_digest"] != digest(challenge)
        or session.state != "SUBMITTED"
        or member_of(candidate, challenge["recipient"]["device_id"])
        != challenge["recipient"]
        or candidate["operation"] != "grant"
        or candidate["authority_device_id"] != proof["device_id"]
    ):
        raise ValueError("PAIRING_SCOPE_MISMATCH")
    verify_grant(receipt["grant"], candidate)
    if (
        receipt["grant"]["context"]["session_id"] != session.id
        or receipt["grant"]["context"]["recipient_device_id"]
        != challenge["recipient"]["device_id"]
    ):
        raise ValueError("PAIRING_SCOPE_MISMATCH")
    membership_update(db, project, manifest, candidate, recovery=False)
    object_put(db, project, "grant", session.id, receipt["grant"])
    session.receipt = canonical_bytes(receipt)
    session.state = "OWNER_COMPLETED"
    return {"state": session.state, "manifest_digest": digest(candidate)}


def validate_chunk_body(body):
    fields(
        body,
        frozenset(
            (
                "opaque_project_id",
                "opaque_locator",
                "key_epoch",
                "index",
                "total",
                "size",
                "manifest_identity",
                "nonce",
                "ciphertext",
            )
        ),
    )
    uuid(body["opaque_project_id"])
    uuid(body["opaque_locator"])
    safe_int(body["key_epoch"], 1)
    safe_int(body["index"], 0, 15)
    safe_int(body["total"], 1, 16)
    safe_int(body["size"], 1, 65536)
    hex_bytes(body["manifest_identity"], 32)
    nonce = hex_bytes(body["nonce"], 12)
    cipher = b64decode(body["ciphertext"])
    return nonce, cipher


def chunk_dispatch(db, project, manifest, proof, method, query, body):
    if method == "GET":
        chunk = db.get(Chunk, (project.id, query["opaque_locator"], query["index"]))
        if chunk is None:
            raise ValueError("NOT_FOUND")
        return strict_loads(chunk.body)
    nonce, cipher = validate_chunk_body(body)
    if (
        body["opaque_project_id"] != project.id
        or body["key_epoch"] != manifest["key_epoch"]
        or body["index"] >= body["total"]
        or len(cipher) != body["size"] + 16
        or len(cipher) > 65552
    ):
        raise ValueError("CHUNK_BINDING_MISMATCH")
    member = member_of(manifest, proof["device_id"], roles=("owner", "writer"))
    if (
        int.from_bytes(nonce[:4], "big") != member["nonce_prefix"]
        or not 1 <= int.from_bytes(nonce[4:], "big") <= 9007199254740991
    ):
        raise ValueError("NONCE_BINDING_MISMATCH")
    key = (project.id, body["opaque_locator"], body["index"])
    old = db.get(Chunk, key)
    if old:
        if old.body != canonical_bytes(body):
            raise ValueError("OBJECT_COLLISION")
        return strict_loads(old.receipt)
    siblings = db.scalars(
        select(Chunk).where(
            Chunk.project == project.id, Chunk.locator == body["opaque_locator"]
        )
    ).all()
    for sibling in siblings:
        other = strict_loads(sibling.body)
        if (
            any(
                body[f] != other[f] for f in ("manifest_identity", "key_epoch", "total")
            )
            or sibling.nonce == body["nonce"]
        ):
            raise ValueError("CHUNK_BINDING_MISMATCH")
    if project.pending_bytes + len(cipher) > MAX_CIPHER:
        raise ValueError("CIPHER_QUOTA_EXCEEDED")
    project.pending_bytes += len(cipher)
    receipt = {
        "stage": "RELAY_STORED",
        "opaque_locator": body["opaque_locator"],
        "index": body["index"],
        "chunk_digest": digest(body),
    }
    db.add(
        Chunk(
            project=key[0],
            locator=key[1],
            index=key[2],
            body=canonical_bytes(body),
            receipt=canonical_bytes(receipt),
            manifest_identity=body["manifest_identity"],
            nonce=body["nonce"],
        )
    )
    return receipt


def dispatch(db, project, manifest, proof, method, path, query, body, now):
    device = proof["device_id"]
    if path == "/v1/hello":
        fields(body, frozenset())
        return {
            "audience": "ResearchHub/SecureRelay/QA/v1",
            "transaction_version_pairs": [list(pair) for pair in TRANSACTION_VERSION_PAIRS],
            "manifest_digest": digest(manifest),
            "sequence": project.sequence,
        }
    if path == "/v1/messages":
        return (
            push_messages(db, project, manifest, device, body)
            if method == "POST"
            else pull_messages(db, project, query)
        )
    if path == "/v1/membership" and method == "GET":
        return manifest
    if path == "/v1/membership/receipt":
        candidate = object_get(db, project, "manifest", query["candidate_digest"])
        return {
            "manifest_digest": digest(candidate),
            "membership_epoch": candidate["membership_epoch"],
            "key_epoch": candidate["key_epoch"],
        }
    if path in ("/v1/membership", "/v1/membership/recovery"):
        fields(body, frozenset(("manifest",)))
        candidate = body["manifest"]
        if path == "/v1/membership" and candidate.get("authority_device_id") != device:
            raise ValueError("AUTH_REJECTED")
        return membership_update(
            db, project, manifest, candidate, recovery=path.endswith("recovery")
        )
    if path.startswith("/v1/pairing/"):
        return pairing_dispatch(
            db, project, manifest, proof, method, path, query, body, now
        )
    if path == "/v1/grants":
        if method == "GET":
            value = object_get(db, project, "grant", query["session_id"])
            if (
                value["context"]["recipient_device_id"] != device
                or value["context"]["key_epoch"] != manifest["key_epoch"]
            ):
                raise ValueError("AUTH_REJECTED")
            return value
        fields(body, frozenset(("grant",)))
        grant = body["grant"]
        verify_grant(grant, manifest)
        if grant["authority_device_id"] != device:
            raise ValueError("AUTH_REJECTED")
        return object_put(db, project, "grant", grant["context"]["session_id"], grant)
    if path == "/v1/ack":
        fields(
            body,
            frozenset(
                (
                    "version",
                    "opaque_project_id",
                    "device_id",
                    "message_id",
                    "sequence",
                    "stage",
                    "retain_until_ack",
                    "signature",
                )
            ),
        )
        safe_int(body["version"], 1, 1)
        safe_int(body["sequence"], 1)
        if (
            type(body["retain_until_ack"]) is not bool
            or body["stage"] not in STAGES
            or body["device_id"] != device
            or body["opaque_project_id"] != project.id
        ):
            raise ValueError("ACK_BINDING_MISMATCH")
        message = db.get(Message, (project.id, body["message_id"]))
        if message is None or message.sequence != body["sequence"]:
            raise ValueError("ACK_BINDING_MISMATCH")
        verify_signed(
            "RelayAck", body, member_of(manifest, device)["signing_public_key"]
        )
        return object_put(
            db,
            project,
            "ack",
            digest({k: body[k] for k in ("device_id", "message_id", "stage")}),
            body,
        )
    if path == "/v1/checkpoints":
        if method == "GET":
            rows = db.scalars(
                select(PublicObject)
                .where(
                    PublicObject.project == project.id,
                    PublicObject.kind == "checkpoint",
                )
                .order_by(PublicObject.id)
                .limit(100)
            ).all()
            return {"checkpoints": [strict_loads(r.body) for r in rows]}
        fields(body, frozenset(("checkpoint",)))
        value = body["checkpoint"]
        verify_checkpoint(value, manifest)
        if value["creator_device_id"] != device:
            raise ValueError("AUTH_REJECTED")
        chain = (
            "0" * 64
            if value["cursor"] == 0
            else db.scalar(
                select(Message.chain).where(
                    Message.project == project.id, Message.sequence == value["cursor"]
                )
            )
        )
        if chain != value["chain_digest"]:
            raise ValueError("CURSOR_GAP")
        return object_put(db, project, "checkpoint", digest(value), value)
    if path == "/v1/chunks":
        return chunk_dispatch(db, project, manifest, proof, method, query, body)
    raise ValueError("INVALID_REQUEST")
