import copy
import os
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from researchhub.sync.secure.crypto import aes_encrypt, kw_unwrap
from researchhub.sync.secure.envelope import open_record, seal_record
from researchhub.sync.secure.nonce import NonceVault

from packages.secure_wire.canonical import digest
from packages.secure_wire.envelope import b64decode, b64encode
from tests.secure_sync.test_lifecycle import api, setup_project


def artifact_fixture(tmp_path):
    _, owner, _, _, manifest, _ = setup_project(tmp_path)
    a = api("artifacts")
    key = os.urandom(32)
    vault = NonceVault(tmp_path / "nonce.sqlite")
    vault.register_new(key, 0)
    data = b"SYNTHETIC_SECRET_FILENAME_MAT" * 4000
    bundle = a.seal_artifact(
        [data[:65536], data[65536:]],
        {
            "filename": "SYNTHETIC_SECRET_FILENAME_MAT",
            "category": "synthetic",
            "run_title": "SYNTHETIC_PRIVATE_NOTE",
        },
        manifest,
        owner,
        key,
        vault,
        str(uuid4()),
    )
    return a, manifest, key, data, bundle


def test_artifact_multichunk_private_manifest_and_staging_retry(tmp_path):
    a, manifest, key, data, bundle = artifact_fixture(tmp_path)
    assert "SYNTHETIC_SECRET_FILENAME_MAT" not in str(bundle)
    sink = a.TestOnlyMemoryStagingSink()
    assert (
        a.open_artifact(bundle, manifest, key, sink)["filename"]
        == "SYNTHETIC_SECRET_FILENAME_MAT"
    )
    assert sink.ready and sink.data == data
    writes = sink.writes
    a.open_artifact(bundle, manifest, key, sink)
    assert sink.writes == writes


@pytest.mark.parametrize(
    "mutation", ["order", "missing", "duplicate", "tag", "size", "epoch"]
)
def test_artifact_rejects_fault_and_aborts_staging(tmp_path, mutation):
    a, manifest, key, _, bundle = artifact_fixture(tmp_path)
    bad = copy.deepcopy(bundle)
    if mutation == "order":
        bad["chunks"].reverse()
    elif mutation == "missing":
        bad["chunks"].pop()
    elif mutation == "duplicate":
        bad["chunks"][1] = bad["chunks"][0]
    elif mutation == "tag":
        raw = bytearray(b64decode(bad["chunks"][1]["ciphertext"]))
        raw[0] ^= 1
        bad["chunks"][1]["ciphertext"] = b64encode(raw)
    elif mutation == "size":
        bad["chunks"][1]["size"] += 1
    else:
        bad["chunks"][1]["key_epoch"] += 1
    sink = a.TestOnlyMemoryStagingSink()
    with pytest.raises(ValueError):
        a.open_artifact(bad, manifest, key, sink)
    assert not sink.ready and sink.data == b""


def test_artifact_valid_tag_with_boolean_index_is_strictly_rejected(tmp_path):
    a, manifest, key, data, bundle = artifact_fixture(tmp_path)
    owner = manifest["members"][0]
    inner = open_record(
        bundle["manifest_envelope"],
        key,
        bytes.fromhex(owner["signing_public_key"]),
        opaque_project_id=manifest["opaque_project_id"],
        sender_device_id=owner["device_id"],
        membership_epoch=1,
        key_epoch=1,
        nonce_prefix=0,
        record_type="artifact_manifest",
    )
    dek = kw_unwrap(key, b64decode(inner["wrapped_dek"]))
    vault = NonceVault(tmp_path / "nonce.sqlite")
    chunk = bundle["chunks"][1]
    chunk["index"] = True
    nonce = vault.reserve(dek, 0)
    chunk["nonce"] = nonce.hex()
    chunk["ciphertext"] = b64encode(
        aes_encrypt(dek, nonce, data[65536:], a.chunk_aad(chunk))
    )
    with pytest.raises(ValueError):
        a.open_artifact(bundle, manifest, key, a.TestOnlyMemoryStagingSink())


@pytest.mark.parametrize("field,value", [("key_epoch", True), ("nonce_prefix", False)])
def test_artifact_valid_inner_outer_and_chunk_auth_rejects_boolean_inner(
    tmp_path, field, value
):
    k, owner, _, _, manifest, _ = setup_project(tmp_path)
    a = api("artifacts")
    key = os.urandom(32)
    vault = NonceVault(tmp_path / "nonce.sqlite")
    vault.register_new(key, 0)
    parts = [b"SYNTHETIC_A", b"SYNTHETIC_B"]
    locator = str(uuid4())
    bundle = a.seal_artifact(
        parts,
        {"filename": "qa", "category": "qa", "run_title": "qa"},
        manifest,
        owner,
        key,
        vault,
        locator,
    )
    bindings = {
        "opaque_project_id": manifest["opaque_project_id"],
        "sender_device_id": owner.device_id,
        "membership_epoch": 1,
        "key_epoch": 1,
    }
    inner = open_record(
        bundle["manifest_envelope"],
        key,
        bytes.fromhex(owner.signing_public),
        **bindings,
        nonce_prefix=0,
        record_type="artifact_manifest",
    )
    dek = kw_unwrap(key, b64decode(inner["wrapped_dek"]))
    inner[field] = value
    inner = k.signed_object("ArtifactManifest", inner, owner.signing_seed)
    for chunk, part in zip(bundle["chunks"], parts, strict=True):
        chunk["manifest_identity"] = digest(inner)
        nonce = vault.reserve(dek, 0)
        chunk["nonce"] = nonce.hex()
        chunk["ciphertext"] = b64encode(
            aes_encrypt(dek, nonce, part, a.chunk_aad(chunk))
        )
    bundle["manifest_envelope"] = seal_record(
        inner,
        key,
        owner.signing_seed,
        vault,
        0,
        **bindings,
        message_id=locator,
        record_type="artifact_manifest",
    )
    sink = a.TestOnlyMemoryStagingSink()
    with pytest.raises(ValueError):
        a.open_artifact(bundle, manifest, key, sink)
    assert not sink.ready


def test_artifact_bounded_input_does_not_consume_unbounded_iterable(tmp_path):
    _, owner, _, _, manifest, _ = setup_project(tmp_path)
    a = api("artifacts")
    key = os.urandom(32)
    vault = NonceVault(tmp_path / "nonce.sqlite")
    vault.register_new(key, 0)
    calls = []

    def large():
        for i in range(100000):
            calls.append(i)
            yield bytes(65536)

    with pytest.raises(ValueError, match="ARTIFACT_TOO_LARGE"):
        a.seal_artifact(
            large(),
            {"filename": "qa", "category": "qa", "run_title": "qa"},
            manifest,
            owner,
            key,
            vault,
            str(uuid4()),
        )
    assert len(calls) <= 17


@given(st.permutations([0, 1, 2]))
def test_generated_chunk_order_only_accepts_original(order):
    a = api("artifacts")
    chunks = [{"index": i} for i in order]
    if tuple(order) == (0, 1, 2):
        a.validate_chunk_order(chunks, 3)
    else:
        with pytest.raises(ValueError):
            a.validate_chunk_order(chunks, 3)
