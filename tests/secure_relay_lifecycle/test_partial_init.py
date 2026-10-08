"""Real Docker failed init cleanup; run explicitly before normal network suite."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_partial_initialization(point, *, earlier_failure=False):
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
    reached = []

    def inject(*args, **kwargs):
        values = list(args)
        if (
            values[0] == "create"
            and (point == "tls_helper" or earlier_failure)
            and any(str(x).startswith("researchhub-relay-tls-init-") for x in values)
        ):
            values[-1] = "raise SystemExit(7)"
            if point == "tls_helper":
                reached.append(point)
        if values[0] == "create" and point == "ingress_create" and q.INGRESS in values:
            values[-1] = "invalid@@"
            reached.append(point)
        if (
            values[:3] == ["network", "connect", q.DATA]
            and point == "ingress_connect"
            and values[-1] != q.PG
        ):
            values[2:2] = ["--ip", "invalid"]
            reached.append(point)
        return docker(*values, **kwargs)

    q.docker = inject
    with pytest.raises(RuntimeError, match="QA_DOCKER_") as failure:
        q.initialize(value)
    q.docker = docker
    assert q.STATE.exists(), "Failed init must retain exact resource ownership"
    state = json.loads(q.STATE.read_text())
    assert state["phase"] == "initializing"
    q.guard_partial(state, value)
    if state.get("helper_id"):
        inspect = q.inspect

        def changed_caps(kind, name):
            result = inspect(kind, name)
            if kind == "container" and name == state["helper_id"]:
                result = {
                    **result,
                    "HostConfig": {**result["HostConfig"], "CapAdd": caps},
                }
            return result

        q.inspect = changed_caps
        try:
            caps = ["CAP_" + cap for cap in q.TLS_COPY_CAPABILITIES]
            q.guard_partial(state, value)
            for caps in (["CHOWN"], [*q.TLS_COPY_CAPABILITIES, "DAC_OVERRIDE"]):
                with pytest.raises(RuntimeError, match="^QA_HELPER_REJECTED$"):
                    q.guard_partial(state, value)
        finally:
            q.inspect = inspect
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
    # Check after exact cleanup so an earlier failure cannot leave test resources.
    assert reached == [point], "REQUESTED_FAULT_NOT_REACHED"
    expected = {
        "tls_helper": "START",
        "ingress_create": "CREATE",
        "ingress_connect": "NETWORK",
    }
    assert str(failure.value) == "QA_DOCKER_" + expected[point] + "_FAILED"


@pytest.mark.parametrize("point", ["tls_helper", "ingress_create", "ingress_connect"])
def test_partial_initialization_has_exact_owned_cleanup(point):
    run_partial_initialization(point)


@pytest.mark.parametrize("point", ["ingress_create", "ingress_connect"])
def test_earlier_helper_failure_cannot_pass_later_fault_injection(point):
    with pytest.raises(AssertionError, match="REQUESTED_FAULT_NOT_REACHED"):
        run_partial_initialization(point, earlier_failure=True)
