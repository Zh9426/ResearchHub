"""Sprint 2 acceptance against disposable real PostgreSQL/MinIO; SYNTHETIC fixtures only."""

# ruff: noqa: F811
import hashlib
import uuid

from test_live_system import create, live  # noqa: F401


def test_real_lineage_complete_diff_history_and_provenance_trace(live):
    project = create(
        live,
        "/api/projects",
        {
            "name": "SYNTHETIC intelligence " + uuid.uuid4().hex[:6],
            "module_id": "generic",
        },
    )
    pid = project["id"]
    assert project["module_version"] == "0.2.1"
    parent = create(
        live,
        f"/api/projects/{pid}/runs",
        {"title": "SYNTHETIC provenance baseline", "run_type": "simulation"},
    )
    source = create(
        live,
        f"/api/projects/{pid}/sources",
        {"title": "SYNTHETIC source", "source_kind": "synthetic"},
    )
    for start in (0, 100):
        create(
            live,
            f"/api/runs/{parent['id']}/parameters/batch",
            {
                "parameters": [
                    {
                        "name": f"p{i:03d}",
                        "value": i,
                        "value_type": "number",
                        "source_kind": "synthetic",
                        "source_id": source["id"],
                    }
                    for i in range(start, min(start + 100, 110))
                ]
            },
        )
    child = create(
        live, f"/api/runs/{parent['id']}/clone", {"title": "SYNTHETIC child"}
    )
    values = live.get(
        f"/api/runs/{child['id']}/parameters?format=page&limit=10&offset=100"
    ).json()
    assert values["total"] == 110 and len(values["items"]) == 10
    create(
        live,
        f"/api/runs/{child['id']}/parameters/batch",
        {
            "parameters": [
                {
                    "name": "p109",
                    "value": 0,
                    "value_type": "number",
                    "unit": None,
                    "source_kind": "synthetic",
                    "source_id": source["id"],
                }
            ]
        },
    )
    diff = live.get(f"/api/runs/{child['id']}/diff?kind=parameters&limit=100").json()
    # Clone removes human confirmation only; original parameters were unconfirmed.
    assert diff["total"] == 1 and diff["items"][0]["name"] == "p109"
    assert diff["items"][0]["fields"]["value"] == {"parent": 109, "current": 0}
    for rid, value in (
        (parent["id"], {"a": 1, "b": 2}),
        (child["id"], {"b": 2, "a": 1}),
    ):
        create(
            live,
            f"/api/runs/{rid}/parameters",
            {"name": "object", "value_type": "object", "value": value},
        )
    assert (
        live.get(f"/api/runs/{child['id']}/diff?kind=parameters").json()["total"] == 1
    )
    payload = b"SYNTHETIC,0\n"
    response = live.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("synthetic-metric.csv", payload, "text/csv")},
        data={"category": "data"},
    )
    assert response.status_code == 200, response.text
    artifact = response.json()
    metric = create(
        live,
        f"/api/runs/{child['id']}/metrics",
        {
            "name": "SYNTHETIC metric",
            "value": 0,
            "unit": None,
            "status": "synthetic",
            "source_kind": "synthetic",
            "source_id": source["id"],
            "source_location": "row 2",
            "derivation": "QA fixture",
            "uncertainty": "unknown",
            "valid_conditions": "SYNTHETIC only",
            "artifact_ids": [artifact["id"]],
        },
    )
    patch = live.patch(f"/api/metrics/{metric['id']}", json={"value": 2})
    assert patch.status_code == 200, patch.text
    history = live.get(f"/api/metrics/{metric['id']}/history?limit=1").json()
    assert history["total"] == 2 and history["items"][0]["actor_type"] == "human"
    assert (
        history["items"][0]["before"]["value"] == 0
        and history["items"][0]["after"]["value"] == 2
    )
    evidence = create(
        live,
        f"/api/projects/{pid}/evidence",
        {
            "title": "SYNTHETIC evidence",
            "status": "synthetic",
            "linked_run_id": child["id"],
        },
    )
    claim = create(
        live,
        f"/api/projects/{pid}/claims",
        {
            "title": "SYNTHETIC claim",
            "statement": "QA only",
            "evidence_ids": [evidence["id"]],
        },
    )
    for kind, rid in (
        ("metrics", metric["id"]),
        ("runs", child["id"]),
        ("claims", claim["id"]),
    ):
        trace = live.get(f"/api/projects/{pid}/trace/{kind}/{rid}?limit=100")
        assert trace.status_code == 200, trace.text
        groups = trace.json()["groups"]
        assert source["id"] in {r["id"] for r in groups["sources"]["items"]}
        assert artifact["id"] in {r["id"] for r in groups["artifacts"]["items"]}
        assert child["id"] in {r["id"] for r in groups["runs"]["items"]}
    assert live.get(f"/api/artifacts/{artifact['id']}/download").content == payload
    assert artifact["checksum"] == hashlib.sha256(payload).hexdigest()
    lineage = live.get(f"/api/projects/{pid}/lineage?limit=1").json()
    assert lineage["total"] == 2 and lineage["truncated"]
    metrics = live.get(
        f"/api/projects/{pid}/metrics/query?limit=1&run_types=simulation"
    ).json()
    assert metrics["total"] == 1 and metrics["items"][0]["run"]["id"] == child["id"]


def test_real_evidence_impact_reopens_gate_and_validates_video(live):
    project = create(
        live,
        "/api/projects",
        {"name": "SYNTHETIC impact " + uuid.uuid4().hex[:6], "module_id": "generic"},
    )
    pid = project["id"]
    run = create(
        live,
        f"/api/projects/{pid}/runs",
        {"title": "SYNTHETIC prototype", "run_type": "prototype"},
    )
    evidence = create(
        live,
        f"/api/projects/{pid}/evidence",
        {
            "title": "SYNTHETIC accepted QA evidence",
            "status": "validated",
            "linked_run_id": run["id"],
        },
    )
    gate = create(
        live,
        f"/api/projects/{pid}/gates",
        {
            "gate_id": "QA-impact",
            "name": "SYNTHETIC gate",
            "stage_id": "question",
            "status": "passed",
            "evidence_ids": [evidence["id"]],
            "criteria": [
                {
                    "id": "QA-c1",
                    "description": "SYNTHETIC criterion",
                    "provenance": "QA only",
                    "status": "passed",
                    "evidence_ids": [evidence["id"]],
                }
            ],
        },
    )
    create(
        live,
        f"/api/projects/{pid}/claims",
        {"statement": "SYNTHETIC only", "evidence_ids": [evidence["id"]]},
    )
    create(
        live,
        f"/api/projects/{pid}/decisions",
        {
            "title": "SYNTHETIC decision",
            "decision": "QA only",
            "evidence_ids": [evidence["id"]],
        },
    )
    impact = live.get(f"/api/evidence/{evidence['id']}/impact").json()["groups"]
    assert all(
        impact[k]["total"] == 1 for k in ("claims", "gates", "criteria", "decisions")
    )
    response = live.patch(
        f"/api/evidence/{evidence['id']}", json={"status": "rejected"}
    )
    assert response.status_code == 200, response.text
    after = live.get(f"/api/gates/{gate['id']}").json()
    assert after["status"] == "blocked" and after["criteria"][0]["status"] != "passed"
    assert (
        live.get(f"/api/projects/{pid}/claims/query").json()["items"][0]["status"]
        == "draft"
    )
    # A minimal recognized MP4 container is a signature fixture, not a playable camera recording.
    video = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2"
    response = live.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("synthetic.mp4", video, "video/mp4")},
        data={"run_id": run["id"], "category": "data"},
    )
    assert response.status_code == 200, response.text
    assert live.get(f"/api/artifacts/{response.json()['id']}/download").content == video
    bad = live.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("bad.mp4", b"notvideo", "video/mp4")},
        data={"category": "data"},
    )
    assert bad.status_code == 422
