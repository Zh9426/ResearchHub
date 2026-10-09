import json
from pathlib import Path
from record_kernel_oracle import run

def test_received_historical_proposal_preserves_third_branch(engine):
    f=json.loads((Path(__file__).resolve().parents[2]/'fixtures/sync/v2/conflict_proposal_cases.json').read_text(encoding='utf-8'))
    results=run(f)
    for case,actual in zip(f['cases'],results):
        assert [s['result'] for s in actual['steps']]==[s['expected'] for s in case['steps']]
        if case['name'].startswith('third-'):
            state=actual['steps'][-1]['snapshot']
            assert sorted(state['revisions'][h]['document']['content'] for h in next(iter(state['heads'].values())))==['reviewed','third']
    assert results[0]['steps'][-1]['snapshot']['heads']==results[1]['steps'][-1]['snapshot']['heads']
