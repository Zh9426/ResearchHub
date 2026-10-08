import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from researchhub.sync.secure.crypto import (
    aes_decrypt,
    aes_encrypt,
    sign,
    signing_public,
    verify,
)
from researchhub.sync.secure.nonce import NonceVault

KEY = bytes(range(32))  # PUBLIC TEST ONLY


@given(
    st.binary(max_size=4096),
    st.binary(max_size=80),
    st.integers(min_value=0, max_value=4294967295),
)
@settings(max_examples=50, deadline=None)
def test_roundtrip_mutation(message, aad, prefix):
    key = os.urandom(32)
    with tempfile.TemporaryDirectory(dir="storage/runtime") as folder:
        vault = NonceVault(Path(folder) / "nonce.sqlite")
        vault.register_new(key, prefix)
        nonce = vault.reserve(key, prefix)
        ct = aes_encrypt(key, nonce, message, aad)
        assert aes_decrypt(key, nonce, ct, aad) == message
        bad = bytes([ct[0] ^ 1]) + ct[1:]
        with pytest.raises(ValueError):
            aes_decrypt(key, nonce, bad, aad)
        sig = sign(key, message)
        assert sign(key, message) == sig
        verify(signing_public(key), sig, message)


@given(st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=30))
@settings(max_examples=30, deadline=None)
def test_generated_nonce_reserve_restart_schedules(schedule):
    with tempfile.TemporaryDirectory(dir="storage/runtime") as folder:
        path = Path(folder) / "nonce.sqlite"
        vault = NonceVault(path)
        vault.register_new(KEY, 7)
        seen = set()
        for command in schedule:
            if command == 0:
                vault = NonceVault(path)
            nonce = vault.reserve(KEY, 7)
            assert nonce not in seen
            seen.add(nonce)
        assert len(seen) == len(schedule)
