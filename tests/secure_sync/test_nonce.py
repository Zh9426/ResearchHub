import json
import shutil
import sqlite3
import subprocess
import sys

import pytest
from researchhub.sync.secure.nonce import NonceVault

from .test_crypto import node_call

KEY = bytes(range(32))  # PUBLIC TEST ONLY


def test_register_restart_reserve(tmp_path):
    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    with pytest.raises(ValueError):
        v.reserve(KEY, 4)
    v.register_new(KEY, 4)
    assert v.reserve(KEY, 4) == bytes.fromhex("000000040000000000000001")
    assert NonceVault(p).reserve(KEY, 4) == bytes.fromhex("000000040000000000000002")
    with pytest.raises(ValueError):
        v.register_new(KEY, 4)


@pytest.mark.parametrize(
    "damage",
    [
        "db_deleted",
        "witness_deleted",
        "torn",
        "crlf",
        "row_deleted",
        "rollback",
        "overflow",
        "anchor_deleted",
        "both_deleted",
    ],
)
def test_fail_closed_ledger_damage(tmp_path, damage):
    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    v.register_new(KEY, 4)
    backup = tmp_path / "backup"
    shutil.copyfile(p, backup)
    v.reserve(KEY, 4)
    if damage == "db_deleted":
        p.unlink()
    elif damage == "witness_deleted":
        v.witness_path.unlink()
    elif damage == "torn":
        with v.witness_path.open("ab") as f:
            f.write(b"{")
    elif damage == "crlf":
        v.witness_path.write_bytes(v.witness_path.read_bytes().replace(b"\n", b"\r\n"))
    elif damage == "anchor_deleted":
        v.anchor_path.unlink()
    elif damage == "both_deleted":
        p.unlink()
        v.witness_path.unlink()
    elif damage == "rollback":
        shutil.copyfile(backup, p)
    else:
        with sqlite3.connect(p) as db:
            if damage == "row_deleted":
                db.execute("delete from nonces")
            else:
                db.execute("update nonces set counter=9007199254740991")
    with pytest.raises(ValueError):
        v.reserve(KEY, 4)
    with pytest.raises(ValueError):
        v.register_new(KEY, 4)

    with pytest.raises(subprocess.CalledProcessError):
        node_call(
            {
                "mode": "reserve",
                "path": str(p),
                "key": KEY.hex(),
                "prefix": 4,
                "count": 1,
            }
        )


def test_crash_after_witness_requires_rotation(tmp_path):
    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    v.register_new(KEY, 4)
    with pytest.raises(RuntimeError):
        v.reserve(KEY, 4, crash_point="after_witness")
    with pytest.raises(ValueError):
        NonceVault(p).reserve(KEY, 4)


def test_actual_python_node_concurrent_processes_and_restart(tmp_path):
    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    v.register_new(KEY, 4)
    import os
    from pathlib import Path

    node = os.environ.get(
        "NODE_BIN", "E:/node/node.exe" if Path("E:/node/node.exe").exists() else "node"
    )
    commands = [
        [sys.executable, "tests/secure_sync/nonce_worker.py"],
        [node, "packages/secure-sync/test/interop.ts"],
    ] * 3
    workers = [
        subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for command in commands
    ]
    payload = json.dumps(
        {"mode": "reserve", "path": str(p), "key": KEY.hex(), "prefix": 4, "count": 20}
    )
    for process in workers:
        process.stdin.write(payload)
        process.stdin.close()
        process.stdin = None
    nonces = []
    for process in workers:
        out, err = process.communicate(timeout=40)
        assert process.returncode == 0, err
        nonces.extend(json.loads(out))
    assert len(nonces) == len(set(nonces)) == 120
    assert int.from_bytes(NonceVault(p).reserve(KEY, 4)[4:], "big") == 121
    assert (
        int(
            node_call(
                {
                    "mode": "reserve",
                    "path": str(p),
                    "key": KEY.hex(),
                    "prefix": 4,
                    "count": 1,
                }
            )[0][8:],
            16,
        )
        == 122
    )


@pytest.mark.parametrize("language", ["python", "node"])
@pytest.mark.parametrize("crash", ["after_witness", "after_commit"])
def test_actual_process_crash_windows(tmp_path, language, crash):
    import os
    from pathlib import Path

    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    v.register_new(KEY, 4)
    node = os.environ.get(
        "NODE_BIN", "E:/node/node.exe" if Path("E:/node/node.exe").exists() else "node"
    )
    command = (
        [sys.executable, "tests/secure_sync/nonce_worker.py"]
        if language == "python"
        else [node, "packages/secure-sync/test/interop.ts"]
    )
    process = subprocess.run(
        command,
        check=False,
        input=json.dumps(
            {
                "mode": "reserve",
                "path": str(p),
                "key": KEY.hex(),
                "prefix": 4,
                "count": 1,
                "crash": crash,
            }
        ),
        capture_output=True,
        text=True,
    )
    assert process.returncode == 77
    if crash == "after_witness":
        with pytest.raises(ValueError):
            NonceVault(p).reserve(KEY, 4)
    else:
        assert int.from_bytes(NonceVault(p).reserve(KEY, 4)[4:], "big") == 2


def test_node_rejects_python_witness_damage(tmp_path):
    p = tmp_path / "nonce.sqlite"
    v = NonceVault(p)
    v.register_new(KEY, 4)
    v.reserve(KEY, 4)
    v.witness_path.write_bytes(v.witness_path.read_bytes() + b"{")
    with pytest.raises(subprocess.CalledProcessError):
        node_call(
            {
                "mode": "reserve",
                "path": str(p),
                "key": KEY.hex(),
                "prefix": 4,
                "count": 1,
            }
        )
