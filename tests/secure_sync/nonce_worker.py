"""Synthetic-only subprocess crash probe. Fixed input keys never printed."""

import sys
from pathlib import Path

sys.path[:0] = [
    str(Path(__file__).resolve().parents[2]),
    str(Path(__file__).resolve().parents[2] / "apps/api"),
]
import json
import os

from researchhub.sync.secure.nonce import NonceVault

value = json.load(sys.stdin)
vault = NonceVault(value["path"])
if value.get("crash") == "after_witness":
    original = vault._append

    def crashing(identity, counter):
        original(identity, counter)
        os._exit(77)

    vault._append = crashing
nonces = []
for _ in range(value["count"]):
    nonce = vault.reserve(bytes.fromhex(value["key"]), value["prefix"])
    if value.get("crash") == "after_commit":
        os._exit(77)
    nonces.append(nonce.hex())
print(json.dumps(nonces))
