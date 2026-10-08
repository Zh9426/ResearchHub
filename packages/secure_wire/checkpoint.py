"""PUBLIC checkpoint/schema/signature/chain verification; no client crypto."""

from .canonical import digest
from .envelope import b64decode, hex_bytes, safe_int, uuid
from .membership import fields, member_of, verify_signed

CHECKPOINT_FIELDS = frozenset(
    [
        "version",
        "opaque_project_id",
        "membership_epoch",
        "key_epoch",
        "cursor",
        "chain_digest",
        "creator_device_id",
        "signature",
    ]
)


def extend_chain(previous_digest, cursor, rows):
    hex_bytes(previous_digest, 32)
    safe_int(cursor)
    if cursor == 0 and previous_digest != "0" * 64:
        raise ValueError("INVALID_GENESIS_CHAIN")
    if type(rows) is not list or len(rows) > 100:
        raise ValueError("INVALID_CHECKPOINT_PAGE")
    chain = previous_digest
    for row in rows:
        fields(row, frozenset(("sequence", "envelope_digest")))
        safe_int(row["sequence"], 1)
        hex_bytes(row["envelope_digest"], 32)
        if row["sequence"] != cursor + 1:
            raise ValueError("CURSOR_GAP")
        chain = digest({"previous_digest": chain, **row})
        cursor += 1
    return chain


def validate_anchor(checkpoint, *, bootstrap=False):
    """Shape validation only: signed anchors must already be locally authenticated.

    A three-field anchor is allowed only at an explicitly trusted pin boundary.
    Missing signed fields never implicitly grant that capability.
    """
    if type(bootstrap) is not bool:
        raise ValueError("INVALID_CHECKPOINT_KIND")
    fields(
        checkpoint,
        frozenset(("opaque_project_id", "cursor", "chain_digest"))
        if bootstrap
        else CHECKPOINT_FIELDS,
    )
    safe_int(checkpoint["cursor"])
    uuid(checkpoint["opaque_project_id"])
    hex_bytes(checkpoint["chain_digest"], 32)
    if checkpoint["cursor"] == 0 and checkpoint["chain_digest"] != "0" * 64:
        raise ValueError("INVALID_GENESIS_CHAIN")
    if not bootstrap:
        safe_int(checkpoint["version"], 1, 1)
        safe_int(checkpoint["membership_epoch"], 1)
        safe_int(checkpoint["key_epoch"], 1)
        uuid(checkpoint["creator_device_id"])
        b64decode(checkpoint["signature"], 64)
    return checkpoint


def verify_checkpoint(checkpoint, manifest):
    validate_anchor(checkpoint)
    if any(
        checkpoint[f] != manifest[f]
        for f in ("opaque_project_id", "membership_epoch", "key_epoch")
    ):
        raise ValueError("CHECKPOINT_BINDING_MISMATCH")
    creator = member_of(manifest, checkpoint["creator_device_id"])
    verify_signed("Checkpoint", checkpoint, creator["signing_public_key"])
    return checkpoint


def verify_advance(anchor, checkpoint, manifest, rows, *, bootstrap=False):
    validate_anchor(anchor, bootstrap=bootstrap)
    verify_checkpoint(checkpoint, manifest)
    if anchor["opaque_project_id"] != checkpoint["opaque_project_id"]:
        raise ValueError("CHECKPOINT_BINDING_MISMATCH")
    if not bootstrap and any(
        checkpoint[f] < anchor[f] for f in ("membership_epoch", "key_epoch")
    ):
        raise ValueError("ROLLBACK_DETECTED")
    if checkpoint["cursor"] < anchor["cursor"] or (
        checkpoint["cursor"] == anchor["cursor"]
        and checkpoint["chain_digest"] != anchor["chain_digest"]
    ):
        raise ValueError("ROLLBACK_DETECTED")
    if checkpoint["cursor"] != anchor["cursor"] + len(rows):
        raise ValueError("CURSOR_GAP")
    chain = extend_chain(anchor["chain_digest"], anchor["cursor"], rows)
    if chain != checkpoint["chain_digest"]:
        raise ValueError("CHAIN_DIGEST_MISMATCH")
    return checkpoint
