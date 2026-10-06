"""Sprint 1 acceptance writes SYNTHETIC fixtures to real opt-in PostgreSQL/MinIO QA."""

# ruff: noqa: F811
import hashlib
import io
import json
import uuid
import zipfile

from test_live_system import create, live  # noqa: F401


def test_real_hdsp_clone_parameters_highlight_and_file_reference(live):
    p = create(
        live,
        "/api/projects",
        {
            "name": "SYNTHETIC HDSP workflow " + uuid.uuid4().hex[:6],
            "module_id": "hdsp",
        },
    )
    pid = p["id"]
    parent = create(
        live,
        f"/api/projects/{pid}/runs",
        {
            "title": "SYNTHETIC HDSP baseline",
            "run_type": "acoustic_simulation",
            "status": "completed",
            "scientific_outcome": "negative_result",
            "human_conclusion": "SYNTHETIC QA, no scientific claim",
        },
    )
    create(
        live,
        f"/api/runs/{parent['id']}/parameters/batch",
        {
            "parameters": [
                {
                    "name": "pressure",
                    "value": 1,
                    "value_type": "number",
                    "unit": "MPa",
                    "source_kind": "synthetic",
                    "source_location": "QA fixture",
                    "is_confirmed": True,
                },
                {"name": "beta", "value": None, "value_type": "number"},
            ]
        },
    )
    uploaded = live.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("synthetic.csv", b"SYNTHETIC,1\n", "text/csv")},
        data={"run_id": parent["id"], "category": "data"},
    )
    assert uploaded.status_code == 200, uploaded.text
    artifact = uploaded.json()
    child = create(
        live,
        f"/api/runs/{parent['id']}/clone",
        {
            "title": "SYNTHETIC HDSP pressure comparison",
            "artifact_ids": [artifact["id"]],
        },
    )
    assert (
        child["status"] == "planned"
        and child["scientific_outcome"] == "unknown"
        and not child["human_conclusion"]
        and not child["is_highlighted"]
    )
    ctx = live.get(f"/api/runs/{child['id']}/context").json()
    assert all(not row["is_confirmed"] for row in ctx["parameters"])
    assert (
        ctx["metrics"] == []
        and ctx["artifacts"] == []
        and ctx["referenced_artifacts"][0]["id"] == artifact["id"]
    )
    create(
        live,
        f"/api/runs/{child['id']}/parameters/batch",
        {
            "parameters": [
                {
                    "name": "pressure",
                    "value": 2,
                    "value_type": "number",
                    "unit": "MPa",
                    "source_kind": "synthetic",
                    "source_location": "QA fixture",
                }
            ]
        },
    )
    ctx = live.get(f"/api/runs/{child['id']}/context").json()
    pressure = next(
        item
        for item in ctx["changes_from_parent"]["parameters"]
        if item["name"] == "pressure"
    )
    assert pressure["fields"]["value"] == {"parent": 1, "current": 2}
    starred = live.patch(
        f"/api/runs/{parent['id']}/highlight",
        json={
            "is_highlighted": True,
            "type": "negative_result",
            "note": "SYNTHETIC QA only",
        },
    ).json()
    assert (
        starred["status"] == "completed"
        and starred["scientific_outcome"] == "negative_result"
    )
    page = live.get(
        f"/api/projects/{pid}/runs/query?is_highlighted=true&limit=1"
    ).json()
    assert page["total"] == 1 and page["items"][0]["id"] == parent["id"]
    download = live.get(f"/api/artifacts/{artifact['id']}/download")
    assert hashlib.sha256(download.content).hexdigest() == artifact["checksum"]
    assert live.get(f"/api/projects/{pid}/artifacts/query").json()["total"] == 1


def test_real_ice_negative_measurement_activity_audit_and_export(live):
    p = create(
        live,
        "/api/projects",
        {
            "name": "SYNTHETIC ICE measurement " + uuid.uuid4().hex[:6],
            "module_id": "ice-sonocuring",
        },
    )
    pid = p["id"]
    run = create(
        live,
        f"/api/projects/{pid}/runs",
        {
            "title": "SYNTHETIC hydrophone negative result",
            "run_type": "hydrophone_measurement",
            "context_data": {
                "device": "SYNTHETIC hydrophone",
                "calibration_record": "Unknown, QA only",
            },
            "status": "completed",
            "scientific_outcome": "negative_result",
            "observation": "SYNTHETIC QA; no distinguishable change",
            "human_conclusion": "SYNTHETIC QA only",
        },
    )
    artifact = live.post(
        f"/api/projects/{pid}/artifacts",
        files={
            "file": ("hydrophone.csv", b"SYNTHETIC,x,pressure\n0,0,0\n", "text/csv")
        },
        data={"run_id": run["id"], "category": "data"},
    ).json()
    tag = create(live, f"/api/projects/{pid}/tags", {"name": "SYNTHETIC negative"})
    assert (
        live.patch(f"/api/runs/{run['id']}", json={"tag_ids": [tag["id"]]}).status_code
        == 200
    )
    assert (
        live.get(f"/api/projects/{pid}/runs/query?tag_id={tag['id']}").json()["total"]
        == 1
    )
    before = live.get(f"/api/audit?format=page&project_id={pid}").json()["total"]
    create(live, "/api/activity/clear", {"project_id": pid, "confirm": True})
    assert (
        live.get(f"/api/audit?format=page&project_id={pid}").json()["total"]
        == before + 1
    )
    assert all(
        row["action"] == "clear_activity_display"
        for row in live.get(f"/api/activity?project_id={pid}").json()
    )
    exact = json.loads(
        live.get(f"/api/projects/{pid}/audit/export").text.splitlines()[0]
    )
    assert exact["project_id"] == pid
    exported = live.get(f"/api/projects/{pid}/export?include_files=true")
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        module = json.loads(archive.read("module-manifest.json"))
        assert module == p["module_snapshot"]
        rows = [json.loads(line) for line in archive.read("runs.jsonl").splitlines()]
        assert rows[0]["scientific_outcome"] == "negative_result"
        assert (
            hashlib.sha256(
                archive.read(f"artifacts/{artifact['id']}/{artifact['filename']}")
            ).hexdigest()
            == artifact["checksum"]
        )
        assert len(archive.read("audit.jsonl").splitlines()) == before + 1
    assert (
        "SYNTHETIC hydrophone negative result"
        in live.get(f"/api/projects/{pid}/research-log").text
    )


def test_real_bundle_preview_confirm_hash_and_replay(live):
    p = create(
        live,
        "/api/projects",
        {"name": "SYNTHETIC Bundle " + uuid.uuid4().hex[:6], "module_id": "generic"},
    )
    pid = p["id"]
    content = b"SYNTHETIC,1\n"
    checksum = hashlib.sha256(content).hexdigest()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in {
            "researchhub-run.json": {
                "title": "SYNTHETIC imported run",
                "run_type": "simulation",
            },
            "parameters.json": [
                {"name": "unknown_input", "value": None, "value_type": "number"}
            ],
            "metrics.json": [{"name": "sample", "value": 0, "status": "synthetic"}],
            "manifest.json": {
                "artifacts": [
                    {
                        "path": "artifacts/result.csv",
                        "filename": "result.csv",
                        "mime_type": "text/csv",
                        "category": "data",
                        "checksum": checksum,
                    }
                ]
            },
        }.items():
            archive.writestr(name, json.dumps(value))
        archive.writestr("artifacts/result.csv", content)
    preview = live.post(
        f"/api/projects/{pid}/imports/preview",
        files={"file": ("bundle.zip", stream.getvalue(), "application/zip")},
    )
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan["parameters"][0]["value"] is None and plan["metrics"][0]["value"] == 0
    assert live.get(f"/api/projects/{pid}/runs/query").json()["total"] == 0
    payload = {
        "preview_id": plan["preview_id"],
        "digest": plan["digest"],
        "confirm": True,
    }
    imported = create(live, f"/api/projects/{pid}/imports/confirm", payload)
    assert (
        imported["parameters"][0]["value"] is None
        and not imported["parameters"][0]["is_confirmed"]
    )
    artifact = imported["artifacts"][0]
    assert (
        hashlib.sha256(
            live.get(f"/api/artifacts/{artifact['id']}/download").content
        ).hexdigest()
        == checksum
    )
    assert (
        live.post(f"/api/projects/{pid}/imports/confirm", json=payload).status_code
        == 409
    )
    assert live.get(f"/api/projects/{pid}/runs/query").json()["total"] == 1
    audit = live.get(f"/api/audit?project_id={pid}&action=import_bundle").json()
    assert len(audit) == 1 and audit[0]["actor_type"] == "human"
