"""Sprint 0 semantic safeguards; SQLite tests are isolated, not service acceptance."""

import copy
from datetime import timedelta

import pytest
from test_api import client as api_client
from test_api import login, passed_gate, project, run

from apps.api.researchhub import models as m

client = api_client


def token(client):
    value = client.post(
        "/api/auth/tokens",
        json={"name": "AI", "scopes": ["research:read", "research:write"]},
    ).json()["token"]
    client.headers["Authorization"] = "Bearer " + value


def test_project_manifest_is_frozen_and_upgrade_explicit(client):
    login(client)
    pid = project(client)
    original = client.get(f"/api/projects/{pid}/context").json()["module"]
    latest = copy.deepcopy(original)
    latest["version"] = "0.2.2"
    latest["run_types"] = [{"id": "new_run", "name": "新类型"}]
    client.app.state.modules["generic"] = latest
    assert client.get(f"/api/projects/{pid}/context").json()["module"] == original
    assert (
        client.get(f"/api/projects/{pid}").json()["module_version"]
        == original["version"]
    )
    assert (
        client.post(
            f"/api/projects/{pid}/runs",
            json={"title": "旧定义", "run_type": "simulation"},
        ).status_code
        == 200
    )
    preview = client.get(f"/api/projects/{pid}/module-upgrade/preview").json()
    assert preview["changes"]["run_types"]["removed"]
    body = {
        "expected_version": original["version"],
        "expected_target_digest": preview["target_digest"],
        "confirm": True,
    }
    denied = client.post(
        f"/api/projects/{pid}/module-upgrade",
        json={**body, "expected_version": "invalid"},
    )
    assert denied.status_code == 409
    # Incompatible removal cannot strand existing scientific records.
    denied = client.post(f"/api/projects/{pid}/module-upgrade", json=body)
    assert denied.status_code == 422
    latest["run_types"] = original["run_types"] + latest["run_types"]
    assert (
        client.post(f"/api/projects/{pid}/module-upgrade", json=body).status_code == 409
    )
    body["expected_target_digest"] = client.get(
        f"/api/projects/{pid}/module-upgrade/preview"
    ).json()["target_digest"]
    assert (
        client.post(f"/api/projects/{pid}/module-upgrade", json=body).status_code == 200
    )
    assert (
        client.get(f"/api/projects/{pid}/context").json()["module"]["version"]
        == "0.2.2"
    )


def test_ai_cannot_confirm_create_or_patch_but_can_propose(client):
    login(client)
    pid = project(client)
    rid = run(client, pid, human_conclusion="人工结论")
    reviewed = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "人工实测", "status": "measured"},
    ).json()
    token(client)
    assert (
        client.patch(f"/api/runs/{rid}", json={"human_conclusion": ""}).status_code
        == 403
    )
    assert (
        client.patch(f"/api/runs/{rid}", json={"ai_analysis": "建议"}).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{pid}/runs",
            json={
                "run_type": "simulation",
                "title": "越权",
                "human_conclusion": "伪造",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/runs/{rid}/parameters", json={"name": "x", "is_confirmed": True}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{pid}/evidence",
            json={"title": "越权", "status": "validated"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{pid}/evidence",
            json={"title": "提议", "status": "proposed"},
        ).status_code
        == 200
    )
    for status in ("measured", "calibrated", "rejected", "unknown", "simulated"):
        assert (
            client.post(
                f"/api/projects/{pid}/evidence",
                json={"title": "越权", "status": status},
            ).status_code
            == 403
        )
    assert (
        client.post(f"/api/projects/{pid}/evidence", json={"title": "默认提议"}).json()[
            "status"
        ]
        == "proposed"
    )
    assert (
        client.patch(
            f"/api/evidence/{reviewed['id']}", json={"title": "篡改"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{pid}/decisions",
            json={"title": "越权", "status": "accepted"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{pid}/decisions",
            json={"title": "越权", "status": "rejected"},
        ).status_code
        == 403
    )
    assert client.post("/api/demo/seed").status_code == 403
    assert client.delete(f"/api/runs/{rid}").status_code == 403
    assert (
        client.patch(f"/api/lifecycle/runs/{rid}", json={"action": "trash"}).status_code
        == 403
    )


def test_soft_delete_preserves_values_and_audit_restore(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    param = client.post(
        f"/api/runs/{rid}/parameters", json={"name": "unknown", "value": None}
    ).json()
    assert client.delete(f"/api/runs/{rid}").status_code == 200
    assert client.get(f"/api/runs/{rid}").status_code == 404
    assert client.get(f"/api/projects/{pid}/runs").json() == []
    with client.app.state.session_factory() as db:
        assert db.get(m.ResearchRun, rid).trashed_at is not None
        assert db.get(m.Parameter, param["id"]).value is None
    assert (
        client.post(
            f"/api/lifecycle/runs/{rid}/purge", json={"confirm": True}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/lifecycle/runs/{rid}", json={"action": "restore"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/runs/{rid}").status_code == 200
    assert client.get(f"/api/runs/{rid}/parameters").json()[0]["id"] == param["id"]
    assert any(
        a["action"] == "restore_runs" for a in client.get("/api/activity").json()
    )


def test_project_archive_blocks_writes_and_trash_restore_retains_children(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    assert (
        client.patch(
            f"/api/lifecycle/projects/{pid}", json={"action": "archive"}
        ).status_code
        == 200
    )
    assert (
        client.patch(f"/api/runs/{rid}", json={"title": "不应写入"}).status_code == 409
    )
    assert (
        client.post(
            f"/api/projects/{pid}/runs",
            json={"title": "不应写入", "run_type": "simulation"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/lifecycle/projects/{pid}", json={"action": "restore"}
        ).status_code
        == 200
    )
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/runs/{rid}").status_code == 404
    assert (
        client.patch(
            f"/api/lifecycle/projects/{pid}", json={"action": "restore"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/runs/{rid}").status_code == 200


def test_purge_enqueues_private_objects_gc_failure_retry_and_live_guard(client):
    login(client)
    pid = project(client)
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("data.txt", b"fact", "text/plain")},
        data={"category": "data"},
    ).json()
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    with client.app.state.session_factory() as db:
        db.get(m.Project, pid).trashed_at = m.now() - timedelta(days=31)
        db.commit()
    assert (
        client.post(
            f"/api/lifecycle/projects/{pid}/purge", json={"confirm": True}
        ).status_code
        == 200
    )
    preview = client.get("/api/storage/gc-preview").json()
    assert preview["items"][0]["object_key"] == artifact["object_key"]
    assert artifact["object_key"] in client.app.state.objects.data
    original_delete = client.app.state.objects.delete

    def failing(key):
        raise OSError("private-secret-should-not-be-exposed")

    client.app.state.objects.delete = failing
    body = {"confirm": True, "object_keys": [artifact["object_key"]]}
    failed = client.post("/api/storage/gc", json=body)
    assert failed.status_code == 200 and failed.json()["failed"] == 1
    assert "private-secret" not in failed.text
    client.app.state.objects.delete = original_delete
    assert client.post("/api/storage/gc", json=body).json()["deleted"] == 1
    assert artifact["object_key"] not in client.app.state.objects.data
    assert (
        client.post(
            "/api/storage/gc", json={"confirm": True, "object_keys": ["arbitrary/key"]}
        ).status_code
        == 422
    )


def test_token_cannot_pass_gate_or_criterion_and_cannot_confirm_by_patch(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    rid = run(client, pid, run_type="numerical_validation")
    evidence = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "人工证据", "status": "validated"},
    ).json()
    parameter = client.post(
        f"/api/runs/{rid}/parameters",
        json={"name": "confirmed", "value": 0, "is_confirmed": True},
    ).json()
    gate = client.get(f"/api/projects/{pid}/gates").json()[0]
    token(client)
    criteria = [
        {**criterion, "status": "passed", "evidence_ids": [evidence["id"]]}
        for criterion in gate["criteria"]
    ]
    assert (
        client.patch(
            f"/api/gates/{gate['id']}",
            json={
                "status": "passed",
                "criteria": criteria,
                "evidence_ids": [evidence["id"]],
            },
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/gates/{gate['id']}", json={"criteria": criteria}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/parameters/{parameter['id']}", json={"value": 1}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/parameters/{parameter['id']}", json={"is_confirmed": False}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/runs/{rid}/metrics/batch",
            json={"metrics": [{"name": "unsafe", "status": "reproduced", "value": 7}]},
        ).status_code
        == 403
    )
    assert client.get(f"/api/runs/{rid}/metrics").json() == []
    assert (
        client.post(
            "/api/storage/gc", json={"confirm": True, "object_keys": ["any"]}
        ).status_code
        == 403
    )
    assert client.get("/api/storage/gc-preview").status_code == 403
    preview = client.get(f"/api/projects/{pid}/module-upgrade/preview").json()
    assert (
        client.post(
            f"/api/projects/{pid}/module-upgrade",
            json={
                "confirm": True,
                "expected_version": preview["current_version"],
                "expected_target_digest": preview["target_digest"],
            },
        ).status_code
        == 403
    )


def test_trashing_underlying_run_invalidates_gate_and_blocks_reapproval(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    rid = run(client, pid, run_type="numerical_validation")
    evidence = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "人工证据", "status": "validated", "linked_run_id": rid},
    ).json()
    gate = passed_gate(client, pid, [evidence["id"]], [evidence["id"]])
    assert client.delete(f"/api/runs/{rid}").status_code == 200
    assert client.get(f"/api/gates/{gate['id']}").json()["status"] == "blocked"
    assert (
        client.patch(
            f"/api/gates/{gate['id']}",
            json={
                "status": "passed",
                "criteria": gate["criteria"],
                "evidence_ids": gate["evidence_ids"],
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/lifecycle/runs/{rid}", json={"action": "restore"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/gates/{gate['id']}").json()["status"] == "blocked"
    assert (
        client.patch(
            f"/api/gates/{gate['id']}",
            json={
                "status": "passed",
                "criteria": gate["criteria"],
                "evidence_ids": gate["evidence_ids"],
            },
        ).status_code
        == 200
    )


def test_live_object_guard_and_gc_idempotent(client):
    from apps.api.researchhub import service as svc

    login(client)
    pid = project(client)
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("live.txt", b"fact", "text/plain")},
        data={"category": "data"},
    ).json()
    with client.app.state.session_factory() as db:
        svc.enqueue_object_deletion(
            db, db.get(m.Project, pid).owner_id, pid, artifact["object_key"]
        )
        db.commit()
    preview = client.get("/api/storage/gc-preview").json()
    assert preview["items"][0]["has_live_reference"]
    assert (
        client.post(
            "/api/storage/gc",
            json={"confirm": True, "object_keys": [artifact["object_key"]]},
        ).json()["skipped_live"]
        == 1
    )
    assert artifact["object_key"] in client.app.state.objects.data


def test_upload_metadata_failure_preserves_retryable_orphan_cleanup(
    client, monkeypatch
):
    from apps.api.researchhub import service as svc

    login(client)
    pid = project(client)
    original = svc.audit

    def fail(db, actor, request, action, obj, before=None):
        if action == "upload_artifact":
            raise RuntimeError("isolated simulated DB failure")
        return original(db, actor, request, action, obj, before)

    monkeypatch.setattr(svc, "audit", fail)
    with pytest.raises(RuntimeError):
        client.post(
            f"/api/projects/{pid}/artifacts",
            files={"file": ("orphan.txt", b"fact", "text/plain")},
            data={"category": "data"},
        )
    key = next(iter(client.app.state.objects.data))
    assert client.get(f"/api/projects/{pid}/artifacts").json() == []
    assert client.get("/api/storage/gc-preview").json()["items"][0]["object_key"] == key
    assert (
        client.post(
            "/api/storage/gc", json={"confirm": True, "object_keys": [key]}
        ).json()["deleted"]
        == 1
    )
    assert (
        client.post(
            "/api/storage/gc", json={"confirm": True, "object_keys": [key]}
        ).json()["deleted"]
        == 0
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("questions", {"title": "问题"}),
        ("hypotheses", {"statement": "假设"}),
        ("milestones", {"title": "里程碑"}),
        ("tasks", {"title": "任务"}),
        ("notes", {"title": "笔记"}),
        ("decisions", {"title": "决策"}),
        ("evidence", {"title": "证据"}),
        ("claims", {"statement": "主张"}),
        ("sources", {"title": "来源"}),
        ("risks", {"title": "风险"}),
        ("tags", {"name": "标签"}),
    ],
)
def test_scientific_entities_all_reversible_not_hard_deleted(client, kind, payload):
    login(client)
    pid = project(client)
    obj = client.post(f"/api/projects/{pid}/{kind}", json=payload).json()
    assert client.delete(f"/api/{kind}/{obj['id']}").status_code == 200
    assert client.get(f"/api/projects/{pid}/{kind}").json() == []
    assert (
        client.get(f"/api/projects/{pid}/lifecycle?kind={kind}").json()[0]["id"]
        == obj["id"]
    )
    assert (
        client.patch(
            f"/api/lifecycle/{kind}/{obj['id']}", json={"action": "restore"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/{kind}/{obj['id']}").status_code == 200


def test_owner_isolation_lifecycle_listing_and_restore(client):
    from apps.api.researchhub.main import password_hash

    login(client)
    pid = project(client)
    rid = run(client, pid)
    client.delete(f"/api/runs/{rid}")
    with client.app.state.session_factory() as db:
        db.add(
            m.User(
                email="other@example.test",
                display_name="Other",
                password_hash=password_hash("other-long-password"),
            )
        )
        db.commit()
    client.post("/api/auth/logout")
    logged = client.post(
        "/api/auth/login",
        json={"email": "other@example.test", "password": "other-long-password"},
    ).json()
    client.headers["X-CSRF-Token"] = logged["csrf_token"]
    assert client.get("/api/lifecycle/runs").json() == []
    assert client.get(f"/api/projects/{pid}/lifecycle?kind=runs").status_code == 404
    assert (
        client.patch(
            f"/api/lifecycle/runs/{rid}", json={"action": "restore"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/lifecycle/runs/{rid}/purge", json={"confirm": True}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("coerced_true", [True, 1, "true", "1"])
def test_ai_parameter_confirmation_cannot_bypass_with_coerced_boolean(
    client, coerced_true
):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    parameter = client.post(
        f"/api/runs/{rid}/parameters", json={"name": "unconfirmed", "value": 0}
    ).json()
    token(client)
    assert (
        client.patch(
            f"/api/parameters/{parameter['id']}", json={"is_confirmed": coerced_true}
        ).status_code
        == 403
    )
    assert client.get(f"/api/runs/{rid}/parameters").json()[0]["is_confirmed"] is False
    # Partial updates of the independent AI analysis field remain usable.
    assert (
        client.patch(f"/api/runs/{rid}", json={"ai_analysis": "未审核建议"}).status_code
        == 200
    )


def test_object_put_lost_ack_preserves_cleanup_outbox(client, monkeypatch):
    login(client)
    pid = project(client)
    original = client.app.state.objects.put

    def lost_ack(key, stream, size, mime):
        original(key, stream, size, mime)
        raise OSError("isolated lost acknowledgement after bytes stored")

    monkeypatch.setattr(client.app.state.objects, "put", lost_ack)
    response = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("lost.txt", b"stored", "text/plain")},
        data={"category": "data"},
    )
    assert response.status_code == 503
    assert client.get(f"/api/projects/{pid}/artifacts").json() == []
    key = next(iter(client.app.state.objects.data))
    preview = client.get("/api/storage/gc-preview").json()
    assert preview["items"][0]["object_key"] == key
    assert preview["items"][0]["has_live_reference"] is False
    assert (
        client.post(
            "/api/storage/gc", json={"confirm": True, "object_keys": [key]}
        ).json()["deleted"]
        == 1
    )
    assert client.app.state.objects.data == {}


def test_ai_cannot_modify_existing_passed_gate(client):
    login(client)
    pid = project(client, "ice-sonocuring")
    evidence = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "人工证据", "status": "validated"},
    ).json()
    gate = passed_gate(client, pid, [evidence["id"]], [evidence["id"]])
    stage = client.get(f"/api/projects/{pid}/context").json()["module"][
        "research_stages"
    ][-1]["id"]
    token(client)
    for payload in (
        {"stage_id": stage},
        {"evidence_ids": [evidence["id"]]},
        {"name": "AI重写通过结论"},
        {"description": "AI替换判据说明"},
    ):
        assert client.patch(f"/api/gates/{gate['id']}", json=payload).status_code == 403
    client.headers.pop("Authorization")
    assert (
        client.patch(
            f"/api/gates/{gate['id']}", json={"name": "人工修改名称"}
        ).status_code
        == 200
    )


def test_write_and_lifecycle_locks_follow_project_run_resource_order(client):
    from sqlalchemy import event
    from sqlalchemy.dialects import postgresql

    login(client)
    pid = project(client)
    rid = run(client, pid)
    parameter = client.post(f"/api/runs/{rid}/parameters", json={"name": "x"}).json()
    seen = []

    def capture(connection, clause, multiparams, params, options):
        if getattr(clause, "_for_update_arg", None) is not None:
            assert "FOR UPDATE" in str(clause.compile(dialect=postgresql.dialect()))
            assert options.get("populate_existing") is True
            seen.append(clause.get_final_froms()[0].name)

    engine = client.app.state.engine
    event.listen(engine, "before_execute", capture)
    try:
        assert (
            client.patch(
                f"/api/parameters/{parameter['id']}", json={"value": 2}
            ).status_code
            == 200
        )
        assert seen == ["projects", "research_runs", "parameters"]
        seen.clear()
        assert client.delete(f"/api/runs/{rid}").status_code == 200
        assert seen == ["projects", "research_runs"]
        seen.clear()
        assert (
            client.patch(
                f"/api/lifecycle/runs/{rid}", json={"action": "restore"}
            ).status_code
            == 200
        )
        # The restore parent guard reacquires the already-held project lock.
        assert seen == ["projects", "research_runs", "projects"]
        seen.clear()
        assert (
            client.post(
                f"/api/lifecycle/runs/{rid}/purge", json={"confirm": True}
            ).status_code
            == 409
        )
        assert seen == ["projects", "research_runs"]
    finally:
        event.remove(engine, "before_execute", capture)


def test_locked_write_refreshes_cached_confirmation_and_trash_state(client):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from apps.api.researchhub import service as svc

    login(client)
    pid = project(client)
    rid = run(client, pid)
    parameter = client.post(f"/api/runs/{rid}/parameters", json={"name": "x"}).json()
    factory = client.app.state.session_factory
    with factory() as cached:
        stale = cached.get(m.Parameter, parameter["id"])
        assert stale.is_confirmed is False
        with factory() as other:
            other.get(m.Parameter, parameter["id"]).is_confirmed = True
            other.commit()
        actor = SimpleNamespace(
            user=cached.get(m.User, cached.get(m.Project, pid).owner_id),
            token=object(),
            actor_type="codex",
        )
        refreshed = svc.resource(
            cached, actor, m.Parameter, parameter["id"], write=True
        )
        assert refreshed is stale and refreshed.is_confirmed is True
        with pytest.raises(HTTPException) as denied:
            svc.scientific_authority(
                actor, "parameters", {"value": 2}, existing=refreshed
            )
        assert denied.value.status_code == 403
    with factory() as setup:
        setup.get(m.ResearchRun, rid).trashed_at = m.now() - timedelta(days=31)
        setup.commit()
    with factory() as cached:
        stale_run = cached.get(m.ResearchRun, rid)
        assert stale_run.trashed_at is not None
        actor = SimpleNamespace(
            user=cached.get(m.User, cached.get(m.Project, pid).owner_id),
            token=None,
            actor_type="human",
        )
        with factory() as restored:
            restored.get(m.ResearchRun, rid).trashed_at = None
            restored.commit()
        with pytest.raises(HTTPException) as denied:
            svc.purge(cached, actor, SimpleNamespace(), "runs", rid)
        assert denied.value.status_code == 409
        assert stale_run.trashed_at is None
    assert client.get(f"/api/runs/{rid}").status_code == 200
