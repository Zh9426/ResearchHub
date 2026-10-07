"""QA opt-in and connection guard checks never contact any product database."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))
from researchhub.sync.qa import assert_qa_bind


def test_explicit_qa_opt_in_required(monkeypatch):
    monkeypatch.delenv("HUB_SYNC_QA", raising=False)
    engine = create_engine("postgresql+psycopg://researchhub_sync_qa@127.0.0.1/researchhub_sync_kernel_qa")
    with pytest.raises(RuntimeError, match="explicit"):
        assert_qa_bind(engine)


@pytest.mark.parametrize("url", ["sqlite://", "postgresql+psycopg://researchhub@127.0.0.1/researchhub",
                                 "postgresql+psycopg://researchhub_sync_qa@remote.invalid/researchhub_sync_kernel_qa"])
def test_product_or_remote_engine_rejected_without_connection(monkeypatch, url):
    monkeypatch.setenv("HUB_SYNC_QA", "1")
    engine = create_engine(url)
    with pytest.raises(RuntimeError, match="dedicated"):
        assert_qa_bind(engine)
