"""PUBLIC verification only: canonical objects, pinned keys and Ed25519 public keys.

No Domain, client, private-key, wrapping, or AEAD dependency. Suitable for Relay.
"""

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import canonical_bytes, digest
from .envelope import (
    b64decode,
    hex_bytes,
    safe_int,
    uuid,
    validate_envelope,
    verify_envelope,
)

ZERO = "0" * 64
MEMBER_FIELDS = frozenset(
    [
        "device_id",
        "signing_public_key",
        "recipient_public_key",
        "fingerprint",
        "role",
        "status",
        "nonce_prefix",
        "granted_at",
        "revoked_at",
    ]
)
MANIFEST_FIELDS = frozenset(
    [
        "version",
        "opaque_project_id",
        "membership_epoch",
        "key_epoch",
        "previous_digest",
        "operation",
        "authority_device_id",
        "recovery_device_id",
        "recovery_signing_public_key",
        "recovery_recipient_public_key",
        "members",
        "signature",
    ]
)
GRANT_FIELDS = frozenset(
    [
        "version",
        "authority_device_id",
        "context",
        "role",
        "manifest_digest",
        "wrapped_key",
        "signature",
    ]
)
CONTEXT_FIELDS = frozenset(
    [
        "opaque_project_id",
        "recipient_device_id",
        "key_epoch",
        "membership_epoch",
        "session_id",
        "recipient_signing_public_key",
        "recipient_public_key",
    ]
)
CHALLENGE_FIELDS = frozenset(
    [
        "version",
        "session_id",
        "opaque_project_id",
        "manifest_digest",
        "membership_epoch",
        "key_epoch",
        "authority_device_id",
        "recipient",
        "issued_at",
        "expires_at",
        "wrapped_challenge",
        "sas",
        "signature",
    ]
)


def fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        raise ValueError("INVALID_SIGNED_OBJECT")
    canonical_bytes(value)


def preimage(kind, value):
    return ("ResearchHub/" + kind + "/v1\0").encode() + canonical_bytes(
        {k: v for k, v in value.items() if k != "signature"}
    )


def verify_signed(kind, value, public):
    try:
        Ed25519PublicKey.from_public_bytes(hex_bytes(public, 32)).verify(
            b64decode(value["signature"], 64), preimage(kind, value)
        )
    except (ValueError, InvalidSignature):
        raise ValueError("INVALID_SIGNATURE") from None


def fingerprint(signing_public, recipient_public):
    hex_bytes(signing_public, 32)
    hex_bytes(recipient_public, 32)
    return digest(
        {"signing_public_key": signing_public, "recipient_public_key": recipient_public}
    )


def validate_member(member):
    fields(member, MEMBER_FIELDS)
    uuid(member["device_id"])
    if member["fingerprint"] != fingerprint(
        member["signing_public_key"], member["recipient_public_key"]
    ):
        raise ValueError("FINGERPRINT_MISMATCH")
    if member["role"] not in ("owner", "writer", "reader") or member["status"] not in (
        "PENDING",
        "ACTIVE",
        "REVOKED",
    ):
        raise ValueError("INVALID_MEMBERSHIP")
    safe_int(member["nonce_prefix"], 0, 4294967295)
    safe_int(member["granted_at"])
    if member["status"] == "REVOKED":
        safe_int(member["revoked_at"], member["granted_at"])
    elif member["revoked_at"] is not None:
        raise ValueError("INVALID_MEMBERSHIP")
    return member


def validate_manifest(manifest):
    fields(manifest, MANIFEST_FIELDS)
    safe_int(manifest["version"], 1, 1)
    uuid(manifest["opaque_project_id"])
    uuid(manifest["authority_device_id"])
    for key in ("membership_epoch", "key_epoch"):
        safe_int(manifest[key], 1)
    hex_bytes(manifest["previous_digest"], 32)
    hex_bytes(manifest["recovery_signing_public_key"], 32)
    hex_bytes(manifest["recovery_recipient_public_key"], 32)
    uuid(manifest["recovery_device_id"])
    b64decode(manifest["signature"], 64)
    if manifest["operation"] not in ("bootstrap", "grant", "revoke", "recovery"):
        raise ValueError("INVALID_MEMBERSHIP")
    members = manifest["members"]
    if type(members) is not list or not 1 <= len(members) <= 1024:
        raise ValueError("INVALID_MEMBERSHIP")
    for m in members:
        validate_member(m)
    if len({m["device_id"] for m in members}) != len(members) or len(
        {m["nonce_prefix"] for m in members}
    ) != len(members):
        raise ValueError("PREFIX_OR_DEVICE_COLLISION")
    if not any(m["status"] == "ACTIVE" and m["role"] == "owner" for m in members):
        raise ValueError("NO_ACTIVE_OWNER")
    return manifest


def member_of(manifest, device_id, *, roles=None):
    member = next((m for m in manifest["members"] if m["device_id"] == device_id), None)
    if member is None:
        raise ValueError("UNKNOWN_DEVICE")
    if member["status"] == "REVOKED":
        raise ValueError("REVOKED_DEVICE")
    if member["status"] != "ACTIVE" or (
        roles is not None and member["role"] not in roles
    ):
        raise ValueError("UNAUTHORIZED_DEVICE")
    return member


def verify_bootstrap(manifest, owner_public, recovery_public):
    validate_manifest(manifest)
    owner = member_of(manifest, manifest["authority_device_id"], roles=("owner",))
    if (
        manifest["operation"] != "bootstrap"
        or manifest["previous_digest"] != ZERO
        or manifest["membership_epoch"] != 1
        or manifest["key_epoch"] != 1
        or len(manifest["members"]) != 1
        or owner["signing_public_key"] != owner_public
        or manifest["recovery_signing_public_key"] != recovery_public
    ):
        raise ValueError("UNTRUSTED_BOOTSTRAP")
    verify_signed("Membership", manifest, owner_public)
    return manifest


def verify_transition(previous, candidate, recovery_public):
    """previous must already be locally pinned/verified; candidate cannot self-authorize."""
    validate_manifest(previous)
    validate_manifest(candidate)
    if candidate["membership_epoch"] == previous["membership_epoch"]:
        if digest(candidate) == digest(previous):
            return previous
        raise ValueError("MEMBERSHIP_FORK")
    if (
        candidate["opaque_project_id"] != previous["opaque_project_id"]
        or candidate["previous_digest"] != digest(previous)
        or candidate["membership_epoch"] != previous["membership_epoch"] + 1
    ):
        raise ValueError("MEMBERSHIP_CAS_MISMATCH")
    op = candidate["operation"]
    if op not in ("grant", "revoke", "recovery") or candidate["key_epoch"] != previous[
        "key_epoch"
    ] + (op in ("revoke", "recovery")):
        raise ValueError("EPOCH_TRANSITION_INVALID")
    if previous["recovery_signing_public_key"] != recovery_public or any(
        candidate[f] != previous[f]
        for f in (
            "recovery_signing_public_key",
            "recovery_recipient_public_key",
            "recovery_device_id",
        )
    ):
        raise ValueError("UNTRUSTED_RECOVERY_ROOT")
    if op == "recovery":
        verify_signed("Membership", candidate, recovery_public)
    else:
        authority = member_of(
            previous, candidate["authority_device_id"], roles=("owner",)
        )
        verify_signed("Membership", candidate, authority["signing_public_key"])
    old = {m["device_id"]: m for m in previous["members"]}
    new = {m["device_id"]: m for m in candidate["members"]}
    if not old.keys() <= new.keys():
        raise ValueError("MEMBERSHIP_HISTORY_REMOVED")
    changed, added = [], [m for id_, m in new.items() if id_ not in old]
    for id_, m in old.items():
        n = new[id_]
        for f in MEMBER_FIELDS - {"status", "revoked_at"}:
            if m[f] != n[f]:
                raise ValueError("MEMBERSHIP_IDENTITY_CHANGED")
        if m["status"] == "REVOKED" and n != m:
            raise ValueError("REVOKED_DEVICE")
        if m != n:
            changed.append((m, n))
    if added and min(m["nonce_prefix"] for m in added) <= max(
        m["nonce_prefix"] for m in old.values()
    ):
        raise ValueError("PREFIX_HISTORY_REUSED")
    if op == "grant" and (
        len(added) + len(changed) != 1
        or any(m["status"] not in ("PENDING", "ACTIVE") for m in added)
        or any(m["status"] != "PENDING" or n["status"] != "ACTIVE" for m, n in changed)
    ):
        raise ValueError("INVALID_GRANT_TRANSITION")
    if op == "revoke" and (
        added
        or not changed
        or any(
            m["status"] not in ("PENDING", "ACTIVE") or n["status"] != "REVOKED"
            for m, n in changed
        )
    ):
        raise ValueError("INVALID_REVOKE_TRANSITION")
    if op == "recovery" and (
        len(added) != 1
        or added[0]["status"] != "ACTIVE"
        or added[0]["role"] != "owner"
        or candidate["authority_device_id"] != added[0]["device_id"]
        or any(new[id_]["status"] != "REVOKED" for id_ in old)
    ):
        raise ValueError("INVALID_RECOVERY_TRANSITION")
    return candidate


def validate_context(context):
    fields(context, CONTEXT_FIELDS)
    for f in ("opaque_project_id", "recipient_device_id", "session_id"):
        uuid(context[f])
    for f in ("key_epoch", "membership_epoch"):
        safe_int(context[f], 1)
    for f in ("recipient_signing_public_key", "recipient_public_key"):
        hex_bytes(context[f], 32)


def verify_grant(grant, manifest):
    fields(grant, GRANT_FIELDS)
    safe_int(grant["version"], 1, 1)
    validate_context(grant["context"])
    c = grant["context"]
    target = member_of(manifest, c["recipient_device_id"])
    if (
        grant["manifest_digest"] != digest(manifest)
        or c["opaque_project_id"] != manifest["opaque_project_id"]
        or any(c[f] != manifest[f] for f in ("key_epoch", "membership_epoch"))
        or c["recipient_signing_public_key"] != target["signing_public_key"]
        or c["recipient_public_key"] != target["recipient_public_key"]
        or grant["role"] != target["role"]
    ):
        raise ValueError("GRANT_BINDING_MISMATCH")
    authority = member_of(manifest, grant["authority_device_id"], roles=("owner",))
    b64decode(grant["wrapped_key"], 80)
    verify_signed("ProjectGrant", grant, authority["signing_public_key"])
    return grant


def challenge_sas(challenge):
    return digest(
        {k: v for k, v in challenge.items() if k not in ("signature", "sas")}
    )[:12]


def verify_challenge(challenge, manifest, now):
    fields(challenge, CHALLENGE_FIELDS)
    safe_int(challenge["version"], 1, 1)
    safe_int(challenge["membership_epoch"], 1)
    safe_int(challenge["key_epoch"], 1)
    uuid(challenge["session_id"])
    validate_member(challenge["recipient"])
    safe_int(challenge["issued_at"])
    safe_int(challenge["expires_at"])
    safe_int(now)
    if (
        challenge["expires_at"] != challenge["issued_at"] + 300
        or not challenge["issued_at"] <= now < challenge["expires_at"]
    ):
        raise ValueError("PAIRING_EXPIRED")
    if (
        challenge["recipient"]["status"] != "ACTIVE"
        or challenge["sas"] != challenge_sas(challenge)
        or challenge["manifest_digest"] != digest(manifest)
        or any(
            challenge[f] != manifest[f]
            for f in ("opaque_project_id", "membership_epoch", "key_epoch")
        )
    ):
        raise ValueError("PAIRING_SCOPE_MISMATCH")
    authority = member_of(manifest, challenge["authority_device_id"], roles=("owner",))
    b64decode(challenge["wrapped_challenge"], 80)
    verify_signed("PairingChallenge", challenge, authority["signing_public_key"])
    return challenge


def verify_active_envelope(envelope, manifest, *, mutation=True):
    validate_envelope(envelope)
    if any(
        envelope[f] != manifest[f]
        for f in ("opaque_project_id", "membership_epoch", "key_epoch")
    ):
        raise ValueError("STALE_MEMBERSHIP_OR_KEY_EPOCH")
    member = member_of(
        manifest,
        envelope["sender_device_id"],
        roles=("owner", "writer") if mutation else None,
    )
    verify_envelope(envelope, bytes.fromhex(member["signing_public_key"]))
    nonce = bytes.fromhex(envelope["nonce"])
    if (
        int.from_bytes(nonce[:4], "big") != member["nonce_prefix"]
        or not 1 <= int.from_bytes(nonce[4:], "big") <= 9007199254740991
    ):
        raise ValueError("NONCE_BINDING_MISMATCH")
    return envelope


def verify_historical_envelope(envelope, historical_manifest, current_manifest):
    """Both manifests MUST come from locally pinned continuous history."""
    validate_envelope(envelope)
    if (
        historical_manifest["opaque_project_id"]
        != current_manifest["opaque_project_id"]
        or historical_manifest["membership_epoch"]
        >= current_manifest["membership_epoch"]
        or historical_manifest["key_epoch"] > current_manifest["key_epoch"]
    ):
        raise ValueError("UNPINNED_MEMBERSHIP_HISTORY")
    verify_active_envelope(envelope, historical_manifest)
    return {
        "status": "QUARANTINED",
        "reason": "HISTORICAL_EPOCH",
        "envelope_digest": digest(envelope),
    }
