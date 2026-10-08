"""Owned synthetic loopback lifecycle; captures Docker diagnostics without secrets."""

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "storage/runtime/secure-relay-qa.json"
ENV_FILE = ROOT / ".env.secure-relay-qa"
STATE = ROOT / "storage/runtime/secure-relay-run.json"
SCOPE, PG = "secure-relay-s2", "researchhub-secure-relay-pg"
RELAY, INGRESS = "researchhub-secure-relay", "researchhub-secure-relay-ingress"
DATA, TRANSPORT = "researchhub-secure-relay-qa", "researchhub-secure-relay-transport-qa"
DB, USER = "researchhub_secure_relay_qa", "researchhub_relay_qa"
LABEL, RUNLABEL = "researchhub.qa.scope", "researchhub.qa.run"


class QAConfig(dict):
    def __repr__(self):
        return "QAConfig(<service credentials redacted>)"


def docker(*args, missing=False):
    result = subprocess.run(
        ["docker", *args], capture_output=True, timeout=180, check=False
    )
    if result.returncode:
        if missing and (
            b"no such" in result.stderr.lower() or b"not found" in result.stderr.lower()
        ):
            return None
        raise RuntimeError("QA_DOCKER_" + args[0].upper().replace("-", "_") + "_FAILED")
    return result.stdout


def inspect(kind, name):
    raw = (
        docker(kind, "inspect", name, missing=True)
        if kind != "container"
        else docker("inspect", name, missing=True)
    )
    return json.loads(raw)[0] if raw else None


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def write_env(value):
    ENV_FILE.write_text(
        f"POSTGRES_DB={DB}\nPOSTGRES_USER={USER}\nPOSTGRES_PASSWORD={value['password']}\n",
        encoding="utf-8",
    )
    os.chmod(ENV_FILE, 0o600)


def config():
    if os.environ.get("HUB_RELAY_QA") != "1":
        raise RuntimeError("QA_OPT_IN_REQUIRED")
    if not CONFIG.exists():
        if ENV_FILE.exists():
            raise RuntimeError("QA_CONFIG_MISSING")
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "scope": SCOPE,
            "container": PG,
            "database": DB,
            "username": USER,
            "password": secrets.token_hex(32),
            "host": "127.0.0.1",
            "port": 35434,
        }
        write_json(CONFIG, value)
        write_env(value)
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    if (
        tuple(
            value.get(k)
            for k in ("scope", "container", "database", "username", "host", "port")
        )
        != (SCOPE, PG, DB, USER, "127.0.0.1", 35434)
        or not isinstance(value.get("password"), str)
        or len(value["password"]) != 64
    ):
        raise RuntimeError("QA_CONFIG_REJECTED")
    expected = f"POSTGRES_DB={DB}\nPOSTGRES_USER={USER}\nPOSTGRES_PASSWORD={value['password']}\n"
    if not ENV_FILE.exists() or ENV_FILE.read_text(encoding="utf-8") != expected:
        raise RuntimeError("QA_ENV_REJECTED")
    return QAConfig(value)


def labels(run=None):
    return ["--label", f"{LABEL}={SCOPE}"] + (
        ["--label", f"{RUNLABEL}={run}"] if run else []
    )


def guard_network(name, *, id_=None, allowed=()):
    net = inspect("network", name)
    if (
        net is None
        or net["Labels"].get(LABEL) != SCOPE
        or net["Driver"] != "bridge"
        or net["Internal"] != (name == DATA)
        or (id_ and net["Id"] != id_)
    ):
        raise RuntimeError("QA_NETWORK_REJECTED")
    if set(net.get("Containers", {})) - set(allowed):
        raise RuntimeError("QA_NETWORK_UNKNOWN_MEMBER")
    if net.get("Options") not in (
        {},
        {
            "com.docker.network.enable_ipv4": "true",
            "com.docker.network.enable_ipv6": "false",
        },
    ) or net.get("EnableIPv6"):
        raise RuntimeError("QA_NETWORK_OPTIONS_REJECTED")
    return net


def guard_privileges(obj, *, hardened):
    host = obj["HostConfig"]
    if (
        host["Privileged"]
        or host["NetworkMode"] == "host"
        or host["PidMode"]
        or host["IpcMode"] not in ("private", "")
        or host.get("CapAdd")
        or host.get("Devices")
        or host.get("DeviceRequests")
        or host.get("VolumesFrom")
        or host.get("Links")
        or host.get("ExtraHosts")
        or host["PublishAllPorts"]
    ):
        raise RuntimeError("QA_PRIVILEGE_REJECTED")
    if hardened and (
        not host["ReadonlyRootfs"]
        or host["CapDrop"] != ["ALL"]
        or "no-new-privileges" not in " ".join(host.get("SecurityOpt") or ())
        or obj["Config"]["User"] != "10001:10001"
        or host.get("PidsLimit") != 128
        or host.get("Memory") != 268435456
    ):
        raise RuntimeError("QA_HARDENING_REJECTED")


def guard_pg(value, *, id_=None, initial=False):
    obj = inspect("container", PG)
    if obj is None:
        return None
    cfg, host = obj["Config"], obj["HostConfig"]
    env = dict(v.split("=", 1) for v in cfg["Env"])
    nets, mounts = set(obj["NetworkSettings"]["Networks"]), obj["Mounts"]
    allowed = ({DATA, TRANSPORT},)
    id_ = id_ or value.get("pg_id")
    # POSTGRES_PASSWORD may be the original bootstrap value after an ALTER ROLE;
    # actual authentication is checked separately. No Env values are displayed.
    if (
        cfg["Labels"].get(LABEL) != SCOPE
        or (id_ and obj["Id"] != id_)
        or cfg["Image"] != "postgres:17.11-bookworm"
        or cfg["Entrypoint"] != ["docker-entrypoint.sh"]
        or cfg["Cmd"] != ["postgres"]
        or env.get("POSTGRES_DB") != DB
        or env.get("POSTGRES_USER") != USER
        or nets not in allowed
        or host["PortBindings"]
        != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "35434"}]}
        or len(mounts) != 1
        or mounts[0]["Type"] != "volume"
        or mounts[0]["Destination"] != "/var/lib/postgresql/data"
        or not mounts[0]["RW"]
    ):
        raise RuntimeError("QA_PG_REJECTED")
    guard_privileges(obj, hardened=False)
    if any(v.get("Aliases") for v in obj["NetworkSettings"]["Networks"].values()):
        raise RuntimeError("QA_PG_ALIAS_REJECTED")
    if value.get("pg_volume") and mounts[0]["Name"] != value["pg_volume"]:
        raise RuntimeError("QA_PG_VOLUME_REJECTED")
    return obj


def guard_service(state, name):
    obj = inspect("container", name)
    if (
        obj is None
        or obj["Id"] != state["containers"][name]
        or obj["Config"]["Labels"].get(LABEL) != SCOPE
        or obj["Config"]["Labels"].get(RUNLABEL) != state["run"]
    ):
        raise RuntimeError("QA_SERVICE_ID_REJECTED")
    guard_privileges(obj, hardened=True)
    nets, host = set(obj["NetworkSettings"]["Networks"]), obj["HostConfig"]
    if name == RELAY:
        if (
            nets != {DATA}
            or host["PortBindings"]
            or len(obj["Mounts"]) != 1
            or obj["Mounts"][0]["Type"] != "volume"
            or obj["Mounts"][0]["Name"] != state["tls_volume"]
            or obj["Mounts"][0]["Destination"] != "/tls"
            or obj["Mounts"][0]["RW"]
        ):
            raise RuntimeError("QA_RELAY_TOPOLOGY_REJECTED")
        if set(obj["NetworkSettings"]["Networks"][DATA].get("Aliases") or []) != {
            RELAY
        }:
            raise RuntimeError("QA_RELAY_ALIAS_REJECTED")
    elif (
        nets
        != (
            {TRANSPORT}
            if state.get("phase") == "initializing"
            and not state.get("ingress_connected")
            else {DATA, TRANSPORT}
        )
        or host["PortBindings"]
        != {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "38001"}]}
        or obj["Mounts"]
    ):
        raise RuntimeError("QA_INGRESS_TOPOLOGY_REJECTED")
    if obj["Image"] != state["images"][name]:
        raise RuntimeError("QA_IMAGE_REJECTED")
    image = inspect("image", obj["Image"])["Config"]
    expected_env = dict(v.split("=", 1) for v in image["Env"])
    if name == RELAY:
        expected_env.update(
            HUB_RELAY_QA="1",
            HUB_RELAY_QA_PROFILE="container",
            HUB_RELAY_QA_DATABASE_URL=url(config(), container=True),
            HUB_RELAY_QA_FAULT_DIR="/fault",
        )
    actual_env = dict(v.split("=", 1) for v in obj["Config"]["Env"])
    if (
        actual_env != expected_env
        or obj["Config"]["Cmd"] != image["Cmd"]
        or obj["Config"].get("Entrypoint") != image.get("Entrypoint")
    ):
        raise RuntimeError("QA_SERVICE_CONFIG_REJECTED")
    expected_tmpfs = (
        {"/fault": "rw,noexec,nosuid,size=1m,uid=10001,gid=10001,mode=0700"}
        if name == RELAY
        else {}
    )
    if (host.get("Tmpfs") or {}) != expected_tmpfs:
        raise RuntimeError("QA_TMPFS_REJECTED")
    if name == INGRESS and any(
        v.get("Aliases") for v in obj["NetworkSettings"]["Networks"].values()
    ):
        raise RuntimeError("QA_INGRESS_ALIAS_REJECTED")
    return obj


def guard_state(state, value):
    guard_partial(state, value)
    if set(state["containers"]) != {RELAY, INGRESS} or set(state["networks"]) != {
        DATA,
        TRANSPORT,
    }:
        raise RuntimeError("QA_STATE_INCOMPLETE")
    if state["scope"] != SCOPE or state["pg"]["name"] != PG:
        raise RuntimeError("QA_STATE_REJECTED")
    pg = guard_pg(value, id_=state["pg"]["id"])
    if pg is None or pg["Mounts"][0]["Name"] != state["pg"]["volume"]:
        raise RuntimeError("QA_PG_VOLUME_REJECTED")
    known = [pg["Id"], *state["containers"].values()]
    for name in (DATA, TRANSPORT):
        guard_network(name, id_=state["networks"][name]["id"], allowed=known)
    for name in state["containers"]:
        guard_service(state, name)
    volume = inspect("volume", state["tls_volume"])
    if (
        volume is None
        or volume["Labels"].get(LABEL) != SCOPE
        or volume["Labels"].get(RUNLABEL) != state["run"]
        or volume["Driver"] != "local"
        or volume.get("Options")
    ):
        raise RuntimeError("QA_TLS_VOLUME_REJECTED")


def guard_partial(state, value):
    """Validate only exact journaled resources; never discover by label to delete."""
    if state.get("scope") != SCOPE or str(UUID(state["run"])) != state["run"]:
        raise RuntimeError("QA_STATE_REJECTED")
    if (
        state["pg"].get("name") != PG
        or type(state["pg"].get("created")) is not bool
        or set(state["containers"]) - {RELAY, INGRESS}
        or set(state["networks"]) - {DATA, TRANSPORT}
    ):
        raise RuntimeError("QA_STATE_REJECTED")
    if (
        state["tls_volume"] != "researchhub-relay-tls-" + state["run"]
        or Path(state["tls_directory"]).resolve()
        != (ROOT / "storage/runtime" / ("secure-relay-tls-" + state["run"])).resolve()
    ):
        raise RuntimeError("QA_TLS_CLEANUP_REJECTED")
    if (
        "relay_env" in state
        and Path(state["relay_env"]).resolve()
        != (
            ROOT
            / "storage/runtime"
            / ("secure-relay-container-" + state["run"] + ".env")
        ).resolve()
    ):
        raise RuntimeError("QA_ENV_CLEANUP_REJECTED")
    pg = guard_pg(value, id_=state["pg"].get("id"))
    if pg is None or pg["Mounts"][0]["Name"] != state["pg"].get("volume"):
        raise RuntimeError("QA_PG_VOLUME_REJECTED")
    known = [pg["Id"], *state["containers"].values()]
    for name, network in state["networks"].items():
        guard_network(name, id_=network["id"], allowed=known)
    for name in state["containers"]:
        guard_service(state, name)
    if state.get("tls_created"):
        volume = inspect("volume", state["tls_volume"])
        if (
            volume is None
            or volume["Labels"].get(LABEL) != SCOPE
            or volume["Labels"].get(RUNLABEL) != state["run"]
            or volume["Driver"] != "local"
            or volume.get("Options")
        ):
            raise RuntimeError("QA_TLS_VOLUME_REJECTED")
    if state.get("helper_id"):
        helper = inspect("container", state["helper_id"])
        host = helper["HostConfig"] if helper else {}
        mounts = helper["Mounts"] if helper else []
        if (
            helper is None
            or helper["Id"] != state["helper_id"]
            or helper["Config"]["Labels"].get(LABEL) != SCOPE
            or helper["Config"]["Labels"].get(RUNLABEL) != state["run"]
            or helper["Image"] != state["images"][RELAY]
            or host.get("NetworkMode") != "none"
            or host.get("Privileged")
            or host.get("CapAdd") not in (["CHOWN"], ["CAP_CHOWN"])
            or host.get("CapDrop") != ["ALL"]
            or not host.get("ReadonlyRootfs")
            or host.get("PortBindings")
            or len(mounts) != 2
        ):
            raise RuntimeError("QA_HELPER_REJECTED")
        if not any(
            m["Type"] == "bind"
            and Path(m["Source"]).resolve()
            == Path(state["tls_directory"]).resolve() / "server"
            and m["Destination"] == "/source"
            and not m["RW"]
            for m in mounts
        ) or not any(
            m["Type"] == "volume"
            and m["Name"] == state["tls_volume"]
            and m["Destination"] == "/target"
            and m["RW"]
            for m in mounts
        ):
            raise RuntimeError("QA_HELPER_MOUNT_REJECTED")


def url(value, *, container=False):
    from sqlalchemy import URL

    return URL.create(
        "postgresql+psycopg",
        username=USER,
        password=value["password"],
        host=PG if container else "127.0.0.1",
        port=5432 if container else 35434,
        database=DB,
    ).render_as_string(hide_password=False)


def readiness(value):
    sys.path[:0] = [str(ROOT), str(ROOT / "apps/relay")]
    from researchhub_relay.qa import connect

    for _ in range(80):
        try:
            engine = connect(url(value), profile="host")
            engine.dispose()
            return
        except Exception:  # noqa: BLE001 -- bounded readiness retry; never disclose credentials
            time.sleep(0.25)
    raise RuntimeError("QA_PG_UNAVAILABLE")


def initialize(value):
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if state.get("phase") != "ready":
            guard_partial(state, value)
            raise RuntimeError("QA_INIT_INCOMPLETE_USE_DESTROY")
        guard_state(state, value)
        for name in (PG, RELAY, INGRESS):
            docker(
                "start", state["pg"]["id"] if name == PG else state["containers"][name]
            )
        readiness(value)
        return state
    for name in (RELAY, INGRESS):
        if inspect("container", name):
            raise RuntimeError("QA_UNOWNED_SERVICE_EXISTS")
    pg = guard_pg(value, initial=True)
    known, run = [pg["Id"]] if pg else [], str(uuid4())
    state = {
        "scope": SCOPE,
        "run": run,
        "containers": {},
        "networks": {},
        "images": {},
        "tls_volume": "researchhub-relay-tls-" + run,
        "tls_directory": str(ROOT / "storage/runtime" / ("secure-relay-tls-" + run)),
        "pg": {"name": PG, "created": pg is None},
    }
    for name in (DATA, TRANSPORT):
        existing = inspect("network", name)
        if existing:
            net = guard_network(name, allowed=known)
        else:
            docker(
                "network",
                "create",
                *labels(),
                *(["--internal"] if name == DATA else []),
                name,
            )
            net = guard_network(name)
        state["networks"][name] = {"id": net["Id"], "created": existing is None}
    if pg:
        docker("start", pg["Id"])
    else:
        docker(
            "run",
            "-d",
            "--name",
            PG,
            *labels(run),
            "--env-file",
            str(ENV_FILE),
            "--network",
            TRANSPORT,
            "-p",
            "127.0.0.1:35434:5432",
            "postgres:17.11-bookworm",
        )
        docker("network", "connect", DATA, PG)
    pg = guard_pg(value)
    state["pg"].update(id=pg["Id"], volume=pg["Mounts"][0]["Name"])
    value.update(pg_id=pg["Id"], pg_volume=pg["Mounts"][0]["Name"])
    write_json(CONFIG, value)
    state["phase"] = "initializing"
    write_json(STATE, state)
    readiness(value)
    spec = importlib.util.spec_from_file_location(
        "qa_tls", ROOT / "scripts/secure_relay_tls.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = module.generate_certificates(Path(state["tls_directory"]))
    for name, file, tag in (
        (RELAY, "apps/relay/Dockerfile", "researchhub-relay-qa:"),
        (INGRESS, "apps/relay/ingress/Dockerfile", "researchhub-relay-ingress-qa:"),
    ):
        docker("build", "-q", "-f", file, "-t", tag + run, ".")
        state["images"][name] = inspect("image", tag + run)["Id"]
        write_json(STATE, state)
    docker("volume", "create", *labels(run), state["tls_volume"])
    state["tls_created"] = True
    write_json(STATE, state)
    helper = "researchhub-relay-tls-init-" + run
    command = "import pathlib,os; a=pathlib.Path('/source'); b=pathlib.Path('/target'); assert sorted(p.name for p in a.iterdir())==['server.crt','server.key']; [(b/n).write_bytes((a/n).read_bytes()) for n in ('server.crt','server.key')]; os.chmod(b/'server.key',0o600); os.chmod(b/'server.crt',0o644); os.chown(b/'server.key',10001,10001)"
    helper_id = (
        docker(
            "create",
            "--name",
            helper,
            *labels(run),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=bind,source={paths['server_directory']},target=/source,readonly",
            "--mount",
            f"type=volume,source={state['tls_volume']},target=/target",
            "--user",
            "0:0",
            "--entrypoint",
            "python",
            state["images"][RELAY],
            "-c",
            command,
        )
        .decode()
        .strip()
    )
    state["helper_id"] = helper_id
    write_json(STATE, state)
    docker("start", "-a", helper_id)
    helper_obj = inspect("container", helper_id)
    if (
        helper_obj["Id"] != helper_id
        or helper_obj["Config"]["Labels"].get(RUNLABEL) != run
        or helper_obj["State"]["ExitCode"] != 0
    ):
        raise RuntimeError("QA_TLS_INIT_FAILED")
    docker("rm", helper_id)
    state.pop("helper_id")
    write_json(STATE, state)
    relay_env = ROOT / "storage/runtime" / ("secure-relay-container-" + run + ".env")
    relay_env.write_text(
        "HUB_RELAY_QA=1\nHUB_RELAY_QA_PROFILE=container\nHUB_RELAY_QA_DATABASE_URL="
        + url(value, container=True)
        + "\nHUB_RELAY_QA_FAULT_DIR=/fault\n",
        encoding="utf-8",
    )
    os.chmod(relay_env, 0o600)
    state["relay_env"] = str(relay_env)
    write_json(STATE, state)
    hardened = [
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "256m",
        "--user",
        "10001:10001",
        "--log-driver",
        "local",
        "--log-opt",
        "max-size=1m",
        "--log-opt",
        "max-file=2",
    ]
    relay_id = (
        docker(
            "create",
            "--name",
            RELAY,
            *labels(run),
            *hardened,
            "--network",
            DATA,
            "--network-alias",
            RELAY,
            "--mount",
            f"type=volume,source={state['tls_volume']},target=/tls,readonly",
            "--tmpfs",
            "/fault:rw,noexec,nosuid,size=1m,uid=10001,gid=10001,mode=0700",
            "--env-file",
            str(relay_env),
            state["images"][RELAY],
        )
        .decode()
        .strip()
    )
    state["containers"][RELAY] = relay_id
    write_json(STATE, state)
    ingress_id = (
        docker(
            "create",
            "--name",
            INGRESS,
            *labels(run),
            *hardened,
            "--network",
            TRANSPORT,
            "-p",
            "127.0.0.1:38001:8443",
            state["images"][INGRESS],
        )
        .decode()
        .strip()
    )
    state["containers"][INGRESS] = ingress_id
    state["ingress_connected"] = False
    write_json(STATE, state)
    docker("network", "connect", DATA, ingress_id)
    state["ingress_connected"] = True
    write_json(STATE, state)
    guard_state(state, value)
    state["phase"] = "ready"
    write_json(STATE, state)
    docker("start", relay_id)
    docker("start", ingress_id)
    return state


def wait_tls(state):
    import httpx

    context = ssl.create_default_context(
        cafile=str(Path(state["tls_directory"]) / "ca.crt")
    )
    for _ in range(100):
        try:
            response = httpx.get(
                "https://127.0.0.1:38001/v1/hello",
                verify=context,
                trust_env=False,
                timeout=1,
            )
            if response.status_code == 401:
                return
        except httpx.TransportError:
            response = None
        time.sleep(0.2)
    raise RuntimeError("QA_TLS_UNAVAILABLE")


def destroy(state, value):
    guard_partial(state, value)
    if state.get("helper_id"):
        docker("rm", "-f", state["helper_id"])
    for name in (INGRESS, RELAY):
        if name not in state["containers"]:
            continue
        guard_service(state, name)
        docker("rm", "-f", state["containers"][name])
        state["containers"].pop(name)
    if state.get("tls_created"):
        docker("volume", "rm", state["tls_volume"])
    if state["pg"]["created"]:
        obj = guard_pg(value, id_=state["pg"]["id"])
        if obj["Config"]["Labels"].get(RUNLABEL) != state["run"]:
            raise RuntimeError("QA_PG_OWNER_REJECTED")
        docker("rm", "-f", obj["Id"])
        docker("volume", "rm", state["pg"]["volume"])
        value.pop("pg_id", None)
        value.pop("pg_volume", None)
        write_json(CONFIG, value)
    for name in (DATA, TRANSPORT):
        if state["networks"][name]["created"]:
            net = guard_network(
                name,
                id_=state["networks"][name]["id"],
                allowed=() if state["pg"]["created"] else (state["pg"]["id"],),
            )
            if not net["Containers"]:
                docker("network", "rm", net["Id"])
    tls = Path(state["tls_directory"]).resolve()
    expected = (
        ROOT / "storage/runtime" / ("secure-relay-tls-" + state["run"])
    ).resolve()
    if tls != expected or not tls.is_relative_to((ROOT / "storage/runtime").resolve()):
        raise RuntimeError("QA_TLS_CLEANUP_REJECTED")
    if tls.exists():
        shutil.rmtree(tls)
    if "relay_env" in state:
        env = Path(state["relay_env"]).resolve()
        if (
            env
            != (
                ROOT
                / "storage/runtime"
                / ("secure-relay-container-" + state["run"] + ".env")
            ).resolve()
        ):
            raise RuntimeError("QA_ENV_CLEANUP_REJECTED")
        env.unlink(missing_ok=True)
    STATE.unlink()


def preflight_client():
    """Fail before either destructive QA fixture if client PG opt-in is missing."""
    if any(os.environ.get(name) != "1" for name in ("HUB_RELAY_QA", "HUB_SYNC_QA")):
        raise RuntimeError("QA_BOTH_RELAY_AND_SYNC_OPTINS_REQUIRED")
    sys.path[:0] = [str(ROOT), str(ROOT / "apps/api")]
    from researchhub.sync.secure.transport_pg import client_engine

    engine = client_engine()
    engine.dispose()


def run_test_cohorts(state):
    """Preserve fixed 64-project quota and each cohort's complete privacy evidence."""
    import xml.etree.ElementTree as ET

    preflight_client()
    files = sorted((ROOT / "tests/secure_relay").glob("test_*.py"))
    cohorts = {
        "relay": [str(p) for p in files if not p.name.startswith("test_transport")],
        "client": [str(p) for p in files if p.name.startswith("test_transport")],
    }
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (
                str(ROOT),
                str(ROOT / "apps/api"),
                str(ROOT / "apps/relay"),
                str(Path(__file__).parent),
            )
        ),
    }
    # User process/global settings are preserved; only complete QA subprocesses
    # ignore inherited selectors and pytest.ini addopts.
    env.pop("PYTEST_ADDOPTS", None)
    runtime = ROOT / "storage/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    summaries = []
    trial = str(uuid4())
    for name, paths in cohorts.items():
        if not paths:
            raise RuntimeError("QA_EMPTY_COHORT")
        invocation = str(uuid4())
        evidence_id = state["run"] + "-" + trial + "-" + name
        junit = runtime / ("secure-relay-tests-" + evidence_id + ".xml")
        collection_path = runtime / ("secure-relay-collection-" + evidence_id + ".json")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *paths,
                "-q",
                "-o",
                "addopts=",
                "-p",
                "secure_relay_pytest",
                "--rh-collection-report",
                str(collection_path),
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(runtime / ("secure-relay-pytest-" + evidence_id)),
                "--junitxml",
                str(junit),
            ],
            env={
                **env,
                "HUB_QA_TRIAL": trial,
                "HUB_QA_COHORT": name,
                "HUB_QA_INVOCATION": invocation,
                "HUB_QA_SERVICE_RUN": state["run"],
            },
            check=False,
        )
        if result.returncode:
            return (
                result.returncode
            )  # Never clear failed cohort evidence by continuing.
        try:
            privacy = json.loads(
                (runtime / "secure-relay-privacy-result.json").read_text()
            )
        except (OSError, ValueError):
            raise RuntimeError("QA_PRIVACY_EVIDENCE_REQUIRED") from None
        if (
            privacy.get("audit_version") != 2
            or privacy.get("hits") != 0
            or any(
                privacy.get(field) != value
                for field, value in {
                    "run": state["run"],
                    "trial": trial,
                    "cohort": name,
                    "invocation": invocation,
                }.items()
            )
        ):
            raise RuntimeError("QA_PRIVACY_EVIDENCE_REQUIRED")
        evidence = runtime / ("secure-relay-privacy-" + evidence_id + ".json")
        evidence.write_text(json.dumps(privacy), encoding="utf-8")
        suite = ET.parse(junit).getroot().find("testsuite")
        if suite is None or any(
            int(suite.get(field, "0")) for field in ("errors", "failures", "skipped")
        ):
            raise RuntimeError("QA_COMPLETE_COHORT_REQUIRED")
        count = int(suite.get("tests", "0"))
        try:
            collection = json.loads(collection_path.read_text())
        except (OSError, ValueError):
            raise RuntimeError("QA_COMPLETE_COHORT_REQUIRED") from None
        expected_context = {
            "run": state["run"],
            "trial": trial,
            "cohort": name,
            "invocation": invocation,
        }
        if (
            count <= 0
            or any(collection.get(k) != v for k, v in expected_context.items())
            or (
                collection.get("selected") != count
                or collection.get("executed") != count
                or collection.get("deselected") != 0
                or collection.get("exitstatus") != 0
                or collection.get("collected_paths")
                != sorted(str(Path(p).resolve()) for p in paths)
            )
        ):
            raise RuntimeError("QA_COMPLETE_COHORT_REQUIRED")
        summaries.append(
            {
                "name": name,
                "tests": int(suite.get("tests", "0")),
                "collection_file": collection_path.name,
                "collection": collection,
                "privacy_file": evidence.name,
                "privacy": privacy,
            }
        )
        (
            runtime
            / ("secure-relay-suite-result-" + state["run"] + "-" + trial + ".json")
        ).write_text(
            json.dumps(
                {
                    "scope": "SYNTHETIC_LOOPBACK_ONLY",
                    "trial": trial,
                    "cohorts": summaries,
                }
            ),
            encoding="utf-8",
        )
    return 0


def main():
    parser = argparse.ArgumentParser()
    for flag in ("init", "start", "test", "stop", "destroy", "status"):
        parser.add_argument("--" + flag, action="store_true")
    parser.add_argument("--restart", choices=("relay", "ingress", "pg"))
    parser.add_argument("--kill", choices=("relay", "ingress", "pg"))
    args = parser.parse_args()
    os.chdir(ROOT)
    value = config()
    if args.init or args.start:
        state = initialize(value)
        wait_tls(state)
        print("QA_READY TLS:127.0.0.1:38001 PG:127.0.0.1:35434")
    if not STATE.exists():
        if args.destroy:
            print("QA_ALREADY_DESTROYED")
            return 0
        raise RuntimeError("QA_RUN_STATE_REQUIRED")
    state = json.loads(STATE.read_text())
    if args.destroy:
        destroy(state, value)
        print("QA_OWNED_RESOURCES_REMOVED existing_PG_and_unrelated_services_retained")
        return 0
    guard_state(state, value)
    if args.restart or args.kill:
        name = {"relay": RELAY, "ingress": INGRESS, "pg": PG}[args.restart or args.kill]
        docker(
            "restart" if args.restart else "kill",
            state["pg"]["id"] if name == PG else state["containers"][name],
        )
        if args.restart:
            readiness(value)
            wait_tls(state)
    if args.stop:
        for name in (INGRESS, RELAY):
            docker("stop", state["containers"][name])
    if args.status:
        print("QA_TOPOLOGY_VERIFIED", state["run"])
    if args.test:
        wait_tls(state)
        return run_test_cohorts(state)
    if args.destroy:
        destroy(state, value)
        print("QA_OWNED_RESOURCES_REMOVED existing_PG_and_unrelated_services_retained")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(
            str(exc) if str(exc).startswith("QA_") else "QA_OPERATION_FAILED",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except Exception:  # noqa: BLE001 -- CLI errors must not serialize credential-bearing objects
        print("QA_OPERATION_FAILED", file=sys.stderr)
        raise SystemExit(1) from None
