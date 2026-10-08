"""Ephemeral loopback QA TLS; the CA signing key never leaves memory."""

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

RUNTIME = Path(__file__).resolve().parents[1] / "storage/runtime"


def generate_certificates(directory: Path):
    if os.environ.get("HUB_RELAY_QA") != "1":
        raise ValueError("QA_OPT_IN_REQUIRED")
    directory = Path(directory).resolve()
    if (
        not directory.is_relative_to(RUNTIME.resolve())
        or directory == RUNTIME.resolve()
    ):
        raise ValueError("TLS_PATH_OUTSIDE_RUNTIME")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("TLS_TARGET_EXISTS")
    directory.mkdir(parents=True, exist_ok=True)
    server_directory = directory / "server"
    server_directory.mkdir()
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "ResearchHub synthetic QA CA")]
    )
    server_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "ResearchHub loopback QA Relay")]
    )

    def builder(subject, issuer, public_key):
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=2))
        )

    ca = (
        builder(ca_name, ca_name, ca_key.public_key())
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    server = (
        builder(server_name, ca_name, server_key.public_key())
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.KeyUsage(True, False, True, False, False, False, False, False, False),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    paths = {
        "ca_certificate": directory / "ca.crt",
        "server_certificate": server_directory / "server.crt",
        "server_private_key": server_directory / "server.key",
        "server_directory": server_directory,
    }
    paths["ca_certificate"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths["server_certificate"].write_bytes(
        server.public_bytes(serialization.Encoding.PEM)
    )
    with paths["server_private_key"].open("xb") as stream:
        os.chmod(paths["server_private_key"], 0o600)
        stream.write(
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        stream.flush()
        os.fsync(stream.fileno())
    return paths
