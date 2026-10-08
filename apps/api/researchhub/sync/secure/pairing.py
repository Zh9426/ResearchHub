"""TEST ONLY trusted pairing: text confirmation, dual possession and durable CAS."""

import hashlib
import os
from uuid import uuid4

from packages.secure_wire.canonical import canonical_bytes, digest, strict_loads
from packages.secure_wire.envelope import b64decode, b64encode, hex_bytes
from packages.secure_wire.membership import (
    challenge_sas,
    fields,
    member_of,
    preimage,
    verify_challenge,
    verify_signed,
)

from .crypto import sign, unwrap_key, wrap_key
from .keys import grant_context, make_grant, signed_object, transition

PROOF_FIELDS = frozenset(
    ["challenge_digest", "challenge_response", "confirmation", "signature"]
)


def confirmation(challenge):
    r = challenge["recipient"]
    return {
        "fingerprint": r["fingerprint"],
        "opaque_project_id": challenge["opaque_project_id"],
        "role": r["role"],
        "sas": challenge["sas"],
    }


def create_challenge(store, owner, recipient, *, now, project=None):
    if project is None:
        with store.transaction() as db:
            projects = db.execute("SELECT project FROM roots").fetchall()
        if len(projects) != 1:
            raise ValueError("PROJECT_SELECTION_REQUIRED")
        project = projects[0][0]
    manifest = store.verified_current(project)
    authority = member_of(manifest, owner.device_id, roles=("owner",))
    if authority["signing_public_key"] != owner.signing_public:
        raise ValueError("DEVICE_KEY_MISMATCH")
    session = str(uuid4())
    response = os.urandom(32)
    context = grant_context(manifest, recipient, session)
    challenge = {
        "version": 1,
        "session_id": session,
        "opaque_project_id": project,
        "manifest_digest": digest(manifest),
        "membership_epoch": manifest["membership_epoch"],
        "key_epoch": manifest["key_epoch"],
        "authority_device_id": owner.device_id,
        "recipient": recipient,
        "issued_at": now,
        "expires_at": now + 300,
        "wrapped_challenge": b64encode(
            wrap_key(
                bytes.fromhex(recipient["recipient_public_key"]), response, context
            )
        ),
    }
    challenge["sas"] = challenge_sas(challenge)
    challenge = signed_object("PairingChallenge", challenge, owner.signing_seed)
    verify_challenge(challenge, manifest, now)
    with store.transaction() as db:
        if digest(store.verified_current(project, db=db)) != digest(manifest):
            raise ValueError("MEMBERSHIP_CAS_MISMATCH")
        db.execute(
            "INSERT INTO challenges(session,body,response_digest) VALUES (?,?,?)",
            (session, canonical_bytes(challenge), hashlib.sha256(response).hexdigest()),
        )
    return challenge


def answer_challenge(challenge, pinned_manifest, device, *, confirmation, now):
    verify_challenge(challenge, pinned_manifest, now)
    target = challenge["recipient"]
    if confirmation != globals()["confirmation"](challenge):
        raise ValueError("PAIRING_CONFIRMATION_MISMATCH")
    if (
        target["device_id"] != device.device_id
        or target["signing_public_key"] != device.signing_public
        or target["recipient_public_key"] != device.recipient_public
    ):
        raise ValueError("RECIPIENT_MISMATCH")
    response = unwrap_key(
        device.recipient_seed,
        b64decode(challenge["wrapped_challenge"], 80),
        grant_context(pinned_manifest, target, challenge["session_id"]),
    )
    proof = {
        "challenge_digest": digest(challenge),
        "challenge_response": response.hex(),
        "confirmation": confirmation,
    }
    proof["signature"] = b64encode(
        sign(device.signing_seed, preimage("PairingProof", proof))
    )
    return proof


def consume(store, owner, challenge, proof, key, *, now, crash_point=None):
    failure = None
    result = None
    with store.transaction() as db:
        row = db.execute(
            "SELECT body,response_digest,attempts,used FROM challenges WHERE session=?",
            (challenge.get("session_id"),),
        ).fetchone()
        if row is None or row[0] != canonical_bytes(challenge):
            raise ValueError("PAIRING_SCOPE_MISMATCH")
        if row[3]:
            raise ValueError("PAIRING_USED")
        if row[2] >= 5:
            raise ValueError("PAIRING_ATTEMPTS_EXCEEDED")
        manifest = store.verified_current(challenge["opaque_project_id"], db=db)
        db.execute(
            "UPDATE challenges SET attempts=attempts+1 WHERE session=?",
            (challenge["session_id"],),
        )
        try:
            verify_challenge(challenge, manifest, now)
            fields(proof, PROOF_FIELDS)
            response = hex_bytes(proof["challenge_response"], 32)
            if (
                proof["challenge_digest"] != digest(challenge)
                or proof["confirmation"] != confirmation(challenge)
                or hashlib.sha256(response).hexdigest() != row[1]
            ):
                raise ValueError("PAIRING_PROOF_INVALID")
            verify_signed(
                "PairingProof", proof, challenge["recipient"]["signing_public_key"]
            )
            recipient = challenge["recipient"]
            existing = next(
                (
                    m
                    for m in manifest["members"]
                    if m["device_id"] == recipient["device_id"]
                ),
                None,
            )
            if existing is None:
                new = transition(manifest, owner, add=recipient, now=now)
            else:
                # Activation may change only status, never pinned identity or scope.
                if existing["status"] != "PENDING" or recipient != {
                    **existing,
                    "status": "ACTIVE",
                }:
                    raise ValueError("PAIRING_SCOPE_MISMATCH")
                new = transition(
                    manifest, owner, activate=recipient["device_id"], now=now
                )
            grant = make_grant(
                new,
                owner,
                challenge["recipient"]["device_id"],
                challenge["session_id"],
                key,
            )
            result = {
                "challenge_digest": digest(challenge),
                "manifest": new,
                "grant": grant,
            }
        except ValueError as exc:
            failure = exc
        if failure is None:
            # Persistence errors must escape the transaction, never commit a
            # partially written activation as a mere failed proof attempt.
            store.accept(new, db=db)
            db.execute(
                "UPDATE challenges SET used=1,receipt=? WHERE session=?",
                (canonical_bytes(result), challenge["session_id"]),
            )
            if crash_point == "before_commit":
                raise RuntimeError("SYNTHETIC_CRASH_BEFORE_COMMIT")
    if failure is not None:
        raise failure
    if crash_point == "after_commit":
        raise RuntimeError("SYNTHETIC_CRASH_AFTER_COMMIT")
    return result


def retry_receipt(store, challenge, recipient_device_id):
    """Explicit immutable lookup; never a second consume or activation."""
    with store.transaction() as db:
        row = db.execute(
            "SELECT body,used,receipt FROM challenges WHERE session=?",
            (challenge.get("session_id"),),
        ).fetchone()
        if (
            row is None
            or row[0] != canonical_bytes(challenge)
            or not row[1]
            or recipient_device_id != challenge["recipient"]["device_id"]
        ):
            raise ValueError("PAIRING_RETRY_SCOPE_MISMATCH")
        current = store.verified_current(challenge["opaque_project_id"], db=db)
        member = member_of(current, recipient_device_id)
        if member != challenge["recipient"]:
            raise ValueError("PAIRING_RETRY_SCOPE_MISMATCH")
        receipt = strict_loads(row[2])
        if current["key_epoch"] != receipt["manifest"]["key_epoch"]:
            raise ValueError("PAIRING_RETRY_STALE_EPOCH")
        return receipt
