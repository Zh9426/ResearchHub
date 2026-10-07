"""Explicit opt-in dedicated QA PostgreSQL. No product database fallback."""

import copy
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))
from researchhub.sync.authority import TrustedContext, register_principal
from researchhub.sync.kernel import apply, register_project
from researchhub.sync.models import initialize_qa
from researchhub.sync.qa import qa_engine


def uid():
    return str(uuid4())


@pytest.fixture(scope="session")
def engine():
    if os.environ.get("HUB_SYNC_QA") != "1":
        pytest.skip("Explicit dedicated Sync QA opt-in required")
    result = qa_engine()
    initialize_qa(result)
    yield result
    result.dispose()


@dataclass
class World:
    engine: object
    project_id: str
    people: dict
    module_hash: str = "a" * 64

    def context(self, actor="human", *, grant_id=None, mode="online", relay_seq=None):
        return TrustedContext(self.people[actor]["principal_id"], grant_id, mode, relay_seq)

    def make(self, items=None, *, actor="human", kind="Parameter", oid=None,
             payload=None, parents=(), operation="create", dependencies=()):
        person = self.people[actor]
        transaction_id = uid()
        if items is None:
            items = [{"object_type": kind, "object_id": oid or uid(), "operation": operation,
                      "parents": list(parents), "payload": payload if payload is not None else {
                          "name": "SYNTHETIC pressure", "value_type": "decimal", "value": "1.400"}}]
        changes = []
        for item in items:
            changes.append({
                "change_id": uid(), "audit_id": uid(), "transaction_id": transaction_id,
                "project_id": self.project_id, "device_id": person["device_id"],
                "actor_id": person["actor_id"], "actor_type": person["actor_type"],
                "object_type": item["object_type"], "object_id": item.get("object_id", uid()),
                "operation": item.get("operation", "create"),
                "parents": sorted(item.get("parents", [])), "payload": copy.deepcopy(item["payload"]),
                "schema_version": 1, "module_snapshot_hash": self.module_hash,
                "created_at": "2026-10-07T01:02:03.004Z",
            })
        return {
            "transaction_id": transaction_id, "idempotency_key": transaction_id,
            "project_id": self.project_id, "device_id": person["device_id"],
            "actor_id": person["actor_id"], "actor_type": person["actor_type"],
            "protocol_version": 1, "schema_version": 1,
            "created_at": "2026-10-07T01:02:03.004Z",
            "ordered_change_ids": [c["change_id"] for c in changes], "changes": changes,
            "dependencies": sorted(dependencies),
        }

    def apply(self, tx, *, actor="human", context=None, **kwargs):
        return apply(self.engine, tx, context or self.context(actor), **kwargs)


@pytest.fixture
def world_factory(engine):
    def create(module_hash="a" * 64):
        project_id = uid()
        people = {}
        with Session(engine) as db, db.begin():
            register_project(db, project_id, module_hash)
            human_user = uid()
            for name, actor in [("human", "human"), ("human_b", "human"),
                                ("codex", "codex"), ("chatgpt", "chatgpt"), ("system", "system")]:
                identity = {"principal_id": uid(), "user_id": human_user,
                            "device_id": uid(), "session_id": uid(), "project_id": project_id,
                            "actor_id": uid(), "actor_type": actor}
                register_principal(db, **identity)
                people[name] = identity
        return World(engine, project_id, people, module_hash)
    return create


@pytest.fixture
def world(world_factory):
    return world_factory()
