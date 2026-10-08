"""QA runner evidence plugin: complete collection and execution, no payloads."""

import json
import os
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption("--rh-collection-report", action="store")


def pytest_configure(config):
    path = config.getoption("--rh-collection-report")
    if path:
        config.pluginmanager.register(
            CollectionEvidence(path), "researchhub-collection-evidence"
        )


class CollectionEvidence:
    def __init__(self, path):
        self.path = Path(path)
        self.selected = 0
        self.deselected = 0
        self.paths = set()
        self.executed = set()

    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_collection_finish(self, session):
        self.selected = len(session.items)
        self.paths = {str(Path(item.path).resolve()) for item in session.items}

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.executed.add(report.nodeid)

    def pytest_sessionfinish(self, session, exitstatus):
        self.path.write_text(
            json.dumps(
                {
                    "run": os.environ["HUB_QA_SERVICE_RUN"],
                    "trial": os.environ["HUB_QA_TRIAL"],
                    "cohort": os.environ["HUB_QA_COHORT"],
                    "invocation": os.environ["HUB_QA_INVOCATION"],
                    "selected": self.selected,
                    "executed": len(self.executed),
                    "deselected": self.deselected,
                    "exitstatus": int(exitstatus),
                    "collected_paths": sorted(self.paths),
                }
            ),
            encoding="utf-8",
        )
