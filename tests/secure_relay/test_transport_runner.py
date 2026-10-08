"""Runner orchestration unit tests, never substitute for actual two-cohort QA."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import qa_module


def write_collection(args, env, *, changed=None):
    evidence = {
        "run": "unit",
        "cohort": env.get("HUB_QA_COHORT"),
        "trial": env.get("HUB_QA_TRIAL"),
        "invocation": env.get("HUB_QA_INVOCATION"),
        "selected": 2,
        "executed": 2,
        "deselected": 0,
        "exitstatus": 0,
        "collected_paths": sorted(
            str(Path(arg).resolve())
            for arg in args
            if Path(arg).name.startswith("test_") and arg.endswith(".py")
        ),
    }
    evidence.update(changed or {})
    if "--rh-collection-report" in args:
        Path(args[args.index("--rh-collection-report") + 1]).write_text(
            json.dumps(evidence)
        )


def test_runner_has_fail_closed_sequential_cohorts():
    module = qa_module()
    assert callable(getattr(module, "run_test_cohorts", None)), (
        "quota-safe complete QA runner missing"
    )


@pytest.mark.parametrize(
    "codes,expected_calls", [([7, 0], 1), ([0, 9], 2), ([0, 0], 2)]
)
def test_runner_failure_propagation_and_distinct_evidence(
    monkeypatch, tmp_path, codes, expected_calls
):
    module = qa_module()
    assert callable(getattr(module, "run_test_cohorts", None)), (
        "quota-safe complete QA runner missing"
    )
    monkeypatch.setenv("HUB_RELAY_QA", "1")
    monkeypatch.setenv("HUB_SYNC_QA", "1")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "preflight_client", lambda: None)
    directory = tmp_path / "tests/secure_relay"
    directory.mkdir(parents=True)
    (directory / "test_old.py").touch()
    (directory / "test_transport.py").touch()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        write_collection(args, kwargs["env"])
        runtime = tmp_path / "storage/runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "secure-relay-privacy-result.json").write_text(
            json.dumps(
                {
                    "audit_version": 2,
                    "hits": 0,
                    "private_material_count": len(calls),
                    "run": "unit",
                    "cohort": kwargs["env"].get("HUB_QA_COHORT"),
                    "invocation": kwargs["env"].get("HUB_QA_INVOCATION"),
                    "trial": kwargs["env"].get("HUB_QA_TRIAL"),
                }
            )
        )
        Path(args[args.index("--junitxml") + 1]).write_text(
            '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0" /></testsuites>'
        )
        return SimpleNamespace(returncode=codes[len(calls) - 1])

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.run_test_cohorts({"run": "unit"})
    assert result == next((n for n in codes if n), 0)
    assert len(calls) == expected_calls
    assert len({c[c.index("--basetemp") + 1] for c in calls}) == expected_calls
    if result == 0:
        index = json.loads(
            (
                next(
                    (tmp_path / "storage/runtime").glob(
                        "secure-relay-suite-result-*.json"
                    )
                )
            ).read_text()
        )
        assert [
            row["privacy"]["private_material_count"] for row in index["cohorts"]
        ] == [1, 2]
        assert all(row["tests"] == 2 for row in index["cohorts"])


@pytest.mark.parametrize("field", ["run", "cohort", "invocation", "trial", "missing"])
def test_runner_rejects_stale_privacy_before_next_cohort(monkeypatch, tmp_path, field):
    module = qa_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "preflight_client", lambda: None)
    directory = tmp_path / "tests/secure_relay"
    directory.mkdir(parents=True)
    (directory / "test_old.py").touch()
    (directory / "test_transport.py").touch()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        write_collection(args, kwargs["env"])
        evidence = {
            "audit_version": 2,
            "hits": 0,
            "run": "unit",
            "cohort": kwargs["env"].get("HUB_QA_COHORT"),
            "invocation": kwargs["env"].get("HUB_QA_INVOCATION"),
            "trial": kwargs["env"].get("HUB_QA_TRIAL"),
        }
        evidence[field] = "stale"
        if field != "missing":
            (tmp_path / "storage/runtime/secure-relay-privacy-result.json").write_text(
                json.dumps(evidence)
            )
        Path(args[args.index("--junitxml") + 1]).write_text(
            '<testsuites><testsuite tests="2" /></testsuites>'
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="QA_PRIVACY_EVIDENCE_REQUIRED"):
        module.run_test_cohorts({"run": "unit"})
    assert len(calls) == 1


@pytest.mark.parametrize("missing", ["HUB_RELAY_QA", "HUB_SYNC_QA"])
def test_runner_preflight_missing_optin_never_starts_cohort(monkeypatch, missing):
    module = qa_module()
    monkeypatch.setenv("HUB_RELAY_QA", "1")
    monkeypatch.setenv("HUB_SYNC_QA", "1")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match="QA_BOTH_RELAY_AND_SYNC_OPTINS_REQUIRED"):
        module.run_test_cohorts({"run": "unit"})


@pytest.mark.parametrize("selection", ["-k selected", "-m selected"])
@pytest.mark.parametrize("required_fails", [True, False])
def test_real_pytest_selection_cannot_hide_required_failure(
    monkeypatch, tmp_path, selection, required_fails
):
    """Real pytest processes against isolated unit files, NOT a Relay service substitute."""
    module = qa_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "preflight_client", lambda: None)
    monkeypatch.setenv("PYTEST_ADDOPTS", selection)
    directory = tmp_path / "tests/secure_relay"
    directory.mkdir(parents=True)
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = -k selected\nmarkers = selected: unit selection probe\n"
    )
    for name in ("test_old.py", "test_transport.py"):
        (directory / name).write_text(
            "import pytest\n@pytest.mark.selected\ndef test_selected():\n    assert True\n"
            f'def test_required():\n    assert {not required_fails}, "REQUIRED_UNIT_PROBE"\n'
        )
    (directory / "conftest.py").write_text("""import json, os
from pathlib import Path
import pytest
@pytest.fixture(scope="session", autouse=True)
def evidence():
    yield
    data = {"audit_version": 2, "hits": 0, "run": "unit",
        "cohort": os.environ["HUB_QA_COHORT"], "trial": os.environ["HUB_QA_TRIAL"],
        "invocation": os.environ["HUB_QA_INVOCATION"]}
    (Path(__file__).resolve().parents[2] / "storage/runtime/secure-relay-privacy-result.json").write_text(json.dumps(data))
""")
    assert module.run_test_cohorts({"run": "unit"}) == (1 if required_fails else 0)
    import xml.etree.ElementTree as ET

    runtime = tmp_path / "storage/runtime"
    reports = list(runtime.glob("secure-relay-tests-*.xml"))
    assert len(reports) == (1 if required_fails else 2)
    for report in reports:
        suite = ET.parse(report).getroot().find("testsuite")
        assert int(suite.get("tests")) == 2
        assert int(suite.get("failures")) == int(required_fails)
    for report in runtime.glob("secure-relay-collection-*.json"):
        collection = json.loads(report.read_text())
        assert collection["selected"] == collection["executed"] == 2
        assert collection["deselected"] == 0
    # Child sanitization must not mutate the user's process/global environment.
    import os

    assert os.environ["PYTEST_ADDOPTS"] == selection


@pytest.mark.parametrize(
    "changed",
    [
        {"deselected": 1},
        {"selected": 0},
        {"executed": 1},
        {"selected": 3},
        {"collected_paths": []},
    ],
)
def test_runner_rejects_incomplete_collection(monkeypatch, tmp_path, changed):
    module = qa_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "preflight_client", lambda: None)
    directory = tmp_path / "tests/secure_relay"
    directory.mkdir(parents=True)
    (directory / "test_old.py").touch()
    (directory / "test_transport.py").touch()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        write_collection(args, kwargs["env"], changed=changed)
        evidence = {
            "audit_version": 2,
            "hits": 0,
            "run": "unit",
            "cohort": kwargs["env"].get("HUB_QA_COHORT"),
            "invocation": kwargs["env"].get("HUB_QA_INVOCATION"),
            "trial": kwargs["env"].get("HUB_QA_TRIAL"),
        }
        (tmp_path / "storage/runtime/secure-relay-privacy-result.json").write_text(
            json.dumps(evidence)
        )
        Path(args[args.index("--junitxml") + 1]).write_text(
            '<testsuites><testsuite tests="2" /></testsuites>'
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="QA_COMPLETE_COHORT_REQUIRED"):
        module.run_test_cohorts({"run": "unit"})
    assert len(calls) == 1
