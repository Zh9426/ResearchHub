"""Real Docker failed init cleanup; run explicitly before normal network suite."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("point", ["tls_helper", "ingress_create", "ingress_connect"])
def test_partial_initialization_has_exact_owned_cleanup(point):
    assert os.environ.get("HUB_RELAY_QA") == "1"
    spec = importlib.util.spec_from_file_location(
        "qa", ROOT / "scripts/secure-relay-qa.py"
    )
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    assert not q.STATE.exists(), "Destroy current owned run before lifecycle tests"
    value = q.config()
    pg = q.guard_pg(value)
    before = pg["Id"] if pg else None
    docker = q.docker

    def inject(*args, **kwargs):
        values = list(args)
        if (
            values[0] == "create"
            and point == "tls_helper"
            and any(str(x).startswith("researchhub-relay-tls-init-") for x in values)
        ):
            values[-1] = "raise SystemExit(7)"
        if values[0] == "create" and point == "ingress_create" and q.INGRESS in values:
            values[-1] = "invalid@@"
        if (
            values[:3] == ["network", "connect", q.DATA]
            and point == "ingress_connect"
            and values[-1] != q.PG
        ):
            values[2:2] = ["--ip", "invalid"]
        return docker(*values, **kwargs)

    q.docker = inject
    with pytest.raises(RuntimeError, match="QA_DOCKER_"):
        q.initialize(value)
    q.docker = docker
    assert q.STATE.exists(), "Failed init must retain exact resource ownership"
    state = json.loads(q.STATE.read_text())
    assert state["phase"] == "initializing"
    q.guard_partial(state, value)
    ids = list(state["containers"].values()) + (
        [state["helper_id"]] if "helper_id" in state else []
    )
    q.destroy(state, value)
    assert not q.STATE.exists()
    assert not Path(state["tls_directory"]).exists()
    assert q.inspect("volume", state["tls_volume"]) is None
    assert all(q.inspect("container", id_) is None for id_ in ids)
    if before:
        assert q.guard_pg(value, id_=before)["Id"] == before
        q.readiness(value)
