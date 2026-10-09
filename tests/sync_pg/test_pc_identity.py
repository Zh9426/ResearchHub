"""Persistent QA identity safety; project keys are recovered from signed grants."""
from pathlib import Path
from uuid import uuid4
import pytest
from researchhub.sync.pc_identity import setup_node

def test_restart_and_missing_device_blocks(engine):
    runtime=Path('storage/runtime/browser-sync-qa/pc/identity-tests')/str(uuid4())
    first=setup_node(engine,runtime)
    second=setup_node(engine,runtime)
    assert first.binding==second.binding
    assert first.project_key==second.project_key
    assert first.binding['trust']['manifest_head']
    (runtime/'owner.sqlite').rename(runtime/'owner.removed.sqlite')
    with pytest.raises(ValueError,match='MISSING_DEVICE'):setup_node(engine,runtime)

def test_missing_nonce_blocks(engine):
    runtime=Path('storage/runtime/browser-sync-qa/pc/identity-tests')/str(uuid4())
    setup_node(engine,runtime)
    (runtime/'nonce.sqlite').rename(runtime/'nonce.removed.sqlite')
    with pytest.raises(ValueError,match='NONCE'):setup_node(engine,runtime)
