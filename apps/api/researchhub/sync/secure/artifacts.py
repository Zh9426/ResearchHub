"""Bounded 1 MiB synthetic chunked artifact prototype; no MinIO/OPFS integration."""

import hashlib
import os
from typing import Protocol

from packages.secure_wire.canonical import canonical_bytes, digest
from packages.secure_wire.envelope import (
    b64decode,
    b64encode,
    hex_bytes,
    safe_int,
    uuid,
)
from packages.secure_wire.membership import (
    fields,
    member_of,
    verify_active_envelope,
    verify_signed,
)

from .crypto import aes_decrypt, aes_encrypt, kw_unwrap, kw_wrap
from .envelope import open_record, seal_record
from .keys import signed_object

MAX_CHUNK = 64 * 1024
MAX_ARTIFACT = 1024 * 1024
CHUNK_FIELDS = frozenset(
    [
        "opaque_project_id",
        "opaque_locator",
        "key_epoch",
        "index",
        "total",
        "size",
        "manifest_identity",
        "nonce",
        "ciphertext",
    ]
)
METADATA_FIELDS = frozenset(("filename", "category", "run_title"))
MANIFEST_FIELDS = frozenset(
    [
        "version",
        "opaque_project_id",
        "opaque_locator",
        "key_epoch",
        "creator_device_id",
        "total_size",
        "total_chunks",
        "plaintext_digest",
        "chunk_sizes",
        "metadata",
        "wrapped_dek",
        "nonce_prefix",
        "signature",
    ]
)


class StagingSink(Protocol):
    def begin(self, identity: str) -> bool: ...
    def write(self, index: int, value: bytes) -> None: ...
    def commit(self) -> None: ...
    def abort(self) -> None: ...


class TestOnlyMemoryStagingSink:
    """Bounded prototype sink; immutable exact bundle retry performs zero writes."""

    def __init__(self):
        self.identity = None
        self.ready = False
        self.data = b""
        self.writes = 0

    def begin(self, identity):
        if self.ready:
            if identity != self.identity:
                raise ValueError("ARTIFACT_IDENTITY_COLLISION")
            return False
        self.identity = identity
        self.data = b""
        return True

    def write(self, index, value):
        self.data += value
        self.writes += 1

    def commit(self):
        self.ready = True

    def abort(self):
        self.data = b""
        self.ready = False


def chunk_aad(chunk):
    return b"ResearchHub/ArtifactChunk/v1\0" + canonical_bytes(
        {f: chunk[f] for f in CHUNK_FIELDS - {"nonce", "ciphertext"}}
    )


def validate_chunk_order(chunks, total):
    if (
        type(chunks) is not list
        or len(chunks) != total
        or any(type(c) is not dict for c in chunks)
        or [c.get("index") for c in chunks] != list(range(total))
    ):
        raise ValueError("ARTIFACT_CHUNK_ORDER")
    for c in chunks:
        safe_int(c["index"], 0, 15)


def seal_artifact(
    parts, metadata, manifest, creator, project_key, vault, opaque_locator
):
    uuid(opaque_locator)
    fields(metadata, METADATA_FIELDS)
    if any(type(v) is not str or len(v) > 1024 for v in metadata.values()):
        raise ValueError("INVALID_ARTIFACT_METADATA")
    member = member_of(manifest, creator.device_id, roles=("owner", "writer"))
    bounded, total_size, sha = [], 0, hashlib.sha256()
    # Enforce bounds while iterating, before accumulating/encrypting anything.
    for part in parts:
        if type(part) is not bytes or not 1 <= len(part) <= MAX_CHUNK:
            raise ValueError("INVALID_ARTIFACT_CHUNK_SIZE")
        total_size += len(part)
        if total_size > MAX_ARTIFACT or len(bounded) >= 16:
            raise ValueError("ARTIFACT_TOO_LARGE")
        bounded.append(part)
        sha.update(part)
    if not bounded:
        raise ValueError("EMPTY_ARTIFACT")
    dek = os.urandom(32)
    vault.register_new(dek, member["nonce_prefix"])
    inner = signed_object(
        "ArtifactManifest",
        {
            "version": 1,
            "opaque_project_id": manifest["opaque_project_id"],
            "opaque_locator": opaque_locator,
            "key_epoch": manifest["key_epoch"],
            "creator_device_id": creator.device_id,
            "total_size": total_size,
            "total_chunks": len(bounded),
            "plaintext_digest": sha.hexdigest(),
            "chunk_sizes": [len(p) for p in bounded],
            "metadata": metadata,
            "wrapped_dek": b64encode(kw_wrap(project_key, dek)),
            "nonce_prefix": member["nonce_prefix"],
        },
        creator.signing_seed,
    )
    identity = digest(inner)
    chunks = []
    for index, part in enumerate(bounded):
        chunk = {
            "opaque_project_id": manifest["opaque_project_id"],
            "opaque_locator": opaque_locator,
            "key_epoch": manifest["key_epoch"],
            "index": index,
            "total": len(bounded),
            "size": len(part),
            "manifest_identity": identity,
        }
        nonce = vault.reserve(dek, member["nonce_prefix"])
        chunk["nonce"] = nonce.hex()
        chunk["ciphertext"] = b64encode(aes_encrypt(dek, nonce, part, chunk_aad(chunk)))
        chunks.append(chunk)
    env = seal_record(
        inner,
        project_key,
        creator.signing_seed,
        vault,
        member["nonce_prefix"],
        opaque_project_id=manifest["opaque_project_id"],
        sender_device_id=creator.device_id,
        membership_epoch=manifest["membership_epoch"],
        key_epoch=manifest["key_epoch"],
        message_id=opaque_locator,
        record_type="artifact_manifest",
    )
    return {"manifest_envelope": env, "chunks": chunks}


def open_artifact(bundle, manifest, project_key, sink):
    fields(bundle, frozenset(("manifest_envelope", "chunks")))
    env = bundle["manifest_envelope"]
    verify_active_envelope(env, manifest)
    member = member_of(manifest, env["sender_device_id"])
    inner = open_record(
        env,
        project_key,
        bytes.fromhex(member["signing_public_key"]),
        opaque_project_id=manifest["opaque_project_id"],
        sender_device_id=member["device_id"],
        membership_epoch=manifest["membership_epoch"],
        key_epoch=manifest["key_epoch"],
        nonce_prefix=member["nonce_prefix"],
        record_type="artifact_manifest",
    )
    fields(inner, MANIFEST_FIELDS)
    safe_int(inner["version"], 1, 1)
    safe_int(inner["key_epoch"], 1)
    safe_int(inner["nonce_prefix"], 0, 4294967295)
    uuid(inner["opaque_project_id"])
    uuid(inner["opaque_locator"])
    uuid(inner["creator_device_id"])
    safe_int(inner["total_size"], 1, MAX_ARTIFACT)
    safe_int(inner["total_chunks"], 1, 16)
    hex_bytes(inner["plaintext_digest"], 32)
    fields(inner["metadata"], METADATA_FIELDS)
    if any(type(v) is not str or len(v) > 1024 for v in inner["metadata"].values()):
        raise ValueError("INVALID_ARTIFACT_METADATA")
    if (
        inner["opaque_project_id"] != manifest["opaque_project_id"]
        or inner["key_epoch"] != manifest["key_epoch"]
        or inner["creator_device_id"] != member["device_id"]
        or inner["nonce_prefix"] != member["nonce_prefix"]
        or inner["opaque_locator"] != env["message_id"]
        or type(inner["chunk_sizes"]) is not list
        or len(inner["chunk_sizes"]) != inner["total_chunks"]
    ):
        raise ValueError("ARTIFACT_BINDING_MISMATCH")
    for size in inner["chunk_sizes"]:
        safe_int(size, 1, MAX_CHUNK)
    if sum(inner["chunk_sizes"]) != inner["total_size"]:
        raise ValueError("ARTIFACT_SIZE_MISMATCH")
    verify_signed("ArtifactManifest", inner, member["signing_public_key"])
    dek = kw_unwrap(project_key, b64decode(inner["wrapped_dek"], 40))
    identity = digest(inner)
    # Cache exact ciphertext bundle identity, not merely a locator/manifest.
    fresh = sink.begin(digest(bundle))
    try:
        validate_chunk_order(bundle["chunks"], inner["total_chunks"])
        sha, total, nonces = hashlib.sha256(), 0, set()
        for chunk in bundle["chunks"]:
            fields(chunk, CHUNK_FIELDS)
            uuid(chunk["opaque_project_id"])
            uuid(chunk["opaque_locator"])
            safe_int(chunk["key_epoch"], 1)
            safe_int(chunk["index"], 0, 15)
            safe_int(chunk["total"], 1, 16)
            safe_int(chunk["size"], 1, MAX_CHUNK)
            hex_bytes(chunk["manifest_identity"], 32)
            if (
                any(
                    chunk[f] != inner[f]
                    for f in ("opaque_project_id", "opaque_locator", "key_epoch")
                )
                or chunk["manifest_identity"] != identity
                or chunk["total"] != inner["total_chunks"]
                or chunk["size"] != inner["chunk_sizes"][chunk["index"]]
            ):
                raise ValueError("ARTIFACT_BINDING_MISMATCH")
            nonce = hex_bytes(chunk["nonce"], 12)
            if (
                int.from_bytes(nonce[:4], "big") != inner["nonce_prefix"]
                or not 1 <= int.from_bytes(nonce[4:], "big") <= 9007199254740991
                or nonce in nonces
            ):
                raise ValueError("NONCE_BINDING_MISMATCH")
            nonces.add(nonce)
            ciphertext = b64decode(chunk["ciphertext"])
            if len(ciphertext) != chunk["size"] + 16:
                raise ValueError("ARTIFACT_SIZE_MISMATCH")
            part = aes_decrypt(dek, nonce, ciphertext, chunk_aad(chunk))
            total += len(part)
            sha.update(part)
            if fresh:
                sink.write(chunk["index"], part)
        if total != inner["total_size"] or sha.hexdigest() != inner["plaintext_digest"]:
            raise ValueError("ARTIFACT_DIGEST_MISMATCH")
        if fresh:
            sink.commit()
    except BaseException:
        if fresh:
            sink.abort()
        raise
    return inner["metadata"]
