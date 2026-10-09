"""Pure public envelope validation; deliberately no private-key or AEAD imports."""

import base64
import hashlib
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import SAFE_INTEGER, canonical_bytes, strict_loads

SUITE = "RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM"
TRANSACTION_VERSION_PAIRS = ((1, 1), (2, 2))
MAX_ENVELOPE = 256 * 1024
HEADER_FIELDS = frozenset(
    [
        "envelope_version",
        "crypto_suite",
        "protocol_version",
        "schema_version",
        "record_type",
        "opaque_project_id",
        "sender_device_id",
        "membership_epoch",
        "key_epoch",
        "message_id",
        "semantic_transaction_digest",
        "dependencies",
        "nonce",
        "checkpoint_sequence",
    ]
)
ENVELOPE_FIELDS = HEADER_FIELDS | {"ciphertext", "ciphertext_digest", "signature"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def uuid(value):
    if (
        type(value) is not str
        or not UUID.fullmatch(value)
        or value == "00000000-0000-0000-0000-000000000000"
    ):
        raise ValueError("INVALID_ENVELOPE")


def safe_int(value, minimum=0, maximum=SAFE_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("INVALID_ENVELOPE")


def hex_bytes(value, size):
    if type(value) is not str or not re.fullmatch(
        "[0-9a-f]{" + str(size * 2) + "}", value
    ):
        raise ValueError("INVALID_ENVELOPE")
    return bytes.fromhex(value)


def b64encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64decode(value, size=None):
    if type(value) is not str or not re.fullmatch("[A-Za-z0-9_-]*", value):
        raise ValueError("INVALID_ENVELOPE")
    try:
        raw = base64.b64decode(
            value + "=" * ((-len(value)) % 4), altchars=b"-_", validate=True
        )
    except ValueError:
        raise ValueError("INVALID_ENVELOPE") from None
    if b64encode(raw) != value or (size is not None and len(raw) != size):
        raise ValueError("INVALID_ENVELOPE")
    return raw


def validate_header(header):
    if type(header) is not dict or set(header) != HEADER_FIELDS:
        raise ValueError("INVALID_ENVELOPE")
    safe_int(header["envelope_version"], 1, 1)
    for f in ("protocol_version", "schema_version"):
        safe_int(header[f], 1, 2)
    versions = TRANSACTION_VERSION_PAIRS if header["record_type"] == "transaction" else ((1, 1),)
    if (header["protocol_version"], header["schema_version"]) not in versions:
        raise ValueError("UPGRADE_REQUIRED")
    if header["crypto_suite"] != SUITE or header["record_type"] not in (
        "transaction",
        "snapshot",
        "artifact_manifest",
    ):
        raise ValueError("UNSUPPORTED_SUITE")
    for f in ("opaque_project_id", "sender_device_id", "message_id"):
        uuid(header[f])
    for f in ("membership_epoch", "key_epoch"):
        safe_int(header[f], 1)
    safe_int(header["checkpoint_sequence"])
    hex_bytes(header["semantic_transaction_digest"], 32)
    hex_bytes(header["nonce"], 12)
    deps = header["dependencies"]
    if type(deps) is not list or len(deps) > 100:
        raise ValueError("INVALID_ENVELOPE")
    for dep in deps:
        uuid(dep)
    if deps != sorted(set(deps)):
        raise ValueError("INVALID_ENVELOPE")
    canonical_bytes(header)
    return header


def header_of(envelope):
    return {key: envelope[key] for key in HEADER_FIELDS}


def validate_envelope(envelope):
    if type(envelope) is not dict or set(envelope) != ENVELOPE_FIELDS:
        raise ValueError("INVALID_ENVELOPE")
    if len(canonical_bytes(envelope)) > MAX_ENVELOPE:
        raise ValueError("MESSAGE_TOO_LARGE")
    validate_header(header_of(envelope))
    ciphertext = b64decode(envelope["ciphertext"])
    if len(ciphertext) < 16:
        raise ValueError("INVALID_ENVELOPE")
    hex_bytes(envelope["ciphertext_digest"], 32)
    b64decode(envelope["signature"], 64)
    if hashlib.sha256(ciphertext).hexdigest() != envelope["ciphertext_digest"]:
        raise ValueError("INVALID_ENVELOPE")
    return envelope


def decode_envelope(raw):
    if type(raw) is not bytes or len(raw) > MAX_ENVELOPE:
        raise ValueError("MESSAGE_TOO_LARGE")
    envelope = strict_loads(raw)
    if canonical_bytes(envelope) != raw:
        raise ValueError("INVALID_CANONICAL_ENVELOPE")
    return validate_envelope(envelope)


def signature_preimage(envelope):
    return b"ResearchHub/SecureEnvelope/v1\0" + canonical_bytes(
        {k: v for k, v in envelope.items() if k != "signature"}
    )


def verify_envelope(envelope, public_key):
    validate_envelope(envelope)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            b64decode(envelope["signature"], 64), signature_preimage(envelope)
        )
    except (ValueError, InvalidSignature):
        raise ValueError("INVALID_SIGNATURE") from None
    return envelope
