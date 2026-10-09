"""Fixed v2 oracle vectors, independently consumed by Python and TypeScript."""
import json
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api'))
from researchhub.sync.protocol import validate_transaction, validate_change, revision, transaction_digest
CASES = json.loads((ROOT / 'fixtures/sync/v2/protocol.json').read_text(encoding='utf-8'))
@pytest.mark.parametrize('case', CASES, ids=lambda c: c['name'])
def test_v2_fixed(case):
    tx = json.loads(case['raw'])
    if not case['valid']:
        with pytest.raises(ValueError): validate_transaction(tx, case.get('context'))
    else:
        validate_transaction(tx)
        assert transaction_digest(tx) == case['digest']
        assert [revision(c) for c in tx['changes']] == case['revisions']
        validate_change(tx['changes'][0])

def test_materialize_version():
    from researchhub.sync.kernel import _materialize
    tx = json.loads(CASES[0]['raw'])
    assert _materialize(tx['changes'][0], [])[0] == tx['changes'][0]['payload']


def test_v1_only_capability_explicitly_refuses_v2():
    from researchhub.sync.protocol import require_version_pair, ProtocolError
    with pytest.raises(ProtocolError) as caught:
        require_version_pair(2, 2, supported=((1, 1),))
    assert caught.value.code == 'UPGRADE_REQUIRED'


def test_v2_does_not_bypass_protected_run_authority():
    from types import SimpleNamespace
    from researchhub.sync.authority import protected, assert_domain_ai_scope
    tx = json.loads(CASES[0]['raw'])
    change = tx['changes'][0]
    change['payload']['human_conclusion'] = 'final synthetic conclusion'
    validate_transaction(tx)
    assert protected('ResearchRun', change['payload'])
    with pytest.raises(ValueError):
        assert_domain_ai_scope(SimpleNamespace(actor_type='codex'), change, [])


def test_materialize_does_not_downgrade_inherited_v2_fields():
    from types import SimpleNamespace
    from researchhub.sync.kernel import _materialize
    tx = json.loads(CASES[0]['raw'])
    change = tx['changes'][0]
    parent = SimpleNamespace(document=change['payload'], lifecycle='active')
    change['schema_version'] = 1
    change['payload'] = {'title': 'v1 patch'}
    with pytest.raises(ValueError): _materialize(change, [parent])
