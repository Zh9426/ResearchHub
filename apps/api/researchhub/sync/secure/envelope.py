"""Trusted envelope opening validates all bindings before passing records onward."""

import hashlib

from packages.secure_wire.canonical import digest
from packages.secure_wire.envelope import (
    SUITE,
    b64decode,
    b64encode,
    canonical_bytes,
    header_of,
    signature_preimage,
    strict_loads,
    validate_envelope,
    validate_header,
    verify_envelope,
)

from ..protocol import transaction_digest, validate_transaction
from .crypto import aes_decrypt, aes_encrypt, sign


def aad(header):
    return b"ResearchHub/AEAD/v1\0" + canonical_bytes(header)


def seal_record(
    record,
    key,
    seed,
    vault,
    nonce_prefix,
    *,
    opaque_project_id,
    sender_device_id,
    membership_epoch,
    key_epoch,
    message_id,
    dependencies=None,
    checkpoint_sequence=0,
    record_type="snapshot",
):
    plaintext = canonical_bytes(record)
    if len(plaintext) > 180 * 1024:
        raise ValueError("MESSAGE_TOO_LARGE")
    header = {
        "envelope_version": 1,
        "crypto_suite": SUITE,
        "protocol_version": 1,
        "schema_version": 1,
        "record_type": record_type,
        "opaque_project_id": opaque_project_id,
        "sender_device_id": sender_device_id,
        "membership_epoch": membership_epoch,
        "key_epoch": key_epoch,
        "message_id": message_id,
        "semantic_transaction_digest": digest(record),
        "dependencies": [] if dependencies is None else dependencies,
        "nonce": "00" * 12,
        "checkpoint_sequence": checkpoint_sequence,
    }
    validate_header(header)
    header["nonce"] = vault.reserve(key, nonce_prefix).hex()
    ciphertext = aes_encrypt(
        key, bytes.fromhex(header["nonce"]), plaintext, aad(header)
    )
    envelope = {
        **header,
        "ciphertext": b64encode(ciphertext),
        "ciphertext_digest": hashlib.sha256(ciphertext).hexdigest(),
    }
    envelope["signature"] = b64encode(sign(seed, signature_preimage(envelope)))
    return validate_envelope(envelope)


def open_record(
    envelope,
    key,
    public_key,
    *,
    opaque_project_id,
    sender_device_id,
    membership_epoch,
    key_epoch,
    nonce_prefix,
    record_type="snapshot",
):
    verify_envelope(envelope, public_key)
    for f, value in {
        "opaque_project_id": opaque_project_id,
        "sender_device_id": sender_device_id,
        "membership_epoch": membership_epoch,
        "key_epoch": key_epoch,
        "record_type": record_type,
    }.items():
        if envelope[f] != value:
            raise ValueError("ENVELOPE_BINDING_MISMATCH")
    nonce = bytes.fromhex(envelope["nonce"])
    if (
        int.from_bytes(nonce[:4], "big") != nonce_prefix
        or not 1 <= int.from_bytes(nonce[4:], "big") <= 9007199254740991
    ):
        raise ValueError("NONCE_BINDING_MISMATCH")
    raw = aes_decrypt(
        key, nonce, b64decode(envelope["ciphertext"]), aad(header_of(envelope))
    )
    try:
        value = strict_loads(raw)
    except ValueError:
        raise ValueError("INVALID_PLAINTEXT") from None
    if (
        canonical_bytes(value) != raw
        or digest(value) != envelope["semantic_transaction_digest"]
    ):
        raise ValueError("SEMANTIC_DIGEST_MISMATCH")
    return value


def seal_transaction(tx, key, seed, vault, nonce_prefix, **bindings):
    validate_transaction(tx)
    if tx["device_id"] != bindings["sender_device_id"]:
        raise ValueError("DEVICE_MISMATCH")
    return seal_record(
        tx,
        key,
        seed,
        vault,
        nonce_prefix,
        dependencies=tx["dependencies"],
        record_type="transaction",
        **bindings,
    )


def open_transaction(envelope, key, public_key, *, project_id, **bindings):
    tx = open_record(envelope, key, public_key, record_type="transaction", **bindings)
    validate_transaction(tx)
    if (
        tx["project_id"] != project_id
        or tx["device_id"] != envelope["sender_device_id"]
        or tx["dependencies"] != envelope["dependencies"]
    ):
        raise ValueError("TRANSACTION_BINDING_MISMATCH")
    if transaction_digest(tx) != envelope["semantic_transaction_digest"]:
        raise ValueError("SEMANTIC_DIGEST_MISMATCH")
    return tx
