"""Export only fixed-schema ingress metadata from the strictly guarded QA run."""

import importlib.util
import json
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "event",
    "reason",
    "elapsed_ms",
    "time_ms",
    "active",
    "client_to_upstream_bytes",
    "upstream_to_client_bytes",
}
REASONS = {
    "multiple_directions_eof",
    "capacity_rejected",
    "connection_cancelled",
    "upstream_connect_timeout",
    "upstream_connect_error",
    "connection_lifetime_timeout",
    "connection_lifetime_error",
} | {
    direction + "_" + phase + "_" + result
    for direction in ("client_to_upstream", "upstream_to_client")
    for phase in ("read", "write")
    for result in ("eof", "timeout", "error")
}


def validate(raw):
    events = []
    for line in raw.splitlines():
        value = json.loads(line)
        if (
            not isinstance(value, dict)
            or set(value) != FIELDS
            or value["event"] != "ingress_close"
            or value["reason"] not in REASONS
            or any(
                type(value[k]) is not int or value[k] < 0
                for k in FIELDS - {"event", "reason"}
            )
        ):
            raise ValueError("DIAGNOSTIC_SCHEMA_REJECTED")
        events.append(value)
    return events


def main():
    spec = importlib.util.spec_from_file_location(
        "relay_qa", ROOT / "scripts/secure-relay-qa.py"
    )
    qa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qa)
    if not qa.STATE.exists():
        raise RuntimeError("QA_RUN_STATE_REQUIRED")
    state = json.loads(qa.STATE.read_text())
    qa.guard_state(state, qa.config())
    events = validate(qa.docker("logs", state["containers"][qa.INGRESS]))
    directory = ROOT / "storage/runtime/tls-case-evidence"
    directory.mkdir(parents=True, exist_ok=True)
    run = str(UUID(state["run"]))
    with (directory / ("ingress-" + run + "-" + str(uuid4()) + ".json")).open(
        "x", encoding="utf-8"
    ) as output:
        json.dump({"run": run, "events": events}, output)
    print("QA_INGRESS_DIAGNOSTICS", len(events))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 -- fail nonzero without printing credential-bearing objects
        raise SystemExit("QA_DIAGNOSTICS_FAILED") from None
