"""Disposable QA transport identity is separate from client secrets."""

import os
import stat
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization


def test_tls_is_loopback_only_and_server_mount_excludes_ca_private(
    tmp_path, monkeypatch
):
    from scripts.secure_relay_tls import generate_certificates

    monkeypatch.setenv("HUB_RELAY_QA", "1")
    material = generate_certificates(tmp_path)
    ca = x509.load_pem_x509_certificate(material["ca_certificate"].read_bytes())
    cert = x509.load_pem_x509_certificate(material["server_certificate"].read_bytes())
    ca.public_key().verify(
        cert.signature,
        cert.tbs_certificate_bytes,
        cert.signature_algorithm_parameters,
        cert.signature_hash_algorithm,
    )
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert [str(value) for value in san.get_values_for_type(x509.IPAddress)] == [
        "127.0.0.1"
    ]
    assert not san.get_values_for_type(x509.DNSName)
    assert material["server_directory"] == material["server_certificate"].parent
    assert {p.name for p in material["server_directory"].iterdir()} == {
        "server.crt",
        "server.key",
    }
    assert not any(
        "PRIVATE KEY" in p.read_text() for p in tmp_path.iterdir() if p.is_file()
    )
    key = serialization.load_pem_private_key(
        material["server_private_key"].read_bytes(), password=None
    )
    assert key.public_key().public_numbers() == cert.public_key().public_numbers()
    if os.name != "nt":
        assert stat.S_IMODE(material["server_private_key"].stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="TLS_TARGET_EXISTS"):
        generate_certificates(tmp_path)


def test_tls_requires_optin_and_ignored_runtime_path(tmp_path, monkeypatch):
    from scripts.secure_relay_tls import generate_certificates

    monkeypatch.delenv("HUB_RELAY_QA", raising=False)
    with pytest.raises(ValueError, match="QA_OPT_IN_REQUIRED"):
        generate_certificates(tmp_path)
    monkeypatch.setenv("HUB_RELAY_QA", "1")
    with pytest.raises(ValueError, match="TLS_PATH_OUTSIDE_RUNTIME"):
        generate_certificates(Path("fixtures/sync/secure-v1"))
