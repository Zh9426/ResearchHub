"""Explicit separate real-network collection. No skip or Relay fixture teardown."""
import os
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]


@pytest.fixture(scope='session')
def engine():
    assert os.environ.get('HUB_SYNC_QA')=='1'
    assert os.environ.get('HUB_RELAY_QA')=='1'
    from researchhub.sync.secure.transport_pg import client_engine
    result=client_engine()
    try:yield result
    finally:result.dispose()
