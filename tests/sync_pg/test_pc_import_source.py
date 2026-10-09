"""Explicit 3A project identity, never inferred from a name or default module."""
import hashlib
import json
import time
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


@pytest.mark.parametrize('module', ['hdsp', 'ice-sonocuring'])
@pytest.mark.parametrize('fault_point', [None, 'after_consume', 'before_pg_commit'])
def test_source_pairing_response_keeps_original_stringify_order_after_restart(engine, module, fault_point):
    """Real QA PG journal and signed responses; Relay is explicit fault fixture only."""
    from test_pc_pairing import FaultRelay
    from researchhub.sync.pc_pairing import OwnerPairing
    from researchhub.sync.secure.keys import Device
    from researchhub.sync.secure import pairing
    from packages.secure_wire.membership import verify_signed
    from packages.secure_wire.canonical import canonical_bytes
    from fastapi.responses import JSONResponse

    source = descriptor(module)
    runtime = Path('storage/runtime/browser-sync-qa/pc/import-pairing-tests') / str(uuid4())
    node = pc_identity.setup_node(engine, runtime, module, source_project=source)
    relay = FaultRelay(node.binding['trust']['manifest_chain'][-1])
    owner = OwnerPairing(engine, node, relay)
    device = Device.generate()
    now = int(time.time())
    started = owner.start(device.member('writer', 1), now=now)
    proof = pairing.answer_challenge(started['challenge'], relay.manifest, device,
                                    confirmation=started['confirmation'], now=now)
    def fault(stage):
        if stage == fault_point:
            raise RuntimeError('INJECTED_SOURCE_PAIRING_BOUNDARY')
    if fault_point is None:
        first = owner.confirm(started['session_id'], proof, now=now)
    else:
        with pytest.raises(RuntimeError, match='INJECTED_SOURCE_PAIRING_BOUNDARY'):
            owner.confirm(started['session_id'], proof, now=now, fault=fault)
    restarted = pc_identity.setup_node(engine, runtime, module, source_project=source, pairing_transport=relay)
    resumed = OwnerPairing(engine, restarted, relay)
    if fault_point is not None:
        first = resumed.resume(started['session_id'], now=now + 400)
    responses = [first, owner.status(started['session_id']),
                 resumed.resume(started['session_id'], now=now + 400),
                 resumed.confirm(started['session_id'], proof, now=now + 400)]
    if fault_point is None:
        from fastapi.testclient import TestClient
        from researchhub.sync.pc_qa import create_app
        app = create_app(engine=engine, runtime=runtime, module_id=module,
                         source_project=source, pairing_transport=relay)
        with TestClient(app, base_url='http://127.0.0.1:3315', client=('127.0.0.1', 50000)) as client:
            client.get('/api/session')
            wire = client.get('/api/pairing/status', params={'session_id': started['session_id']})
            assert wire.status_code == 200
            assert wire.content == JSONResponse(first).body
            responses.append(wire.json())
    for response in responses:
        # Same JSONResponse encoding as the actual endpoint; do not canonicalize it here.
        decoded = json.loads(JSONResponse(response).body)
        wrapper = decoded['signed_binding']
        binding = wrapper['binding']
        verify_signed('PcProjectBinding', wrapper, node.owner.signing_public)
        serialized = json.dumps(binding['module_snapshot'], ensure_ascii=False, separators=(',', ':'))
        assert hashlib.sha256(serialized.encode()).hexdigest() == source['project']['module_hash']
        assert binding['local_module_hash']['value'] == source['project']['module_hash']
        assert canonical_bytes(response) == canonical_bytes(first)
        assert JSONResponse(response).body == JSONResponse(first).body
    assert relay.posts == 1
    # Presentation must not rewrite journal content or re-sign historical bytes.
    from sqlalchemy.orm import Session
    from researchhub.sync.pc_pairing import PairingJournal
    from types import SimpleNamespace
    from copy import deepcopy
    with Session(engine) as db:
        stored = deepcopy(db.get(PairingJournal, started['session_id']).result)
    assert canonical_bytes(first) == canonical_bytes(stored)
    assert first['signed_binding']['signature'] == stored['signed_binding']['signature']
    for mutation in ('content', 'canonical_hash', 'local_hash'):
        bad = deepcopy(stored)
        target = bad['signed_binding']['binding']
        if mutation == 'content':
            target['module_snapshot']['description'] = 'SYNTHETIC changed journal'
        elif mutation == 'canonical_hash':
            target['module_snapshot_hash'] = '0' * 64
        else:
            target['local_module_hash']['value'] = '0' * 64
        with pytest.raises(ValueError, match='BLOCKED_FROZEN_SNAPSHOT_MISMATCH'):
            resumed._view(SimpleNamespace(stage='COMPLETE', result=bad))
    frozen = deepcopy(restarted.binding['module_snapshot'])
    restarted.binding['module_snapshot']['description'] = 'SYNTHETIC changed frozen source'
    with pytest.raises(ValueError, match='BLOCKED_FROZEN_SNAPSHOT_MISMATCH'):
        resumed._view(SimpleNamespace(stage='COMPLETE', result=stored))
    restarted.binding['module_snapshot'] = frozen
    restarted.binding['module_snapshot'] = dict(reversed(list(frozen.items())))
    with pytest.raises(ValueError, match='BLOCKED_FROZEN_SNAPSHOT_MISMATCH'):
        resumed._view(SimpleNamespace(stage='COMPLETE', result=stored))
    restarted.binding['module_snapshot'] = frozen


def test_default_pairing_response_keeps_previous_canonical_presentation(engine):
    from test_pc_pairing import world
    from researchhub.sync.secure import pairing
    from packages.secure_wire.canonical import canonical_bytes, strict_loads
    from fastapi.responses import JSONResponse
    pc, node, relay, owner, device = world(engine)
    now = int(time.time())
    start = owner.start(device.member('writer', 1), now=now)
    proof = pairing.answer_challenge(start['challenge'], relay.manifest, device,
                                    confirmation=start['confirmation'], now=now)
    response = owner.confirm(start['session_id'], proof, now=now)
    assert JSONResponse(response).body == JSONResponse(strict_loads(canonical_bytes(response))).body
