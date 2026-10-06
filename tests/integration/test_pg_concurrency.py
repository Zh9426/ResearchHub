"""真实隔离 PostgreSQL 服务层竞态验证，不代表外部客户端验收。"""

# ruff: noqa: F811 - imported pytest fixture is intentionally used by name.
import copy
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from test_live_system import create, live  # noqa: F401

from apps.api.researchhub import models as m
from apps.api.researchhub import service as svc


@pytest.mark.parametrize(
    "scenario", ["confirmed_parameter", "restored_run", "module_upgrade"]
)
def test_pg_waiting_writer_rechecks_committed_state(live, scenario):
    if os.getenv("HUB_COMPOSE_RECOVERY") != "1":
        pytest.skip(
            "Requires isolated Compose PostgreSQL; never run against personal DB"
        )
    config = dict(
        line.split("=", 1)
        for line in Path(".env.qa").read_text().splitlines()
        if "=" in line
    )
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=config["POSTGRES_USER"],
            password=config["POSTGRES_PASSWORD"],
            host="127.0.0.1",
            port=35432,
            database=config["POSTGRES_DB"],
        )
    )
    project = create(
        live,
        "/api/projects",
        {"name": "SYNTHETIC concurrency " + uuid_suffix(), "module_id": "generic"},
    )
    pid = project["id"]
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="synthetic-lock-" + uuid_suffix())
    )
    rid = parameter_id = None
    if scenario != "module_upgrade":
        run = create(
            live,
            f"/api/projects/{pid}/runs",
            {"title": "SYNTHETIC concurrency run", "run_type": "simulation"},
        )
        rid = run["id"]
    if scenario == "confirmed_parameter":
        parameter_id = create(
            live,
            f"/api/runs/{rid}/parameters",
            {"name": "SYNTHETIC pressure", "value": 1},
        )["id"]
    elif scenario == "restored_run":
        assert live.delete(f"/api/runs/{rid}").status_code == 200
        with engine.begin() as db:
            db.execute(
                text("UPDATE research_runs SET trashed_at=:stamp WHERE id=:id"),
                {"stamp": m.now() - timedelta(days=31), "id": rid},
            )

    worker_ready = Event()
    worker_pid = []

    def waiting_writer():
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(m.User, project["owner_id"])
            actor = SimpleNamespace(
                user=user,
                actor_type="codex" if scenario == "confirmed_parameter" else "human",
                token=scenario == "confirmed_parameter",
            )
            # Deliberately warm the identity map with stale committed values.
            cls = (
                m.Parameter
                if scenario == "confirmed_parameter"
                else m.ResearchRun
                if scenario == "restored_run"
                else m.Project
            )
            cached = db.get(cls, parameter_id or rid or pid)
            assert cached is not None
            worker_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            worker_ready.set()
            try:
                if scenario == "confirmed_parameter":
                    obj = svc.resource(db, actor, m.Parameter, parameter_id, write=True)
                    svc.scientific_authority(
                        actor, "parameters", {"value": 2}, existing=obj
                    )
                elif scenario == "restored_run":
                    svc.purge(db, actor, request, "runs", rid)
                else:
                    svc.create_record(
                        db,
                        actor,
                        request,
                        "runs",
                        pid,
                        {"title": "SYNTHETIC obsolete type", "run_type": "simulation"},
                        {},
                    )
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
            db.rollback()
            return 200

    try:
        with (
            Session(engine, expire_on_commit=False) as holding,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            human = SimpleNamespace(
                user=holding.get(m.User, project["owner_id"]),
                actor_type="human",
                token=None,
            )
            if scenario == "confirmed_parameter":
                obj = svc.resource(
                    holding, human, m.Parameter, parameter_id, write=True
                )
                obj.is_confirmed = True
                holding.flush()
            elif scenario == "restored_run":
                svc.lifecycle(holding, human, request, "runs", rid, "restore")
            else:
                obj = svc.project_for(holding, human, pid, write=True)
                latest = copy.deepcopy(obj.module_snapshot)
                latest["version"] = "0.2.1"
                latest["run_types"] = [
                    row for row in latest["run_types"] if row["id"] != "simulation"
                ]
                svc.upgrade_module(
                    holding,
                    human,
                    request,
                    obj,
                    latest,
                    obj.module_version,
                    svc.module_digest(latest),
                    {},
                )
                holding.flush()
            future = pool.submit(waiting_writer)
            try:
                assert worker_ready.wait(5), "Concurrent QA writer did not start"
                deadline = time.monotonic() + 5
                blocked = False
                while time.monotonic() < deadline:
                    with engine.connect() as monitor:
                        blocked = monitor.scalar(
                            text(
                                "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"
                            ),
                            {"pid": worker_pid[0]},
                        )
                    if blocked:
                        break
                    if future.done():
                        break
                    time.sleep(0.02)
                assert blocked, "Writer did not wait for the actual PostgreSQL row lock"
            finally:
                holding.commit()  # Release the real lock even when an assertion fails.
            assert (
                future.result(timeout=5)
                == {
                    "confirmed_parameter": 403,
                    "restored_run": 409,
                    "module_upgrade": 422,
                }[scenario]
            )
        with Session(engine) as db:
            if scenario == "confirmed_parameter":
                obj = db.get(m.Parameter, parameter_id)
                assert obj.is_confirmed and obj.value == 1
            elif scenario == "restored_run":
                assert db.get(m.ResearchRun, rid).trashed_at is None
            else:
                assert db.get(m.Project, pid).module_version == "0.2.1"
                assert (
                    list(
                        db.scalars(
                            select(m.ResearchRun).where(m.ResearchRun.project_id == pid)
                        )
                    )
                    == []
                )
    finally:
        engine.dispose()


def uuid_suffix():
    import uuid

    return uuid.uuid4().hex[:8]
