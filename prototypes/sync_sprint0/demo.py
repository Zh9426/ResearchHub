"""Run a disposable synthetic offline/conflict demonstration; no network or credentials."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .model import canonical
from .relay import Relay
from .replica import Replica


def main():
    with TemporaryDirectory(prefix="researchhub-synthetic-sync-") as directory:
        root = Path(directory)
        project = str(uuid4())
        relay = Relay(root / "relay.sqlite")
        a, b = Replica(root / "a.sqlite", project), Replica(root / "b.sqlite", project)
        try:
            relay.register_device(a.device_id, "human")
            relay.register_device(b.device_id, "human")
            run = a.create("ResearchRun", {"title": "synthetic offline run"})
            parameter = a.create("Parameter", {"name": "pressure", "value": 1.4,
                                               "run_id": run.object_id})
            a.push_pending(relay)
            b.pull(relay)
            a.update(parameter.object_id, {"value": 1.6})
            b.update(parameter.object_id, {"value": 1.8})
            a.push_pending(relay)
            b.push_pending(relay)
            a.pull(relay)
            b.pull(relay)
            state = b.state(parameter.object_id)
            print(canonical({"synthetic_only": True, "offline_run_on_b": b.state(run.object_id),
                             "parameter": state, "replicas_agree": state == a.state(parameter.object_id),
                             "audit_count": b.audit_count(), "encryption": "plaintext-simulator"}))
        finally:
            for node in (a, b, relay):
                node.db.close()


if __name__ == "__main__":
    main()
