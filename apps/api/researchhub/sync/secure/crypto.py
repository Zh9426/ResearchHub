"""Standard library primitives. HPKE Base is anonymous, not sender authentication."""

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite
from cryptography.hazmat.primitives.keywrap import (
    InvalidUnwrap,
    aes_key_unwrap,
    aes_key_wrap,
)

from packages.secure_wire.envelope import canonical_bytes, hex_bytes, safe_int, uuid

WRAP_FIELDS = frozenset(
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
HPKE = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_256_GCM)


def fixed(raw, size):
    if not isinstance(raw, bytes) or len(raw) != size:
        raise ValueError("INVALID_KEY_OR_NONCE")
    return raw


def aes_encrypt(key, nonce, plaintext, aad):
    return AESGCM(fixed(key, 32)).encrypt(fixed(nonce, 12), plaintext, aad)


def aes_decrypt(key, nonce, ciphertext, aad):
    try:
        return AESGCM(fixed(key, 32)).decrypt(fixed(nonce, 12), ciphertext, aad)
    except InvalidTag:
        raise ValueError("DECRYPT_FAILED") from None


def signing_public(seed):
    return (
        Ed25519PrivateKey.from_private_bytes(fixed(seed, 32))
        .public_key()
        .public_bytes_raw()
    )


def recipient_public(seed):
    return (
        X25519PrivateKey.from_private_bytes(fixed(seed, 32))
        .public_key()
        .public_bytes_raw()
    )


def sign(seed, message):
    return Ed25519PrivateKey.from_private_bytes(fixed(seed, 32)).sign(message)


def verify(public_key, signature, message):
    try:
        Ed25519PublicKey.from_public_bytes(fixed(public_key, 32)).verify(
            fixed(signature, 64), message
        )
    except InvalidSignature:
        raise ValueError("INVALID_SIGNATURE") from None


def wrap_context(context):
    if type(context) is not dict or set(context) != WRAP_FIELDS:
        raise ValueError("INVALID_WRAP_CONTEXT")
    for f in ("opaque_project_id", "recipient_device_id", "session_id"):
        uuid(context[f])
    for f in ("key_epoch", "membership_epoch"):
        safe_int(context[f], 1)
    for f in ("recipient_signing_public_key", "recipient_public_key"):
        hex_bytes(context[f], 32)
    return canonical_bytes(context)


def wrap_key(public_key, key, context):
    info = wrap_context(context)
    if fixed(public_key, 32).hex() != context["recipient_public_key"]:
        raise ValueError("RECIPIENT_MISMATCH")
    return HPKE.encrypt(
        fixed(key, 32), X25519PublicKey.from_public_bytes(public_key), info
    )


def unwrap_key(seed, wrapped, context):
    info = wrap_context(context)
    if (
        recipient_public(seed).hex() != context["recipient_public_key"]
        or len(wrapped) != 80
    ):
        raise ValueError("RECIPIENT_MISMATCH")
    try:
        return fixed(
            HPKE.decrypt(wrapped, X25519PrivateKey.from_private_bytes(seed), info), 32
        )
    except InvalidTag:
        raise ValueError("UNWRAP_FAILED") from None


def kw_wrap(key, dek):
    return aes_key_wrap(fixed(key, 32), fixed(dek, 32))


def kw_unwrap(key, wrapped):
    try:
        return fixed(aes_key_unwrap(fixed(key, 32), wrapped), 32)
    except InvalidUnwrap:
        raise ValueError("UNWRAP_FAILED") from None
