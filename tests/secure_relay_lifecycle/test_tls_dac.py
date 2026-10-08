"""Real Linux Docker DAC boundary with public sentinel, never runtime TLS bytes."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_tls_copy_helper_reads_foreign_uid_0600_without_changing_mode():
    assert os.environ.get("HUB_RELAY_QA") == "1"
    spec = importlib.util.spec_from_file_location(
        "qa_tls_dac", ROOT / "scripts/secure-relay-qa.py"
    )
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    images = (
        q.docker(
            "image",
            "ls",
            "--filter",
            "reference=researchhub-relay-qa:*",
            "--format",
            "{{.ID}}",
        )
        .decode()
        .splitlines()
    )
    assert images, "Build the QA relay image before the sentinel test"
    image = q.inspect("image", images[0])["Id"]
    volume = "researchhub-tls-dac-sentinel-" + str(uuid4())
    label = "researchhub.qa.scope=tls-dac-sentinel"
    q.docker("volume", "create", "--label", label, volume)

    def sentinel(caps, command, *, readonly=True):
        return q.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            *(arg for cap in caps for arg in ("--cap-add", cap)),
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,source={volume},target=/probe"
            + (",readonly" if readonly else ""),
            "--user",
            "0:0",
            "--entrypoint",
            "python",
            image,
            "-c",
            command,
        )

    try:
        sentinel(
            ("CHOWN",),
            "import os,pathlib; p=pathlib.Path('/probe/sentinel'); p.write_text('SYNTHETIC_PUBLIC_SENTINEL'); os.chmod(p,0o600); os.chown(p,1000,1000)",
            readonly=False,
        )
        read = "import pathlib,stat; p=pathlib.Path('/probe/sentinel'); assert p.stat().st_uid==1000; assert stat.S_IMODE(p.stat().st_mode)==0o600; assert p.read_text()=='SYNTHETIC_PUBLIC_SENTINEL'"
        with pytest.raises(RuntimeError, match="^QA_DOCKER_RUN_FAILED$"):
            sentinel(("CHOWN",), read)
        sentinel(q.TLS_COPY_CAPABILITIES, read)
        # Read/search capability must not grant write access even on a RW mount.
        denied_write = "import pathlib; p=pathlib.Path('/probe/sentinel'); p.write_text('SHOULD_NOT_WRITE')"
        with pytest.raises(RuntimeError, match="^QA_DOCKER_RUN_FAILED$"):
            sentinel(q.TLS_COPY_CAPABILITIES, denied_write, readonly=False)
        sentinel(q.TLS_COPY_CAPABILITIES, read)
    finally:
        metadata = q.inspect("volume", volume)
        assert metadata["Name"] == volume
        assert metadata["Labels"]["researchhub.qa.scope"] == "tls-dac-sentinel"
        q.docker("volume", "rm", volume)
        assert q.inspect("volume", volume) is None
