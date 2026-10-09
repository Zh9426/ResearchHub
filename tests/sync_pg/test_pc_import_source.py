"""Explicit 3A project identity, never inferred from a name or default module."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from researchhub.sync import pc_identity


def descriptor(module):
    snapshot = json.loads((Path('packages/project-modules') / module / 'manifest.json').read_text(encoding='utf-8'))
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))
    project = dict(id=str(uuid4()), route_alias='ice' if module == 'ice-sonocuring' else module,
                   title='合成来源', scope='SYNTHETIC', module_id=module, module_version=snapshot['version'],
                   module_snapshot=snapshot, module_hash=hashlib.sha256(serialized.encode()).hexdigest(), local_format_version=1)
    return dict(format='RESEARCHHUB_3A_SOURCE_PROJECT_V1', project=project)


@pytest.mark.parametrize('module', ['hdsp', 'ice-sonocuring'])
def test_source_descriptor_preserves_snapshot_order(module):
    source = descriptor(module)
    validator = getattr(pc_identity, 'validate_source_project', None)
    assert validator is not None, 'explicit source-project validation is missing'
    assert validator(source) == source['project']
    source['project']['module_snapshot']['unrecognized'] = 'must reject'
    with pytest.raises(ValueError, match='SOURCE_PROJECT'):
        validator(source)


@pytest.mark.parametrize('module', ['hdsp', 'ice-sonocuring'])
def test_fresh_source_semantic_id_and_occupied_refusal(engine, module):
    source = descriptor(module)
    root = Path('storage/runtime/browser-sync-qa/pc/import-tests') / str(uuid4())
    first = pc_identity.setup_node(engine, root / 'one', module, source_project=source)
    assert first.binding['semantic_project_id'] == source['project']['id']
    assert first.binding['module_snapshot'] == source['project']['module_snapshot']
    assert first.binding['local_module_hash']['value'] == source['project']['module_hash']
    assert pc_identity.setup_node(engine, root / 'one', module, source_project=source).binding == first.binding
    with pytest.raises(ValueError, match='SOURCE_PROJECT_OCCUPIED'):
        pc_identity.setup_node(engine, root / 'two', module, source_project=source)
