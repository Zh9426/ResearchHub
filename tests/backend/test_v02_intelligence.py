"""Research intelligence unit checks; SQLite/object substitutes are not deployment acceptance."""

import copy

import pytest
from pydantic import ValidationError
from test_api import client as api_client
from test_api import login, project, run

from apps.api.researchhub import models as m
from apps.api.researchhub.modules import Manifest

client = api_client


def artifact(client, pid, filename="data.csv"):
    response = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": (filename, b"x,1", "text/csv")},
        data={"category": "data"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def make(client, pid, kind, **data):
    response = client.post(f"/api/projects/{pid}/{kind}", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_metric_provenance_history_preserves_updates_and_ai_authority(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    source = make(client, pid, "sources", title="Calibration", source_kind="measured")
    metric = client.post(
        f"/api/runs/{rid}/metrics",
        json={
            "name": "threshold",
            "value": 2,
            "source_kind": "measured",
            "source_id": source["id"],
            "source_location": "row 2",
            "derivation": "mean of three replicates",
            "uncertainty": "±0.1",
            "valid_conditions": "25 C",
            "artifact_ids": [],
        },
    )
    assert metric.status_code == 200, metric.text
    mid = metric.json()["id"]
    assert (
        client.patch(
            f"/api/metrics/{mid}", json={"value": 3, "status": "validated"}
        ).status_code
        == 200
    )
    page = client.get(f"/api/metrics/{mid}/history?limit=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    change = page["items"][0]
    assert change["before"]["value"] == 2 and change["after"]["value"] == 3
    assert change["after"]["derivation"] == "mean of three replicates"
    token = client.post(
        "/api/auth/tokens",
        json={"name": "AI", "scopes": ["research:read", "research:write"]},
    ).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert (
        client.patch(f"/api/metrics/{mid}", json={"derivation": "new"}).status_code
        == 403
    )


def test_parameter_history_survives_trash_without_activity_filter(client):
    login(client)
    rid = run(client, project(client))
    record = client.post(
        f"/api/runs/{rid}/parameters", json={"name": "temperature", "value": 20}
    ).json()
    iid = record["id"]
    client.patch(
        f"/api/parameters/{iid}",
        json={"value": 21, "source_kind": "calibrated", "is_confirmed": True},
    )
    client.delete(f"/api/parameters/{iid}")
    client.post("/api/activity/clear", json={"confirm": True})
    page = client.get(f"/api/parameters/{iid}/history?limit=1&offset=1").json()
    assert (
        page["total"] == 3 and page["items"][0]["after"]["source_kind"] == "calibrated"
    )
    assert client.get(f"/api/parameters/{iid}/history?limit=0").status_code == 422


def test_provenance_links_reject_cross_project_and_batch_preserves(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    foreign = make(client, project(client), "sources", title="Other")
    assert (
        client.post(
            f"/api/runs/{rid}/metrics", json={"name": "bad", "source_id": foreign["id"]}
        ).status_code
        == 422
    )
    source = make(client, pid, "sources", title="Local")
    payload = {
        "name": "score",
        "value": 1,
        "source_id": source["id"],
        "source_kind": "derived",
        "derivation": "ratio",
    }
    response = client.post(
        f"/api/runs/{rid}/metrics/batch", json={"metrics": [payload]}
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["derivation"] == "ratio"


def test_run_values_page_and_full_diff_beyond_one_hundred(client):
    login(client)
    pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    with client.app.state.session_factory() as db:
        for i in range(105):
            db.add(m.Parameter(run_id=parent, name=f"p{i:03}", value=i))
            db.add(m.Parameter(run_id=child, name=f"p{i:03}", value=i + 1))
        db.commit()
    page = client.get(
        f"/api/runs/{child}/parameters?format=page&limit=2&offset=100&q=p"
    ).json()
    assert page["total"] == 105 and len(page["items"]) == 2
    legacy = client.get(f"/api/runs/{child}/parameters")
    assert len(legacy.json()) == 100 and legacy.headers["X-Total-Count"] == "105"
    diff = client.get(
        f"/api/runs/{child}/diff?kind=parameters&limit=2&offset=100"
    ).json()
    assert diff["total"] == 105 and len(diff["items"]) == 2
    assert diff["items"][0]["fields"]["value"] == {"parent": 100, "current": 101}
    assert (
        client.get(
            f"/api/runs/{child}/diff?other_run_id={run(client, project(client))}"
        ).status_code
        == 422
    )
    lineage = client.get(f"/api/projects/{pid}/lineage?limit=1&offset=1").json()
    assert lineage["total"] == 2 and lineage["truncated"]
    assert len(lineage["nodes"][0]["parameter_change_summary"]["names"]) <= 5


def test_trace_reverse_claims_sources_and_evidence_impact(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    source = make(client, pid, "sources", title="Paper")
    parameter = client.post(
        f"/api/runs/{rid}/parameters",
        json={"name": "threshold", "source_id": source["id"]},
    ).json()
    evidence = make(
        client,
        pid,
        "evidence",
        title="Measurement",
        status="measured",
        linked_run_id=rid,
        linked_source_id=source["id"],
    )
    direct = make(client, pid, "claims", statement="Direct", run_ids=[rid])
    indirect = make(
        client, pid, "claims", statement="Indirect", evidence_ids=[evidence["id"]]
    )
    decision = make(
        client, pid, "decisions", title="Proceed", evidence_ids=[evidence["id"]]
    )
    stage = client.app.state.modules["generic"]["research_stages"][0]["id"]
    gate = make(
        client,
        pid,
        "gates",
        gate_id="g",
        stage_id=stage,
        name="Gate",
        status="passed",
        evidence_ids=[evidence["id"]],
        criteria=[
            {
                "id": "c",
                "description": "Measure",
                "status": "passed",
                "evidence_ids": [evidence["id"]],
            }
        ],
    )
    trace = client.get(f"/api/projects/{pid}/trace/runs/{rid}?limit=1").json()
    assert trace["groups"]["claims"]["total"] == 2
    trace2 = client.get(f"/api/projects/{pid}/trace/claims/{indirect['id']}").json()
    assert trace2["groups"]["runs"]["items"][0]["id"] == rid
    src = client.get(f"/api/projects/{pid}/trace/sources/{source['id']}").json()
    assert src["groups"]["parameters"]["items"][0]["id"] == parameter["id"]
    impact = client.get(f"/api/evidence/{evidence['id']}/impact").json()
    assert impact["groups"]["claims"]["items"][0]["id"] == indirect["id"]
    assert impact["groups"]["decisions"]["items"][0]["id"] == decision["id"]
    assert impact["groups"]["criteria"]["total"] == 1
    client.delete(f"/api/evidence/{evidence['id']}")
    assert client.get(f"/api/evidence/{evidence['id']}/impact").status_code == 200
    assert client.get(f"/api/gates/{gate['id']}").json()["status"] == "blocked"
    assert direct["id"] != indirect["id"]


def test_project_metrics_query_joins_run_and_filters_hidden_records(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    for i in range(3):
        client.post(
            f"/api/runs/{rid}/metrics",
            json={"name": f"s{i}", "value": i, "status": "measured"},
        )
    page = client.get(
        f"/api/projects/{pid}/metrics/query?limit=1&offset=1&run_types=simulation"
    ).json()
    assert page["total"] == 3 and page["items"][0]["run"]["id"] == rid
    assert (
        client.get(f"/api/projects/{pid}/metrics/query?metric_ids=s0").json()["total"]
        == 1
    )
    client.delete(f"/api/runs/{rid}")
    assert client.get(f"/api/projects/{pid}/metrics/query").json()["total"] == 0


def test_manifest_custom_views_widgets_and_metric_direction(client):
    login(client)
    manifest = copy.deepcopy(client.app.state.modules["generic"])
    manifest["metric_schemas"] = [
        {"id": "score", "name": "Score", "value_type": "number"}
    ]
    manifest["custom_views"] = [
        {
            "id": "measurements",
            "name": "Measurements",
            "run_types": ["simulation"],
            "metric_ids": [manifest["metric_schemas"][0]["id"]],
            "layout_type": "metrics",
            "evidence_filters": {"status": ["measured"]},
        }
    ]
    manifest["dashboard_widgets"] = [
        {"id": "measurements", "name": "Metrics", "kind": "representative_metrics"}
    ]
    manifest["metric_schemas"][0]["optimization_direction"] = "target_range"
    manifest["metric_schemas"][0]["target_range"] = [1, 2]
    assert Manifest.model_validate(manifest).metric_schemas[0].target_range == [1, 2]
    for bad in ("unknown",):
        other = copy.deepcopy(manifest)
        other["dashboard_widgets"][0]["kind"] = bad
        with pytest.raises(ValidationError):
            Manifest.model_validate(other)
    other = copy.deepcopy(manifest)
    other["custom_views"][0]["run_types"] = ["missing"]
    with pytest.raises(ValidationError):
        Manifest.model_validate(other)
    other = copy.deepcopy(manifest)
    other["metric_schemas"][0]["target_range"] = [2, 1]
    with pytest.raises(ValidationError):
        Manifest.model_validate(other)


def test_manifest_filters_use_full_database_and_reference_runs(client):
    login(client)
    pid = project(client)
    simulation = run(client, pid)
    measurement = run(client, pid, run_type="measurement")
    make(
        client,
        pid,
        "evidence",
        title="Simulation",
        status="simulated",
        linked_run_id=simulation,
    )
    desired = make(
        client,
        pid,
        "evidence",
        title="Measured",
        status="measured",
        evidence_type="observation",
        linked_run_id=measurement,
    )
    make(
        client,
        pid,
        "evidence",
        title="Other type",
        status="measured",
        evidence_type="analysis",
        linked_run_id=measurement,
    )
    response = client.get(
        f"/api/projects/{pid}/evidence/query?run_types=measurement&evidence_statuses=measured&evidence_types=observation"
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["total"] == 1
        and response.json()["items"][0]["id"] == desired["id"]
    )
    artifact = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("plot.csv", b"x,1", "text/csv")},
        data={"category": "data"},
    ).json()
    client.patch(f"/api/runs/{measurement}", json={"artifact_ids": [artifact["id"]]})
    page = client.get(
        f"/api/projects/{pid}/artifacts/query?run_types=measurement&artifact_categories=data"
    ).json()
    assert page["total"] == 1 and page["items"][0]["id"] == artifact["id"]
    assert (
        client.get(f"/api/projects/{pid}/runs/query?run_types=measurement").json()[
            "total"
        ]
        == 1
    )


@pytest.mark.parametrize(
    "filename,mime,content",
    [
        ("clip.mp4", "video/mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12),
        ("clip.webm", "video/webm", b"\x1a\x45\xdf\xa3\x87\x42\x82\x84webm"),
    ],
)
def test_short_video_upload_signature_validation(client, filename, mime, content):
    login(client)
    pid = project(client)
    response = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": (filename, content, mime)},
        data={"category": "data"},
    )
    assert response.status_code == 200, response.text
    bad = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": (filename, b"fake video", mime)},
        data={"category": "data"},
    )
    assert bad.status_code == 422


def test_metric_artifact_provenance_diff_and_reverse_trace(client):
    login(client)
    pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    a1 = artifact(client, pid)
    a2 = artifact(client, pid, "data2.csv")
    for rid, refs in ((parent, [a1["id"]]), (child, [a2["id"]])):
        response = client.post(
            f"/api/runs/{rid}/metrics",
            json={"name": "score", "value": 1, "artifact_ids": refs},
        )
        assert response.status_code == 200, response.text
    page = client.get(f"/api/runs/{child}/diff?kind=metrics").json()
    assert page["total"] == 1 and page["items"][0]["fields"]["artifact_ids"] == {
        "parent": [a1["id"]],
        "current": [a2["id"]],
    }
    page = client.get(f"/api/projects/{pid}/trace/artifacts/{a2['id']}").json()
    assert page["groups"]["metrics"]["total"] == 1
    foreign = artifact(client, project(client))
    assert (
        client.post(
            f"/api/runs/{child}/metrics",
            json={"name": "bad", "artifact_ids": [foreign["id"]]},
        ).status_code
        == 422
    )
    linked = make(
        client, pid, "evidence", title="Artifact evidence", linked_run_id=child
    )
    client.patch(f"/api/runs/{child}", json={"artifact_ids": [a2["id"]]})
    page = client.get(f"/api/projects/{pid}/trace/artifacts/{a2['id']}").json()
    assert page["groups"]["evidence"]["items"][0]["id"] == linked["id"]
    assert page["groups"]["runs"]["items"][0]["id"] == child


def test_intelligence_scope_pagination_and_duplicate_diff_are_explicit(client):
    login(client)
    pid = project(client)
    foreign_pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    source = make(client, foreign_pid, "sources", title="Other project")
    assert (
        client.get(f"/api/projects/{pid}/trace/sources/{source['id']}").status_code
        == 404
    )
    assert client.get(f"/api/projects/{pid}/lineage?limit=0").status_code == 422
    assert client.get(f"/api/projects/{pid}/metrics/query?offset=-1").status_code == 422
    assert client.get(f"/api/runs/{child}/diff?kind=bogus").status_code == 422
    client.post(f"/api/runs/{child}/parameters", json={"name": "same", "value": 1})
    client.post(f"/api/runs/{child}/parameters", json={"name": "same", "value": 2})
    assert client.get(f"/api/runs/{child}/diff").status_code == 409
    lineage = client.get(f"/api/projects/{pid}/lineage").json()
    assert next(node for node in lineage["nodes"] if node["id"] == child)[
        "parameter_change_summary"
    ]["ambiguous"]
    with client.app.state.session_factory() as db:
        owner = db.get(m.Project, pid).owner_id
        outsider = m.User(
            email="outsider@example.test", display_name="Other", password_hash="unused"
        )
        db.add(outsider)
        db.flush()
        db.get(m.Project, pid).owner_id = outsider.id
        db.commit()
    assert owner != outsider.id
    assert client.get(f"/api/projects/{pid}/lineage").status_code == 404
    assert client.get(f"/api/runs/{child}/diff").status_code == 404
    assert client.get(f"/api/projects/{pid}/trace/runs/{child}").status_code == 404


def test_project_metric_query_has_constant_statement_count(client):
    from sqlalchemy import event

    login(client)
    pid = project(client)
    rid = run(client, pid)
    with client.app.state.session_factory() as db:
        for i in range(80):
            db.add(m.Metric(run_id=rid, name=f"score{i}", value=i))
        db.commit()
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        client.get(f"/api/projects/{pid}/metrics/query?limit=1")
        small = len(statements)
        statements.clear()
        page = client.get(f"/api/projects/{pid}/metrics/query?limit=50").json()
        assert page["total"] == 80 and len(page["items"]) == 50
        assert len(statements) == small
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)


def test_trace_complete_parameter_metric_provenance_in_both_directions(client):
    login(client)
    pid = project(client)
    rid = run(client, pid)
    parameter_source = make(client, pid, "sources", title="Parameter calibration")
    metric_source = make(client, pid, "sources", title="Metric method")
    file = artifact(client, pid)
    parameter = client.post(
        f"/api/runs/{rid}/parameters",
        json={"name": "temperature", "value": 20, "source_id": parameter_source["id"]},
    ).json()
    metric = client.post(
        f"/api/runs/{rid}/metrics",
        json={
            "name": "score",
            "value": 1,
            "source_id": metric_source["id"],
            "artifact_ids": [file["id"]],
        },
    ).json()
    evidence = make(client, pid, "evidence", title="Run evidence", linked_run_id=rid)
    claim = make(
        client,
        pid,
        "claims",
        statement="Supported by run",
        evidence_ids=[evidence["id"]],
    )
    for kind, iid in (
        ("runs", rid),
        ("claims", claim["id"]),
        ("parameters", parameter["id"]),
        ("metrics", metric["id"]),
        ("sources", parameter_source["id"]),
        ("artifacts", file["id"]),
    ):
        response = client.get(f"/api/projects/{pid}/trace/{kind}/{iid}")
        assert response.status_code == 200, response.text
        groups = response.json()["groups"]
        assert rid in {item["id"] for item in groups["runs"]["items"]}
        assert claim["id"] in {item["id"] for item in groups["claims"]["items"]}
        assert evidence["id"] in {item["id"] for item in groups["evidence"]["items"]}
        assert {parameter_source["id"], metric_source["id"]} <= {
            item["id"] for item in groups["sources"]["items"]
        }
        assert file["id"] in {item["id"] for item in groups["artifacts"]["items"]}
    client.delete(f"/api/sources/{metric_source['id']}")
    hidden = client.get(f"/api/projects/{pid}/trace/runs/{rid}").json()["groups"]
    assert metric_source["id"] not in {
        item["id"] for item in hidden["sources"]["items"]
    }


def test_diff_json_values_compare_semantically_in_historical_records(client):
    login(client)
    pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    with client.app.state.session_factory() as db:
        db.add(
            m.Parameter(
                run_id=parent,
                name="object",
                value_type="object",
                value={"a": 1, "b": {"c": 2, "d": 3}},
            )
        )
        db.add(
            m.Parameter(
                run_id=child,
                name="object",
                value_type="object",
                value={"b": {"d": 3.0, "c": 2}, "a": 1.0},
            )
        )
        db.add(
            m.Parameter(
                run_id=parent,
                name="bool-vs-number",
                value_type="object",
                value={"value": True},
            )
        )
        changed = m.Parameter(
            run_id=child,
            name="bool-vs-number",
            value_type="object",
            value={"value": 1},
        )
        db.add(changed)
        db.commit()
    page = client.get(f"/api/runs/{child}/diff?limit=1").json()
    assert page["total"] == 1 and page["items"][0]["name"] == "bool-vs-number"
    assert page["items"][0]["fields"]["value"] == {
        "parent": {"value": True},
        "current": {"value": 1},
    }
    nodes = client.get(f"/api/projects/{pid}/lineage").json()["nodes"]
    summary = next(node for node in nodes if node["id"] == child)[
        "parameter_change_summary"
    ]
    assert summary == {"names": ["bool-vs-number"], "total": 1}
    response = client.patch(
        f"/api/parameters/{changed.id}", json={"value": {"value": True}}
    )
    assert response.status_code == 200, response.text
    page = client.get(f"/api/runs/{child}/diff?limit=1").json()
    assert page["total"] == 0 and page["items"] == [], [
        item["fields"] for item in page["items"]
    ]
    nodes = client.get(f"/api/projects/{pid}/lineage").json()["nodes"]
    assert next(node for node in nodes if node["id"] == child)[
        "parameter_change_summary"
    ] == {"names": [], "total": 0}


def test_metric_artifact_diff_is_correlated_to_matching_name(client):
    login(client)
    pid = project(client)
    parent = run(client, pid)
    child = run(client, pid, parent_run_id=parent)
    a1, a2 = artifact(client, pid), artifact(client, pid, "data2.csv")
    for rid, refs in ((parent, [a1, a2]), (child, [a2, a1])):
        for index, file in enumerate(refs):
            client.post(
                f"/api/runs/{rid}/metrics",
                json={
                    "name": f"score{index}",
                    "value": None,
                    "artifact_ids": [file["id"]],
                },
            )
    page = client.get(f"/api/runs/{child}/diff?kind=metrics").json()
    assert page["total"] == 2 and all(
        "artifact_ids" in item["fields"] for item in page["items"]
    )


def test_metric_query_prefers_explicit_schema_over_legacy_name_and_scopes(client):
    login(client)
    pid = project(client, "hdsp")
    rid = run(client, pid, run_type="acoustic_simulation")
    expected = []
    for name, schema in (
        ("coverage", "p_max"),
        ("Coverage caption", "coverage"),
        ("coverage", None),
    ):
        response = client.post(
            f"/api/runs/{rid}/metrics",
            json={"name": name, "metric_schema_id": schema, "value": 1},
        )
        assert response.status_code == 200, response.text
        if schema != "p_max":
            expected.append(response.json()["id"])
    foreign_pid = project(client, "hdsp")
    foreign_run = run(client, foreign_pid, run_type="acoustic_simulation")
    client.post(
        f"/api/runs/{foreign_run}/metrics",
        json={"name": "coverage", "metric_schema_id": "coverage", "value": 2},
    )
    foreign_source = make(client, foreign_pid, "sources", title="Foreign calibration")
    assert (
        client.post(
            f"/api/runs/{rid}/metrics",
            json={
                "name": "coverage",
                "metric_schema_id": "coverage",
                "source_id": foreign_source["id"],
            },
        ).status_code
        == 422
    )
    page = client.get(
        f"/api/projects/{pid}/metrics/query?metric_ids=coverage&limit=1"
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    full = client.get(f"/api/projects/{pid}/metrics/query?metric_ids=coverage").json()
    assert {item["id"] for item in full["items"]} == set(expected)
