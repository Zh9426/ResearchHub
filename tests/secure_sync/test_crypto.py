"""Synthetic public TEST ONLY inputs; never production key material."""

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
from researchhub.sync.secure.crypto import (
    aes_decrypt,
    aes_encrypt,
    kw_unwrap,
    kw_wrap,
    recipient_public,
    sign,
    signing_public,
    unwrap_key,
    verify,
    wrap_key,
)
from researchhub.sync.secure.envelope import open_record, seal_record

from packages.secure_wire.envelope import (
    canonical_bytes,
    validate_envelope,
    verify_envelope,
)

KEY = bytes(range(32))  # PUBLIC TEST ONLY
SEED = bytes(range(32, 64))  # PUBLIC TEST ONLY
ID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def context():
    return {
        "opaque_project_id": ID,
        "recipient_device_id": OTHER,
        "key_epoch": 1,
        "membership_epoch": 1,
        "session_id": ID,
        "recipient_signing_public_key": signing_public(SEED).hex(),
        "recipient_public_key": recipient_public(SEED).hex(),
    }


def binding():
    return {
        "opaque_project_id": ID,
        "sender_device_id": OTHER,
        "membership_epoch": 1,
        "key_epoch": 1,
    }


def sealed():
    import tempfile
    from pathlib import Path

    from researchhub.sync.secure.nonce import NonceVault

    with tempfile.TemporaryDirectory(dir="storage/runtime") as folder:
        vault = NonceVault(Path(folder) / "nonce.sqlite")
        vault.register_new(KEY, 7)
        return seal_record(
            {"synthetic": "TEST ONLY"}, KEY, SEED, vault, 7, **binding(), message_id=ID
        )


def test_primitives_roundtrip_and_authentication():
    nonce = bytes(12)
    msg = b"TEST ONLY"
    aad = b"bound"
    ct = aes_encrypt(KEY, nonce, msg, aad)
    assert aes_decrypt(KEY, nonce, ct, aad) == msg
    with pytest.raises(ValueError):
        aes_decrypt(KEY, nonce, ct, b"wrong")
    sig = sign(SEED, msg)
    verify(signing_public(SEED), sig, msg)
    with pytest.raises(ValueError):
        verify(signing_public(SEED), sig, b"wrong")
    wrapped = wrap_key(recipient_public(SEED), KEY, context())
    assert unwrap_key(SEED, wrapped, context()) == KEY
    with pytest.raises(ValueError):
        unwrap_key(KEY, wrapped, context())
    ctx = context()
    ctx["key_epoch"] = 2
    with pytest.raises(ValueError):
        unwrap_key(SEED, wrapped, ctx)
    assert kw_unwrap(KEY, kw_wrap(KEY, SEED)) == SEED


def test_envelope_signature_binding_and_semantic_digest():
    env = sealed()
    validate_envelope(env)
    verify_envelope(env, signing_public(SEED))
    assert open_record(env, KEY, signing_public(SEED), **binding(), nonce_prefix=7) == {
        "synthetic": "TEST ONLY"
    }
    for field in env:
        altered = copy.deepcopy(env)
        if field == "signature":
            altered[field] = "A" * 86
        elif field == "dependencies":
            altered[field] = [ID]
        elif isinstance(altered[field], int):
            altered[field] += 1
        else:
            altered[field] = str(altered[field]) + "A"
        with pytest.raises(ValueError):
            open_record(altered, KEY, signing_public(SEED), **binding(), nonce_prefix=7)
    with pytest.raises(ValueError):
        open_record(
            env,
            KEY,
            signing_public(SEED),
            **{**binding(), "key_epoch": 2},
            nonce_prefix=7,
        )


def test_canonical_copy_matches_existing_vectors():
    import json
    from pathlib import Path

    from researchhub.sync.canonical import canonical_bytes as original

    for path in Path("fixtures/sync/v1").rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        try:
            expected = original(value)
        except ValueError:
            with pytest.raises(ValueError):
                canonical_bytes(value)
        else:
            assert canonical_bytes(value) == expected


def test_public_canonical_all_shared_vectors():
    from packages.secure_wire.canonical import digest, strict_loads

    for vector in json.loads(
        Path("fixtures/sync/v1/canonical.json").read_text(encoding="utf8")
    ):
        assert canonical_bytes(vector["input"]).hex() == vector["hex"]
        assert digest(vector["input"]) == vector["sha256"]
    for vector in json.loads(
        Path("fixtures/sync/v1/nesting.json").read_text(encoding="utf8")
    ):
        if vector["valid"]:
            assert (
                canonical_bytes(strict_loads(vector["raw"])).decode() == vector["raw"]
            )
        else:
            with pytest.raises(ValueError):
                strict_loads(vector["raw"])


def node_call(value):
    node = os.environ.get(
        "NODE_BIN", "E:/node/node.exe" if Path("E:/node/node.exe").exists() else "node"
    )
    result = subprocess.run(
        [node, "packages/secure-sync/test/interop.ts"],
        input=json.dumps(value),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_independent_cross_language_primitives_and_fixed_vectors():
    fixture = json.loads(
        Path("fixtures/sync/secure-v1/primitives.TEST_ONLY.json").read_text()
    )
    result = node_call({"mode": "verify", **fixture})
    assert result == {
        "plaintext": fixture["message"],
        "unwrapped_matches": True,
        "dek_matches": True,
    }
    result = node_call({"mode": "generate", **fixture})
    assert result["ciphertext"] == fixture["ciphertext"]
    assert result["signature"] == fixture["signature"]
    verify(
        bytes.fromhex(result["signing_public"]),
        bytes.fromhex(result["signature"]),
        bytes.fromhex(fixture["message"]),
    )
    assert (
        aes_decrypt(
            KEY,
            bytes.fromhex(fixture["nonce"]),
            bytes.fromhex(result["ciphertext"]),
            bytes.fromhex(fixture["aad"]),
        ).hex()
        == fixture["message"]
    )
    assert unwrap_key(SEED, bytes.fromhex(result["wrapped"]), fixture["context"]) == KEY
    assert kw_unwrap(KEY, bytes.fromhex(result["kw"])) == SEED


def test_independent_cross_language_envelopes(tmp_path):
    env = sealed()
    assert node_call(
        {
            "mode": "open",
            "key": KEY.hex(),
            "public_key": signing_public(SEED).hex(),
            "envelope": env,
            "bindings": {**binding(), "nonce_prefix": 7},
        }
    ) == {"synthetic": "TEST ONLY"}
    env = node_call(
        {
            "mode": "seal",
            "key": KEY.hex(),
            "seed": SEED.hex(),
            "path": str(tmp_path / "node.sqlite"),
            "prefix": 7,
            "record": {"synthetic": "TEST ONLY"},
            "bindings": {**binding(), "message_id": ID},
        }
    )
    assert open_record(env, KEY, signing_public(SEED), **binding(), nonce_prefix=7) == {
        "synthetic": "TEST ONLY"
    }


def test_wire_decoder_rejects_noncanonical_oversized_duplicate_json():
    from packages.secure_wire import envelope as wire

    assert hasattr(wire, "decode_envelope"), "public strict wire decoder must exist"
    env = sealed()
    raw = canonical_bytes(env)
    assert wire.decode_envelope(raw) == env
    for bad in (b" " + raw, raw.replace(b"{", b'{"nonce":"00",', 1), b" " * 262145):
        with pytest.raises(ValueError):
            wire.decode_envelope(bad)


def test_transaction_reencryption_preserves_semantic_identity(tmp_path):
    from researchhub.sync.protocol import revision, transaction_digest
    from researchhub.sync.secure.envelope import open_transaction, seal_transaction
    from researchhub.sync.secure.nonce import NonceVault

    tx = json.loads(
        json.loads(Path("fixtures/sync/v1/protocol.json").read_text())[0]["raw"]
    )
    v = NonceVault(tmp_path / "nonce.sqlite")
    v.register_new(KEY, 7)
    bindings = {**binding(), "sender_device_id": tx["device_id"]}
    first = seal_transaction(tx, KEY, SEED, v, 7, **bindings, message_id=ID)
    retry_bytes = canonical_bytes(first)
    # Exact retry sends immutable cached bytes; no call to seal or reserve.
    assert canonical_bytes(first) == retry_bytes
    second = seal_transaction(tx, KEY, SEED, v, 7, **bindings, message_id=OTHER)
    assert (
        first["nonce"] != second["nonce"]
        and first["ciphertext"] != second["ciphertext"]
    )
    assert (
        first["semantic_transaction_digest"]
        == second["semantic_transaction_digest"]
        == transaction_digest(tx)
    )
    for env in (first, second):
        opened = open_transaction(
            env,
            KEY,
            signing_public(SEED),
            **bindings,
            nonce_prefix=7,
            project_id=tx["project_id"],
        )
        assert opened["transaction_id"] == tx["transaction_id"]
        assert [revision(c) for c in opened["changes"]] == [
            revision(c) for c in tx["changes"]
        ]
        with pytest.raises(ValueError):
            open_transaction(
                env,
                KEY,
                signing_public(SEED),
                **bindings,
                nonce_prefix=7,
                project_id=OTHER,
            )


def forge_plain(env, raw, **changes):
    import hashlib

    from researchhub.sync.secure.envelope import aad

    from packages.secure_wire.envelope import b64encode, header_of, signature_preimage

    bad = {**env, **changes}
    ct = aes_encrypt(KEY, bytes.fromhex(bad["nonce"]), raw, aad(header_of(bad)))
    bad["ciphertext"] = b64encode(ct)
    bad["ciphertext_digest"] = hashlib.sha256(ct).hexdigest()
    bad["signature"] = b64encode(sign(SEED, signature_preimage(bad)))
    return bad


def test_valid_signature_noncanonical_plaintext_and_wrong_digest_rejected():
    env = sealed()
    for bad in (
        forge_plain(env, b'{"synthetic": "TEST ONLY"}'),
        forge_plain(env, b'{"synthetic":"DIFFERENT"}'),
    ):
        with pytest.raises(ValueError):
            open_record(bad, KEY, signing_public(SEED), **binding(), nonce_prefix=7)


def test_decrypted_parser_errors_do_not_expose_plaintext_tokens():
    env = sealed()
    secret_token = "1.123456789123456789"
    bad = forge_plain(env, ('{"synthetic":' + secret_token + "}").encode())
    with pytest.raises(ValueError, match="^INVALID_PLAINTEXT$") as error:
        open_record(bad, KEY, signing_public(SEED), **binding(), nonce_prefix=7)
    assert secret_token not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol_version", 0),
        ("crypto_suite", "unsigned"),
        ("key_epoch", True),
        ("dependencies", [OTHER, ID]),
        ("nonce", "AA" * 12),
        ("ciphertext", "AA=="),
        ("signature", "A" * 85),
        ("message_id", "00000000-0000-0000-0000-000000000000"),
    ],
)
def test_strict_malformed_envelope_fields(field, value):
    env = sealed()
    env[field] = value
    with pytest.raises(ValueError):
        validate_envelope(env)


def test_runtime_random_material_interoperability():
    key = os.urandom(32)
    seed = os.urandom(32)
    ctx = {
        **context(),
        "recipient_public_key": recipient_public(seed).hex(),
        "recipient_signing_public_key": signing_public(seed).hex(),
    }
    fixture = {
        "key": key.hex(),
        "seed": seed.hex(),
        "message": b"SYNTHETIC RANDOM RUN".hex(),
        "aad": b"binding".hex(),
        "nonce": (bytes.fromhex("00000007") + (1).to_bytes(8, "big")).hex(),
        "context": ctx,
    }
    generated = node_call({"mode": "generate", **fixture})
    assert (
        aes_decrypt(
            key,
            bytes.fromhex(fixture["nonce"]),
            bytes.fromhex(generated["ciphertext"]),
            bytes.fromhex(fixture["aad"]),
        ).hex()
        == fixture["message"]
    )
    verify(
        signing_public(seed),
        bytes.fromhex(generated["signature"]),
        bytes.fromhex(fixture["message"]),
    )
    assert unwrap_key(seed, bytes.fromhex(generated["wrapped"]), ctx) == key
    python = {
        "ciphertext": aes_encrypt(
            key,
            bytes.fromhex(fixture["nonce"]),
            bytes.fromhex(fixture["message"]),
            bytes.fromhex(fixture["aad"]),
        ).hex(),
        "signature": sign(seed, bytes.fromhex(fixture["message"])).hex(),
        "signing_public": signing_public(seed).hex(),
        "wrapped": wrap_key(recipient_public(seed), key, ctx).hex(),
        "kw": kw_wrap(key, seed).hex(),
    }
    assert node_call({"mode": "verify", **fixture, **python}) == {
        "plaintext": fixture["message"],
        "unwrapped_matches": True,
        "dek_matches": True,
    }


def test_fixed_canonical_transaction_envelope_cross_language(tmp_path):
    import hashlib

    from researchhub.sync.protocol import revision, transaction_digest
    from researchhub.sync.secure.envelope import aad, open_transaction

    from packages.secure_wire.envelope import b64decode, decode_envelope, header_of

    fixture_path = Path("fixtures/sync/secure-v1/transaction-envelope.TEST_ONLY.json")
    assert fixture_path.is_file(), (
        "fixed PUBLIC TEST ONLY canonical transaction/envelope fixture is required"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf8"))
    raw = bytes.fromhex(fixture["envelope_canonical_hex"])
    assert hashlib.sha256(raw).hexdigest() == fixture["envelope_sha256"]
    env = decode_envelope(raw)
    assert env == fixture["envelope"]
    assert aad(header_of(env)).hex() == fixture["aad_hex"]
    key = bytes.fromhex(fixture["key_TEST_ONLY"])
    pub = bytes.fromhex(fixture["signing_public_key"])
    tx = open_transaction(env, key, pub, **fixture["bindings"])
    assert canonical_bytes(tx).hex() == fixture["plaintext_canonical_hex"]
    assert transaction_digest(tx) == fixture["semantic_transaction_digest"]
    assert [revision(c) for c in tx["changes"]] == fixture["semantic_revision_digests"]
    assert b64decode(env["ciphertext"]).hex() == fixture["ciphertext_hex"]
    assert b64decode(env["signature"]).hex() == fixture["signature_hex"]
    assert (
        unwrap_key(
            bytes.fromhex(fixture["recipient_seed_TEST_ONLY"]),
            bytes.fromhex(fixture["wrapped_key_hex"]),
            fixture["wrap_context"],
        )
        == key
    )
    assert (
        node_call({"mode": "transaction_fixture", **fixture})
        == fixture["expected_verification"]
    )
    from researchhub.sync.secure.envelope import seal_transaction
    from researchhub.sync.secure.nonce import NonceVault

    vault = NonceVault(tmp_path / "fixed-python.sqlite")
    vault.register_new(key, fixture["bindings"]["nonce_prefix"])
    seal_bindings = {
        k: v
        for k, v in fixture["bindings"].items()
        if k not in ("nonce_prefix", "project_id")
    }
    python_sealed = seal_transaction(
        tx,
        key,
        bytes.fromhex(fixture["signing_seed_TEST_ONLY"]),
        vault,
        fixture["bindings"]["nonce_prefix"],
        message_id=env["message_id"],
        **seal_bindings,
    )
    assert canonical_bytes(python_sealed) == raw
    assert node_call(
        {
            "mode": "transaction_seal",
            **fixture,
            "path": str(tmp_path / "fixed-node.sqlite"),
        }
    ) == {
        "envelope_canonical_hex": fixture["envelope_canonical_hex"],
        "envelope_sha256": fixture["envelope_sha256"],
    }
    for field, replacement in [
        ("opaque_project_id", OTHER),
        ("sender_device_id", ID),
        ("membership_epoch", 2),
        ("key_epoch", 2),
        ("nonce_prefix", 20),
        ("project_id", OTHER),
    ]:
        bad_bindings = {**fixture["bindings"], field: replacement}
        with pytest.raises(ValueError):
            open_transaction(env, key, pub, **bad_bindings)
        with pytest.raises(subprocess.CalledProcessError):
            node_call(
                {"mode": "transaction_fixture", **fixture, "bindings": bad_bindings}
            )
