"""Actual trusted client process; private QA material arrives only via stdin."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/api")]

from researchhub.sync.secure.keys import Device
from researchhub.sync.secure.transport import SecureTransport
from researchhub.sync.secure.transport_pg import client_engine


def main():
    config = json.loads(sys.stdin.buffer.read())
    device = Device(
        config["device"],
        bytes.fromhex(config["signing"]),
        bytes.fromhex(config["recipient"]),
    )
    client = SecureTransport(
        client_engine(),
        config["project"],
        device,
        config["ca"],
        {1: bytes.fromhex(config["key"])},
    )

    def barrier(point):
        if point == config["point"]:
            Path(config["barrier"]).write_text(point)
            while True:
                time.sleep(0.1)

    client.receive(client.pull(0), 0, barrier=barrier)
    raise RuntimeError("Expected parent process termination")


if __name__ == "__main__":
    main()
