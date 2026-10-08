"""Cross-language framing. Every deterministic seed is PUBLIC TEST ONLY (§66).

Inputs exist only in the subprocess pipe; output contains authenticated public
objects/ciphertext and digests, never private seeds or plaintext keys.
"""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from researchhub.sync.secure.crypto import recipient_public, signing_public
from researchhub.sync.secure.nonce import NonceVault

from packages.secure_wire.canonical import digest
from packages.secure_wire.membership import (
    verify_bootstrap,
    verify_grant,
    verify_transition,
)
from tests.secure_sync.test_lifecycle import api

ROOT = Path(__file__).resolve().parents[2]


def test_independent_python_node_membership_grant_recovery_snapshot_and_chunks(
    tmp_path,
):
    helper = ROOT / "packages/secure-sync/test/lifecycle_interop.ts"
    assert helper.exists(), "cross-language lifecycle helper missing"
    k, a, c = api(), api("artifacts"), api("checkpoint")
    # Public deterministic test vectors only; never valid runtime identities.
    owner_seed, owner_recipient = bytes(range(32)), bytes(range(32, 64))
    target_seed, target_recipient = bytes(range(64, 96)), bytes(range(96, 128))
    owner = k.Device(
        "11111111-1111-4111-8111-111111111111", owner_seed, owner_recipient
    )
    target = k.Device(
        "22222222-2222-4222-8222-222222222222", target_seed, target_recipient
    )
    kit = k.RecoveryKit.from_public_test_vectors(
        bytes(range(128, 160)),
        bytes(range(160, 192)),
        device_id="33333333-3333-4333-8333-333333333333",
    )
    project = "44444444-4444-4444-8444-444444444444"
    key = bytes(range(192, 224))  # PUBLIC TEST ONLY
    initial = k.bootstrap(project, owner, kit)
    manifest = k.transition(initial, owner, add=target.member("writer", 1))
    grant = k.make_grant(manifest, owner, target.device_id, str(uuid4()), key)
    backup = k.make_recovery_backup(manifest, owner, kit, key)
    vault = NonceVault(tmp_path / "py-nonce.sqlite")
    vault.register_new(key, 0)
    data = b"SYNTHETIC_CHUNK" * 7000
    metadata = {
        "filename": "SYNTHETIC_SECRET_FILENAME_MAT",
        "category": "qa",
        "run_title": "qa",
    }
    bundle = a.seal_artifact(
        [data[:65536], data[65536:]],
        metadata,
        manifest,
        owner,
        key,
        vault,
        str(uuid4()),
    )
    cp = c.sign_checkpoint(manifest, owner, 0, "0" * 64)
    snapshot = c.seal_snapshot(
        {"SYNTHETIC_PRIVATE_NOTE": "qa"},
        "a" * 64,
        cp,
        manifest,
        owner,
        key,
        vault,
        str(uuid4()),
    )
    fixture = {
        "owner_signing_seed_TEST_ONLY": owner_seed.hex(),
        "owner_recipient_seed_TEST_ONLY": owner_recipient.hex(),
        "target_signing_seed_TEST_ONLY": target_seed.hex(),
        "target_recipient_seed_TEST_ONLY": target_recipient.hex(),
        "kit_signing_seed_TEST_ONLY": kit.signing_seed.hex(),
        "kit_recipient_seed_TEST_ONLY": kit.recipient_seed.hex(),
        "key_TEST_ONLY": key.hex(),
        "initial": initial,
        "manifest": manifest,
        "grant": grant,
        "backup": backup,
        "bundle": bundle,
        "checkpoint": cp,
        "snapshot": snapshot,
        "temp_path": str(tmp_path),
    }
    node = os.environ.get(
        "NODE_BIN", "E:/node/node.exe" if Path("E:/node/node.exe").exists() else "node"
    )
    result = subprocess.run(
        [str(node), str(helper)],
        input=json.dumps(fixture),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, "independent Node lifecycle validation failed"
    output = json.loads(result.stdout)
    assert output["input_verified"] is True
    verify_bootstrap(
        output["initial"], signing_public(owner_seed).hex(), kit.signing_public
    )
    verify_transition(initial, output["manifest"], kit.signing_public)
    assert digest(output["initial"]) == digest(initial)
    assert digest(output["manifest"]) == digest(manifest)
    verify_grant(output["grant"], manifest)
    assert digest(k.open_grant(output["grant"], manifest, target).hex()) == digest(
        key.hex()
    )
    store = k.TrustedStore(tmp_path / "recovery.sqlite")
    store.bootstrap(initial, owner.signing_public, kit.signing_public)
    store.accept(manifest)
    kit.update_anchor(manifest, cp, store=store)
    assert digest(k.open_recovery_backup(output["backup"], store, kit).hex()) == digest(
        key.hex()
    )
    sink = a.TestOnlyMemoryStagingSink()
    a.open_artifact(output["bundle"], manifest, key, sink)
    assert digest(sink.data.hex()) == digest(data.hex())
    assert c.open_snapshot(
        output["snapshot"],
        manifest,
        key,
        output["checkpoint"],
        module_snapshot_hash="a" * 64,
    ) == {"SYNTHETIC_PRIVATE_NOTE": "qa"}
    assert (
        recipient_public(target_recipient).hex()
        == manifest["members"][1]["recipient_public_key"]
    )
