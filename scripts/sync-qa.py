"""Create/run only the disposable Sync Kernel QA database; no product fallback."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "researchhub-sync-s1-pg"
CONFIG = ROOT / "storage/runtime/sync-s1-qa.json"
ENV_FILE = ROOT / ".env.sync-qa"


def initialize():
    if not CONFIG.exists():
        if ENV_FILE.exists():
            raise RuntimeError("QA env exists without config; review manually")
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "scope": "sync-kernel-s1", "database": "researchhub_sync_kernel_qa",
            "username": "researchhub_sync_qa", "password": secrets.token_hex(32),
            "host": "127.0.0.1", "port": 35433, "container": CONTAINER,
        }
        CONFIG.write_text(json.dumps(config), encoding="utf-8")
        ENV_FILE.write_text(
            f"POSTGRES_DB={config['database']}\nPOSTGRES_USER={config['username']}\n"
            f"POSTGRES_PASSWORD={config['password']}\n", encoding="utf-8",
        )
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if (config.get("scope"), config.get("container"), config.get("port")) != (
        "sync-kernel-s1", CONTAINER, 35433
    ):
        raise RuntimeError("Unexpected QA scope/container/port")
    inspection = subprocess.run(
        ["docker", "inspect", "--format", '{{index .Config.Labels "researchhub.qa.scope"}}',
         CONTAINER], capture_output=True, text=True, check=False,
    )
    if inspection.returncode == 0:
        if inspection.stdout.strip() != "sync-kernel-s1":
            raise RuntimeError("Existing container is not the dedicated Sync QA container")
        subprocess.run(["docker", "start", CONTAINER], check=True, capture_output=True)
    else:
        subprocess.run([
            "docker", "run", "-d", "--name", CONTAINER,
            "--label", "researchhub.qa.scope=sync-kernel-s1", "--env-file", str(ENV_FILE),
            "-p", "127.0.0.1:35433:5432", "postgres:17.11-bookworm",
        ], check=True, capture_output=True)
    for _ in range(20):
        probe = subprocess.run([
            "docker", "exec", CONTAINER, "pg_isready", "-U", "researchhub_sync_qa",
            "-d", "researchhub_sync_kernel_qa",
        ], capture_output=True, check=False)
        if probe.returncode == 0:
            print("Dedicated Sync Kernel QA PostgreSQL ready (loopback :35433)")
            return
        time.sleep(0.5)
    raise RuntimeError("QA PostgreSQL did not become ready")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Create/start dedicated QA PG")
    parser.add_argument("--test", action="store_true", help="Run vectors/kernel/PG QA tests")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.init:
        initialize()
    if args.test:
        environment = {**os.environ, "HUB_SYNC_QA": "1"}
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/sync_vectors", "tests/sync_kernel",
            "tests/sync_pg", "-q",
        ], env=environment, check=False)
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
