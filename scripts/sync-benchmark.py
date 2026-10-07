"""Opt-in synthetic workload, always through the actual QA PostgreSQL kernel."""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
sys.path.insert(0, str(ROOT / "tests/sync_pg"))
from conftest import World
from researchhub.sync.authority import register_principal
from researchhub.sync.canonical import digest
from researchhub.sync.kernel import heads, register_project
from researchhub.sync.models import ObjectRevision, SyncConflict, initialize_qa
from researchhub.sync.protocol import revision
from researchhub.sync.qa import qa_engine


def timed(call, count=1):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        call()
        samples.append((time.perf_counter() - start) * 1000)
    return {"mean_ms": round(statistics.mean(samples), 3),
            "p95_ms": round(sorted(samples)[max(0, int(len(samples) * .95) - 1)], 3),
            "samples": count}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    if not parser.parse_args().run:
        parser.error("--run required for dedicated QA workload")
    os.environ["HUB_SYNC_QA"] = "1"
    engine = qa_engine()
    initialize_qa(engine)
    project_id = str(uuid4())
    identity = {key: str(uuid4()) for key in
                ("principal_id", "user_id", "device_id", "session_id", "actor_id")}
    identity.update(project_id=project_id, actor_type="human")
    with Session(engine) as db, db.begin():
        register_project(db, project_id, "a" * 64)
        register_principal(db, **identity)
    world = World(engine, project_id, {"human": identity})
    objects = [str(uuid4()) for _ in range(1000)]
    parents, bases = {}, {}
    start = time.perf_counter()
    batch_times = []
    for level in range(10):
        for offset in range(0, 1000, 100):
            tx = world.make(items=[{
                "object_type": "Parameter", "object_id": oid,
                "operation": "create" if level == 0 else "update",
                "parents": [] if level == 0 else [parents[oid]],
                "payload": {"name": "SYNTHETIC benchmark", "value_type": "decimal",
                            "value": f"{level}.000"},
            } for oid in objects[offset:offset + 100]])
            batch_times.append(timed(lambda current=tx: world.apply(current))["mean_ms"])
            for change in tx["changes"]:
                parents[change["object_id"]] = revision(change)
                if level == 8:
                    bases[change["object_id"]] = revision(change)
        print(f"QA benchmark: {(level + 1) * 1000} immutable revisions committed", flush=True)
    result = {"scope": "sync-kernel-s1", "project_id": project_id,
              "backend": "PostgreSQL 17.11 Docker loopback", "base_revisions": 10000,
              "base_objects": 1000, "load_seconds": round(time.perf_counter() - start, 3),
              "load_batch_100_mean_ms": round(statistics.mean(batch_times), 3),
              "load_batch_100_p95_ms": round(sorted(batch_times)[94], 3)}
    with Session(engine) as db:
        index = iter(objects)
        result["head_lookup"] = timed(lambda: heads(db, project_id, "Parameter", next(index)), 1000)
    fork = world.make(items=[{
        "object_type": "Parameter", "object_id": oid, "operation": "update",
        "parents": [bases[oid]], "payload": {"value": "11.000", "value_type": "decimal"},
    } for oid in objects[:100]])
    result["conflict_batch_100_apply"] = timed(lambda: world.apply(fork))
    with Session(engine) as db:
        result["open_conflicts"] = db.scalar(select(func.count()).select_from(SyncConflict).where(
            SyncConflict.project_id == project_id, SyncConflict.status == "open"))
    assert result["open_conflicts"] == 100
    independent = world.make(items=[{"object_type": "Note", "payload": {"content": "SYNTHETIC benchmark"}}
                                    for _ in range(100)])
    result["independent_batch_100_apply"] = timed(lambda: world.apply(independent))
    result["digest_batch_100"] = timed(lambda: digest(independent), 100)
    with Session(engine) as db:
        result["final_revisions"] = db.scalar(select(func.count()).select_from(ObjectRevision).where(
            ObjectRevision.project_id == project_id))
    path = ROOT / "storage/runtime/sync-s1-benchmark.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
