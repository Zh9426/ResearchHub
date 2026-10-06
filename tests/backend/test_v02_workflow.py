"""Workflow unit tests use isolated SQLite and object substitutes, not deployment acceptance."""

import copy
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from test_api import client as api_client
from test_api import login, project, run

from apps.api.researchhub import models as m

client = api_client


def test_date_upper_bound_includes_whole_day_and_global_tasks_page(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    with client.app.state.session_factory() as db:
        db.get(m.ResearchRun, rid).created_at = datetime(
            2026, 10, 6, 18, 0, tzinfo=timezone.utc
        )
        db.commit()
    assert (
        client.get(f"/api/projects/{pid}/runs/query?date_to=2026-10-06").json()["total"]
        == 1
    )
    assert (
        client.get(f"/api/projects/{pid}/runs/query?date_to=2026-10-05").json()["total"]
        == 0
    )
    for i in range(3):
        client.post(
            f"/api/projects/{pid}/tasks",
            json={"title": f"Task {i}", "status": "done" if i == 0 else "todo"},
        )
    page = client.get(
        f"/api/tasks?format=page&project_id={pid}&exclude_status=done&limit=1&offset=1"
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["offset"] == 1
    assert client.get("/api/tasks?limit=0").status_code == 422


def test_worksheet_queries_schema_values_beyond_custom_page_without_losing_units(
    client,
):
    login(client)
    pid = project(client, "hdsp")
    rid = run(client, pid, run_type="acoustic_simulation")
    with client.app.state.session_factory() as db:
        for i in range(101):
            db.add(m.Parameter(run_id=rid, name=f"custom-{i}", value=0))
        db.add(
            m.Parameter(
                run_id=rid,
                name="pressure",
                value=1.4,
                unit=None,
                source_kind="literature",
                source_location="Table2",
            )
        )
        db.add(m.Metric(run_id=rid, name="p_max", value=0, unit=None))
        db.commit()
    ctx = client.get(f"/api/runs/{rid}/context").json()
    assert ctx["parameters_total"] == 102 and len(ctx["parameters"]) == 100
    assert ctx["worksheet_parameters"][0]["name"] == "pressure"
    assert ctx["worksheet_parameters"][0]["unit"] is None
    assert ctx["worksheet_metrics"][0]["unit"] is None
    assert (
        ctx["parameter_diff_incomplete"] and not ctx["worksheet_parameters_incomplete"]
    )


def ai(client):
    response = client.post(
        "/api/auth/tokens",
        json={"name": "AI", "scopes": ["research:read", "research:write"]},
    )
    client.headers["Authorization"] = "Bearer " + response.json()["token"]


def bundle(run_data=None, parameters=None, metrics=None, artifact=False, extra=None):
    values = {
        "researchhub-run.json": {
            "title": "Imported synthetic simulation",
            "run_type": "simulation",
            **(run_data or {}),
        },
        "parameters.json": parameters or [],
        "metrics.json": metrics or [],
        "manifest.json": {"artifacts": []},
    }
    files = {}
    if artifact:
        content = b"synthetic,1\n"
        values["manifest.json"]["artifacts"] = [
            {
                "path": "artifacts/result.csv",
                "filename": "result.csv",
                "mime_type": "text/csv",
                "category": "data",
                "checksum": hashlib.sha256(content).hexdigest(),
                "metadata": {"provenance": "SYNTHETIC"},
            }
        ]
        files["artifacts/result.csv"] = content
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in values.items():
            archive.writestr(name, json.dumps(value))
        for name, content in {**files, **(extra or {})}.items():
            archive.writestr(name, content)
    return stream.getvalue()


def preview(client, pid, data):
    return client.post(
        f"/api/projects/{pid}/imports/preview",
        files={"file": ("bundle.zip", data, "application/zip")},
    )


def confirm(client, pid, response):
    return client.post(
        f"/api/projects/{pid}/imports/confirm",
        json={
            "preview_id": response["preview_id"],
            "digest": response["digest"],
            "confirm": True,
        },
    )


def counts(client):
    with client.app.state.session_factory() as db:
        return {
            cls.__tablename__: db.scalar(select(func.count()).select_from(cls))
            for cls in (m.ResearchRun, m.Parameter, m.Metric, m.Artifact, m.AuditLog)
        }


def test_capabilities_defaults_user_selection_and_frozen_upgrade(client):
    login(client)
    pid = project(client, "hdsp")
    assert len(client.get("/api/capabilities").json()) == 7
    before = client.get(f"/api/projects/{pid}").json()
    assert (
        before["enabled_capabilities"]
        == before["module_snapshot"]["default_capabilities"]
    )
    assert (
        client.patch(
            f"/api/projects/{pid}", json={"enabled_capabilities": ["lab_experiment"]}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/projects/{pid}", json={"enabled_capabilities": ["missing"]}
        ).status_code
        == 422
    )
    latest = copy.deepcopy(client.app.state.modules["hdsp"])
    latest["version"] = "0.2.1"
    latest["default_capabilities"] = ["hardware_system"]
    client.app.state.modules["hdsp"] = latest
    plan = client.get(f"/api/projects/{pid}/module-upgrade/preview").json()
    response = client.post(
        f"/api/projects/{pid}/module-upgrade",
        json={
            "confirm": True,
            "expected_version": before["module_version"],
            "expected_target_digest": plan["target_digest"],
        },
    )
    assert response.status_code == 200
    assert response.json()["enabled_capabilities"] == ["lab_experiment"]


def test_context_fields_are_frozen_and_typed(client):
    login(client)
    pid = project(client)
    rid = run(
        client,
        pid,
        context_data={"repository": "https://example.test/research", "branch": "main"},
    )
    assert client.get(f"/api/runs/{rid}").json()["context_data"]["branch"] == "main"
    assert (
        client.patch(
            f"/api/runs/{rid}", json={"context_data": {"repository": 12}}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/runs/{rid}", json={"context_data": {"pressure": 12}}
        ).status_code
        == 422
    )
    with client.app.state.session_factory() as db:
        p = db.get(m.Project, pid)
        old = copy.deepcopy(p.module_snapshot)
        old.pop("context_fields")
        old.pop("run_forms")
        p.module_snapshot = old
        db.commit()
    assert (
        client.patch(
            f"/api/runs/{rid}", json={"context_data": {"repository": "new"}}
        ).status_code
        == 422
    )


def test_highlight_independent_and_ai_requires_explicit_request(client):
    login(client)
    pid = project(client)
    rid = run(client, pid, status="completed", scientific_outcome="negative_result")
    assert (
        client.patch(f"/api/runs/{rid}", json={"is_highlighted": True}).status_code
        == 422
    )
    ai(client)
    assert (
        client.patch(
            f"/api/runs/{rid}/highlight", json={"is_highlighted": True}
        ).status_code
        == 403
    )
    result = client.patch(
        f"/api/runs/{rid}/highlight",
        json={
            "is_highlighted": True,
            "type": "major",
            "note": "User requested",
            "user_requested": True,
        },
    )
    assert result.status_code == 200
    assert result.json()["scientific_outcome"] == "negative_result"
    assert result.json()["status"] == "completed"
    assert result.json()["highlighted_at"] and result.json()["highlighted_by"]
    audit = client.get("/api/audit?action=set_run_highlight").json()
    assert len(audit) == 1 and audit[0]["actor_type"] == "codex"
    assert (
        client.patch(
            f"/api/runs/{rid}/highlight",
            json={"is_highlighted": False, "user_requested": True},
        ).json()["highlighted_at"]
        is None
    )


def test_clone_resets_results_confirmation_and_references_files(client):
    login(client)
    pid = project(client)
    rid = run(
        client,
        pid,
        status="completed",
        scientific_outcome="positive_result",
        human_conclusion="Confirmed parent result",
        observation="Parent observation",
        context_data={"repository": "code", "branch": "baseline"},
    )
    client.post(
        f"/api/runs/{rid}/parameters",
        json={"name": "pressure", "value": 2, "is_confirmed": True},
    )
    client.post(
        f"/api/runs/{rid}/metrics",
        json={"name": "score", "value": 0.9, "status": "validated"},
    )
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        data={"run_id": rid, "category": "data"},
        files={"file": ("test.csv", b"synthetic,1\n", "text/csv")},
    ).json()
    client.patch(f"/api/runs/{rid}/highlight", json={"is_highlighted": True})
    ai(client)
    created = client.post(
        f"/api/runs/{rid}/clone",
        json={"title": "Candidate", "artifact_ids": [artifact["id"]]},
    )
    assert created.status_code == 200, created.text
    clone = created.json()
    assert (
        clone["parent_run_id"] == rid
        and clone["status"] == "planned"
        and clone["scientific_outcome"] == "unknown"
    )
    assert (
        not clone["human_conclusion"]
        and not clone["observation"]
        and not clone["is_highlighted"]
    )
    context = client.get(f"/api/runs/{clone['id']}/context").json()
    assert context["parameters"][0]["is_confirmed"] is False
    assert context["metrics"] == [] and context["artifacts"] == []
    assert context["referenced_artifacts"][0]["id"] == artifact["id"]
    assert len(client.app.state.objects.data) == 1
    assert (
        client.get(f"/api/projects/{pid}/artifacts/query?run_id={clone['id']}").json()[
            "total"
        ]
        == 1
    )
    client.post(
        f"/api/runs/{clone['id']}/parameters/batch",
        json={"parameters": [{"name": "pressure", "value": 3}]},
    )
    difference = client.get(f"/api/runs/{clone['id']}/context").json()[
        "changes_from_parent"
    ]["parameters"][0]
    assert difference["fields"]["value"] == {"parent": 2, "current": 3}


def test_batch_upsert_atomic_duplicate_and_ai_confirmed_guard(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    url = f"/api/runs/{rid}/parameters/batch"
    assert (
        client.post(url, json={"parameters": [{"name": "x", "value": 1}]}).status_code
        == 200
    )
    assert (
        client.post(url, json={"parameters": [{"name": "x", "value": 2}]}).status_code
        == 200
    )
    assert len(client.get(f"/api/runs/{rid}/parameters").json()) == 1
    assert (
        client.post(
            url, json={"parameters": [{"name": "y"}, {"name": "y"}]}
        ).status_code
        == 422
    )
    client.post(
        url, json={"parameters": [{"name": "x", "value": 2, "is_confirmed": True}]}
    )
    ai(client)
    assert (
        client.post(
            url,
            json={"parameters": [{"name": "z", "value": 3}, {"name": "x", "value": 4}]},
        ).status_code
        == 403
    )
    assert [p["name"] for p in client.get(f"/api/runs/{rid}/parameters").json()] == [
        "x"
    ]
    metric_url = f"/api/runs/{rid}/metrics/batch"
    for value in (1, 2):
        assert (
            client.post(
                metric_url,
                json={
                    "metrics": [
                        {"name": "score", "value": value, "status": "simulated"}
                    ]
                },
            ).status_code
            == 200
        )
    assert len(client.get(f"/api/runs/{rid}/metrics").json()) == 1


def test_pagination_filters_summary_context_and_search(client):
    login(client)
    pid = project(client)
    ids = [run(client, pid, title=f"Candidate {index:02}") for index in range(7)]
    client.patch(f"/api/runs/{ids[2]}/highlight", json={"is_highlighted": True})
    page = client.get(
        f"/api/projects/{pid}/runs/query?limit=2&offset=2&sort=title&direction=asc&q=Candidate"
    ).json()
    assert page["total"] == 7 and [r["title"] for r in page["items"]] == [
        "Candidate 02",
        "Candidate 03",
    ]
    response = client.get(f"/api/projects/{pid}/runs?limit=2&is_highlighted=true")
    assert response.headers["X-Total-Count"] == "1" and len(response.json()) == 1
    for query in ("limit=101", "offset=-1", "sort=object_key", "is_highlighted=yes"):
        assert client.get(f"/api/projects/{pid}/runs/query?{query}").status_code == 422
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["counts"]["runs"] == 7 and len(summary["recent_runs"]) == 5
    assert len(summary["highlighted_runs"]) == 1 and "runs" not in summary
    context = client.get(f"/api/projects/{pid}/context?collections=tags&limit=2").json()
    assert context["runs"] == [] and context["activity"] == []
    search = client.get("/api/search?q=Candidate&kind=runs&limit=3").json()
    assert search["total"] == 7 and len(search["items"]) == 3
    ev = client.post(
        f"/api/projects/{pid}/evidence",
        json={"title": "Observation", "linked_run_id": ids[0]},
    ).json()
    assert (
        client.get(f"/api/projects/{pid}/evidence/query?run_id={ids[0]}").json()[
            "items"
        ][0]["id"]
        == ev["id"]
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("runs", {"title": "Tagged", "run_type": "simulation"}),
        ("evidence", {"title": "Tagged"}),
        ("notes", {"title": "Tagged"}),
        ("decisions", {"title": "Tagged"}),
        ("tasks", {"title": "Tagged"}),
    ],
)
def test_tags_same_project_filter_and_trash_hiding(client, kind, payload):
    login(client)
    pid, other = project(client), project(client)
    tag = client.post(f"/api/projects/{pid}/tags", json={"name": "baseline"}).json()
    foreign = client.post(
        f"/api/projects/{other}/tags", json={"name": "foreign"}
    ).json()
    assert (
        client.post(
            f"/api/projects/{pid}/{kind}", json={**payload, "tag_ids": [foreign["id"]]}
        ).status_code
        == 422
    )
    created = client.post(
        f"/api/projects/{pid}/{kind}", json={**payload, "tag_ids": [tag["id"]]}
    )
    assert created.status_code == 200, created.text
    assert created.json()["tag_ids"] == [tag["id"]]
    assert (
        client.get(f"/api/projects/{pid}/{kind}/query?tag_id={tag['id']}").json()[
            "total"
        ]
        == 1
    )
    client.delete(f"/api/tags/{tag['id']}")
    assert client.get(f"/api/{kind}/{created.json()['id']}").json()["tag_ids"] == []
    assert (
        client.get(f"/api/projects/{pid}/{kind}/query?tag_id={tag['id']}").json()[
            "total"
        ]
        == 0
    )


def test_activity_clear_hides_only_feed_audit_exports_survive(client):
    login(client)
    pid, other = project(client), project(client)
    run(client, pid)
    run(client, other)
    before = counts(client)["audit_logs"]
    cleared = client.post(
        "/api/activity/clear", json={"project_id": pid, "confirm": True}
    )
    assert cleared.status_code == 200
    activity = client.get(f"/api/activity?project_id={pid}&format=page").json()
    assert all(row["action"] == "clear_activity_display" for row in activity["items"])
    assert (
        client.get(f"/api/activity?project_id={other}&format=page").json()["total"] > 0
    )
    assert counts(client)["audit_logs"] == before + 1
    assert len(client.get(f"/api/projects/{pid}/audit/export").text.splitlines()) > 1
    assert (
        "action,resource_type"
        in client.get(f"/api/projects/{pid}/audit/export?format=csv").text.splitlines()[
            0
        ]
    )
    assert (
        len(client.get("/api/audit/export").text.splitlines())
        == counts(client)["audit_logs"]
    )
    ai(client)
    assert client.post("/api/activity/clear", json={"confirm": True}).status_code == 403


def test_exports_are_readonly_complete_frozen_and_hash_checked(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    client.post(
        f"/api/runs/{rid}/parameters", json={"name": "threshold", "value": None}
    )
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        data={"run_id": rid, "category": "data"},
        files={"file": ("test.csv", b"synthetic,1\n", "text/csv")},
    ).json()
    before = counts(client)
    response = client.get(f"/api/projects/{pid}/export?include_files=true")
    assert response.status_code == 200, (
        response.text if response.status_code != 200 else ""
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert {
            "runs.csv",
            "parameters.csv",
            "metrics.csv",
            "evidence.csv",
            "claims.csv",
            "decisions.csv",
            "activity.csv",
            "audit.jsonl",
            "module-manifest.json",
            "README.md",
        } <= set(archive.namelist())
        assert archive.read(f"artifacts/{artifact['id']}/test.csv") == b"synthetic,1\n"
        assert json.loads(archive.read("module-manifest.json"))["version"] == "0.2.0"
        assert json.loads(archive.read("parameters.jsonl"))["value"] is None
    assert client.get(f"/api/projects/{pid}/research-log").status_code == 200
    assert counts(client) == before
    key = next(iter(client.app.state.objects.data))
    client.app.state.objects.data[key] = b"corrupted"
    assert (
        client.get(f"/api/projects/{pid}/export?include_files=true").status_code == 409
    )


def test_bundle_preview_has_no_scientific_writes_confirm_atomic_provenance(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid = project(client)
    before = counts(client)
    response = preview(
        client,
        pid,
        bundle(
            parameters=[{"name": "pressure", "value": 1, "source_kind": "synthetic"}],
            metrics=[{"name": "score", "value": 0.8, "status": "simulated"}],
            artifact=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert counts(client) == before
    assert response.json()["counts"] == {"parameters": 1, "metrics": 1, "artifacts": 1}
    imported = confirm(client, pid, response.json())
    assert imported.status_code == 200, imported.text
    assert imported.json()["parameters"][0]["is_confirmed"] is False
    assert (
        imported.json()["artifacts"][0]["metadata"]["import_provenance"][
            "bundle_digest"
        ]
        == response.json()["digest"]
    )
    assert (
        client.get(f"/api/projects/{pid}/audit?action=import_bundle").json()["total"]
        == 1
    )
    assert confirm(client, pid, response.json()).status_code == 409


@pytest.mark.parametrize(
    "data",
    [
        bundle(run_data={"human_conclusion": "Confirmed"}),
        bundle(parameters=[{"name": "x", "is_confirmed": True}]),
        bundle(metrics=[{"name": "x", "status": "measured"}]),
        bundle(extra={"../evil.txt": "bad"}),
        bundle(extra={"unlisted.txt": "bad"}),
        bundle(parameters=[{"name": "x"}, {"name": "x"}]),
    ],
)
def test_bundle_rejects_bad_metadata_authority_and_paths(
    client, data, tmp_path, monkeypatch
):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid = project(client)
    before = counts(client)
    assert preview(client, pid, data).status_code == 422
    assert counts(client) == before
    assert list((tmp_path / "imports").iterdir()) == []


def test_bundle_rejects_symlink_bomb_duplicate_and_hash(client, tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid = project(client)
    for kind in ("symlink", "bomb", "duplicate", "hash"):
        stream = io.BytesIO(bundle(artifact=True))
        with zipfile.ZipFile(stream, "a", zipfile.ZIP_DEFLATED) as archive:
            if kind == "symlink":
                info = zipfile.ZipInfo("artifacts/link")
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                archive.writestr(info, "../../etc/passwd")
            elif kind == "bomb":
                archive.writestr("artifacts/bomb", b"0" * (2 * 1024 * 1024))
            elif kind == "duplicate":
                archive.writestr("metrics.json", "[]")
            else:
                archive.writestr("artifacts/result.csv", b"bad-checksum")
        assert preview(client, pid, stream.getvalue()).status_code in (413, 422)


def test_bundle_object_failure_rolls_back_and_persists_cleanup(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid = project(client)
    planned = preview(client, pid, bundle(artifact=True)).json()
    before = counts(client)

    def fail(key, stream, size, mime):
        client.app.state.objects.data[key] = stream.read()
        raise OSError("simulated upload failure")

    client.app.state.objects.put = fail
    assert confirm(client, pid, planned).status_code == 503
    assert counts(client) == before
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ObjectDeletion)) == 1
        assert db.get(m.ImportPreview, planned["preview_id"]).consumed_at is None


def test_bundle_owner_expiry_module_digest_and_authority(client, tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid, other = project(client), project(client)
    planned = preview(client, pid, bundle()).json()
    assert confirm(client, other, planned).status_code == 404
    bad = {**planned, "digest": "0" * 64}
    assert confirm(client, pid, bad).status_code == 409
    with client.app.state.session_factory() as db:
        row = db.get(m.ImportPreview, planned["preview_id"])
        row.expires_at = m.now() - timedelta(seconds=1)
        db.commit()
    assert confirm(client, pid, planned).status_code == 409
    ai(client)
    assert preview(client, pid, bundle()).status_code == 403


def test_clone_does_not_inherit_experiment_facts_and_context_patch_merges(client):
    login(client)
    pid = project(client)
    parent = client.post(
        f"/api/projects/{pid}/runs",
        json={
            "title": "Lab parent",
            "run_type": "physical_experiment",
            "context_data": {
                "experiment_date": "2026-10-01",
                "operator": "Synthetic operator",
                "environment_conditions": "Synthetic tank",
                "unexpected_events": "Parent event",
            },
        },
    ).json()
    patched = client.patch(
        f"/api/runs/{parent['id']}",
        json={"context_data": {"sample_batch": "SYNTHETIC-A"}},
    )
    assert patched.status_code == 200
    assert patched.json()["context_data"]["experiment_date"] == "2026-10-01"
    child = client.post(f"/api/runs/{parent['id']}/clone", json={"title": "Lab child"})
    assert child.status_code == 200
    assert child.json()["context_data"] == {"environment_conditions": "Synthetic tank"}
    empty = client.post(
        f"/api/runs/{parent['id']}/clone",
        json={"title": "No environment", "inherit_environment": False},
    )
    assert empty.json()["context_data"] == {}


def test_artifact_tags_and_context_feed_respects_clear(client):
    login(client)
    pid = project(client)
    tag = client.post(f"/api/projects/{pid}/tags", json={"name": "figure"}).json()
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        data={"category": "data"},
        files={"file": ("synthetic.csv", b"synthetic,1\n", "text/csv")},
    ).json()
    updated = client.patch(
        f"/api/artifacts/{artifact['id']}", json={"tag_ids": [tag["id"]]}
    )
    assert updated.status_code == 200 and updated.json()["tag_ids"] == [tag["id"]]
    assert (
        client.get(f"/api/projects/{pid}/artifacts/query?tag_id={tag['id']}").json()[
            "total"
        ]
        == 1
    )
    assert (
        client.patch(
            f"/api/artifacts/{artifact['id']}", json={"object_key": "arbitrary"}
        ).status_code
        == 422
    )
    client.post("/api/activity/clear", json={"project_id": pid, "confirm": True})
    assert all(
        row["action"] == "clear_activity_display"
        for row in client.get(
            f"/api/projects/{pid}/context?collections=activity"
        ).json()["activity"]
    )


def test_bundle_checksum_mismatch_and_stage_tampering_rejected(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("IMPORT_STAGING_DIR", str(tmp_path / "imports"))
    login(client)
    pid = project(client)
    original = bundle(artifact=True)
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as archive,
        zipfile.ZipFile(stream, "w") as changed,
    ):
        for name in archive.namelist():
            data = archive.read(name)
            if name == "manifest.json":
                value = json.loads(data)
                value["artifacts"][0]["checksum"] = "0" * 64
                data = json.dumps(value).encode()
            changed.writestr(name, data)
    before = counts(client)
    assert preview(client, pid, stream.getvalue()).status_code == 422
    planned = preview(client, pid, original).json()
    (tmp_path / "imports" / (planned["preview_id"] + ".zip")).write_bytes(
        bundle(run_data={"title": "Tampered"})
    )
    assert confirm(client, pid, planned).status_code == 409
    assert counts(client) == before
