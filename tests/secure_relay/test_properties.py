"""Hypothesis generated retries, malformed inputs and opaque chunk permutations over HTTPS."""

from uuid import uuid4

from conftest import PRIVATE_MATERIAL
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from researchhub.sync.secure.artifacts import (
    TestOnlyMemoryStagingSink as MemoryStagingSink,
)
from researchhub.sync.secure.artifacts import open_artifact, seal_artifact
from researchhub.sync.secure.crypto import kw_unwrap
from researchhub.sync.secure.envelope import open_record

from packages.secure_wire.envelope import b64decode

RUN = settings(
    max_examples=8,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@RUN
@given(
    retries=st.lists(st.integers(min_value=0, max_value=2), min_size=1, max_size=7),
    payload=st.binary(min_size=1, max_size=50),
)
def test_generated_network_retry_idempotency(project, retries, payload):
    values = [project.envelope({"synthetic": payload.hex(), "n": n}) for n in range(3)]
    receipts = {}
    for index in retries:
        result = project.push([values[index]])
        assert result.status_code == 200
        if index in receipts:
            assert result.content == receipts[index]
        receipts[index] = result.content


@RUN
@given(
    field=st.sampled_from(
        ["crypto_suite", "signature", "nonce", "opaque_project_id", "ciphertext_digest"]
    ),
    change=st.text(alphabet="abcdef0123456789", min_size=1, max_size=6),
)
def test_generated_malformed_envelopes_reject_over_http(project, field, change):
    envelope = project.envelope()
    envelope[field] = change
    response = project.push([envelope])
    assert response.status_code == 400
    assert not response.json()["ok"]


@settings(
    max_examples=6,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(order=st.permutations((0, 1, 2)))
def test_generated_chunk_arrival_permutations_and_exact_retry(project, order):
    bundle = seal_artifact(
        [
            b"SYNTHETIC_PRIVATE_NOTE",
            b"SYNTHETIC_SECRET_PRESSURE_1_600",
            b"SYNTHETIC_SECRET_FILENAME_MAT",
        ],
        {
            "filename": "SYNTHETIC_SECRET_FILENAME_MAT",
            "category": "SYNTHETIC_CATEGORY_a2d6c0",
            "run_title": "SYNTHETIC_RUN_TITLE_b9c7df",
        },
        project.manifest,
        project.owner,
        project.key,
        project.vault,
        str(uuid4()),
    )
    inner = open_record(
        bundle["manifest_envelope"],
        project.key,
        bytes.fromhex(project.owner.signing_public),
        opaque_project_id=project.id,
        sender_device_id=project.owner.device_id,
        membership_epoch=1,
        key_epoch=1,
        nonce_prefix=0,
        record_type="artifact_manifest",
    )
    PRIVATE_MATERIAL.append(kw_unwrap(project.key, b64decode(inner["wrapped_dek"])))
    assert project.push([bundle["manifest_envelope"]]).status_code == 200
    for index in order:
        chunk = bundle["chunks"][index]
        response = project.request("POST", "/v1/chunks", chunk)
        assert response.status_code == 200
        assert project.request("POST", "/v1/chunks", chunk).content == response.content
    restored = [
        project.request(
            "GET",
            "/v1/chunks",
            query={"opaque_locator": bundle["chunks"][0]["opaque_locator"], "index": i},
        ).json()["result"]
        for i in range(3)
    ]
    assert restored == bundle["chunks"]
    sink = MemoryStagingSink()
    open_artifact(
        {"manifest_envelope": bundle["manifest_envelope"], "chunks": restored},
        project.manifest,
        project.key,
        sink,
    )
    assert sink.ready
    changed = {**restored[0], "manifest_identity": "f" * 64}
    assert (
        project.request("POST", "/v1/chunks", changed).json()["code"]
        == "OBJECT_COLLISION"
    )
