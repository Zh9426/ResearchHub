"""The expected statuses are authored independently of both implementations."""
import json
from pathlib import Path
from record_kernel_oracle import run, run_common_base

def test_record_kernel_vectors(engine):
    fixture=json.loads((Path(__file__).resolve().parents[2]/'fixtures/sync/v2/record_kernel_cases.json').read_text(encoding='utf-8'))
    result=run(fixture)
    for case,actual in zip(fixture['cases'],result):
        assert len(case['steps'])==len(actual['steps'])
        for wanted,got in zip(case['steps'],actual['steps']):
            assert got['result']==wanted['expected'],case['name']
    late=next(c for c in result if c['name']=='late-batch-recursive')['steps'][-1]
    assert len(late['snapshot']['projections'])==1
    assert list(late['snapshot']['projections'])[0].endswith('00000000000e')
    assert late['receipt']['state']=='CANDIDATE'
    assert late['receipt']['receipt_state']=='ACCEPTED'
    assert run_common_base(fixture)==[p['expected'] for p in fixture['common_base']]
