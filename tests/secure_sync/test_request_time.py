"""Exact request time boundaries with real synthetic Ed25519 signatures."""

import hashlib
from uuid import uuid4

import pytest
from researchhub.sync.secure import keys

from packages.secure_wire.canonical import canonical_bytes
from packages.secure_wire.envelope import b64encode
from packages.secure_wire.request import AUDIENCE, decode_proof, verify_request

NOW = 1_800_000_000


@pytest.mark.parametrize(
    ("offset", "accepted"), [(-61, False), (-60, True), (5, True), (6, False)]
)
def test_request_time_window_has_inclusive_boundaries(offset, accepted):
    owner = keys.Device.generate()
    proof = keys.signed_object(
        "RelayRequest",
        {
            "version": 1,
            "audience": AUDIENCE,
            "method": "POST",
            "path": "/v1/hello",
            "query": {},
            "opaque_project_id": str(uuid4()),
            "device_id": owner.device_id,
            "membership_epoch": 1,
            "key_epoch": 1,
            "manifest_digest": "0" * 64,
            "body_digest": hashlib.sha256(b"{}").hexdigest(),
            "request_id": str(uuid4()),
            "issued_at": NOW + offset,
        },
        owner.signing_seed,
    )
    proof = decode_proof(b64encode(canonical_bytes(proof)))
    args = (proof, owner.signing_public, "POST", "/v1/hello", {}, b"{}", NOW)
    if accepted:
        assert verify_request(*args) is None
    else:
        with pytest.raises(ValueError, match="^AUTH_REJECTED$"):
            verify_request(*args)
