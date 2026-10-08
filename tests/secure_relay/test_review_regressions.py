"""Spec review regressions: real HTTPS types and real PG leak positive controls."""

import base64
import hashlib
import json
import os
from uuid import uuid4

import pytest
from conftest import CANARIES, PRIVATE_MATERIAL, SecretInventory
from privacy import audit
from researchhub.sync.secure import keys
from researchhub_relay.models import Chunk, Project, PublicObject, RequestReceipt
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import canonical_bytes, strict_loads
from packages.secure_wire.envelope import b64decode, b64encode


def chunk_body(project):
    return {
        "opaque_project_id": project.id,
        "opaque_locator": str(uuid4()),
        "key_epoch": 1,
        "index": 0,
        "total": 1,
        "size": 1,
        "manifest_identity": "0" * 64,
        "nonce": "000000000000000000000001",
        "ciphertext": b64encode(b"\x01" * 17),
    }


def resign(project, prepared, *, query=None, raw=None):
    proof = strict_loads(b64decode(prepared["headers"]["x-rh-proof"]))
    if query is not None:
        proof["query"] = query
    if raw is not None:
        prepared["content"] = raw
        proof["body_digest"] = hashlib.sha256(raw).hexdigest()
    proof = keys.signed_object("RelayRequest", proof, project.owner.signing_seed)
    prepared["headers"]["x-rh-proof"] = b64encode(canonical_bytes(proof))
    return prepared, proof["request_id"]


def assert_no_request_or_quota(project, request_id, expected):
    with Session(project.network["engine"]) as db:
        row = db.get(Project, project.id)
        assert (row.pending_bytes, row.cache_bytes, row.cache_count) == expected
        assert (
            db.get(RequestReceipt, (project.id, project.owner.device_id, request_id))
            is None
        )


def counters(project):
    with Session(project.network["engine"]) as db:
        row = db.get(Project, project.id)
        return row.pending_bytes, row.cache_bytes, row.cache_count


def test_chunk_numeric_types_reject_before_any_receipt_or_quota(project):
    expected = counters(project)
    for field in ("key_epoch", "index", "total", "size"):
        for value in (True, False, 1.0, None, "1"):
            body = chunk_body(project)
            body[field] = value
            # float is not RH-C14N-1, but it must also reject on the real wire.
            raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            request, request_id = resign(
                project, project.prepare("POST", "/v1/chunks", {}), raw=raw
            )
            assert project.send(request).status_code in (400, 401)
            assert_no_request_or_quota(project, request_id, expected)
            with Session(project.network["engine"]) as db:
                assert db.get(Chunk, (project.id, body["opaque_locator"], 0)) is None
    assert project.request("POST", "/v1/chunks", chunk_body(project)).status_code == 200


def test_signed_boolean_query_is_not_integer_query(project):
    chunk = chunk_body(project)
    assert project.request("POST", "/v1/chunks", chunk).status_code == 200
    cases = (
        ("/v1/messages", {"cursor": 0, "limit": 1}, {"cursor": False, "limit": True}),
        (
            "/v1/chunks",
            {"opaque_locator": chunk["opaque_locator"], "index": 0},
            {"opaque_locator": chunk["opaque_locator"], "index": False},
        ),
    )
    for path, actual, signed in cases:
        expected = counters(project)
        request, request_id = resign(
            project, project.prepare("GET", path, query=actual), query=signed
        )
        assert project.send(request).status_code == 401
        assert_no_request_or_quota(project, request_id, expected)
        assert project.request("GET", path, query=actual).status_code == 200


@pytest.mark.parametrize("kind", ["canary", "private"])
def test_real_database_leak_positive_control_and_exact_cleanup(project, kind):
    # Synthetic sentinel only, never a usable Device/Project/Recovery key.
    sentinel = (
        b"SYNTHETIC_PRIVACY_CONTROL_" + uuid4().hex.encode()
        if kind == "canary"
        else os.urandom(32)
    )
    inventory = SecretInventory()
    canaries = []
    if kind == "canary":
        canaries.append(sentinel)
        CANARIES.append(sentinel)
    else:
        inventory.append(sentinel)
        PRIVATE_MATERIAL.append(sentinel)
    variants = (
        sentinel,
        sentinel.hex().encode(),
        sentinel.hex().upper().encode(),
        base64.b64encode(sentinel),
        base64.b64encode(sentinel).rstrip(b"="),
        base64.urlsafe_b64encode(sentinel),
        base64.urlsafe_b64encode(sentinel).rstrip(b"="),
    )
    identity = (project.id, "privacy_control", str(uuid4()))
    try:
        for variant in variants:
            with Session(project.network["engine"]) as db, db.begin():
                row = db.get(PublicObject, identity)
                if row is None:
                    db.add(
                        PublicObject(
                            project=identity[0],
                            kind=identity[1],
                            id=identity[2],
                            body=variant,
                        )
                    )
                else:
                    row.body = variant
            with pytest.raises(RuntimeError, match="^PRIVACY_NONZERO_HITS"):
                audit(project.network, inventory, canaries)
    finally:
        with Session(project.network["engine"]) as db, db.begin():
            row = db.get(PublicObject, identity)
            if row is not None:
                db.delete(row)
        with Session(project.network["engine"]) as db:
            assert db.get(PublicObject, identity) is None
    audit(project.network, inventory, canaries)
