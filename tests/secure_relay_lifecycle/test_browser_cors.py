import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/relay'))
from fastapi.testclient import TestClient
from researchhub_relay.main import app

def test_preflight_is_database_free_and_narrow():
    client=TestClient(app)
    r=client.options('/v1/hello',headers={'Origin':'http://127.0.0.1:3314','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-rh-proof'})
    assert r.status_code==204
    assert r.headers['access-control-allow-origin']=='http://127.0.0.1:3314'
    assert 'access-control-allow-credentials' not in r.headers
    for origin in ['http://localhost:3314','http://127.0.0.1:3313']:
        r=client.options('/v1/hello',headers={'Origin':origin,'Access-Control-Request-Method':'POST'})
        assert r.status_code==403
        assert 'access-control-allow-origin' not in r.headers
    r=client.options('/v1/hello',headers={'Origin':'http://127.0.0.1:3314','Access-Control-Request-Method':'DELETE'})
    assert r.status_code==403

def test_disallowed_origin_rejected_before_business():
    r=TestClient(app).post('/v1/hello',headers={'Origin':'http://evil.invalid'})
    assert r.status_code==403
    assert 'access-control-allow-origin' not in r.headers

def test_allowed_error_has_cors_and_proof_still_required(monkeypatch):
    import researchhub_relay.main as main
    counts=[]
    app.state.engine=object()
    monkeypatch.setattr(main,'charge',lambda *args:counts.append(1))
    client=TestClient(app)
    r=client.post('/v1/hello',headers={'Origin':'http://127.0.0.1:3314','content-type':'application/json'},content='{}')
    assert r.status_code==401
    assert r.headers['access-control-allow-origin']=='http://127.0.0.1:3314'
    assert counts==[1]
    r=client.options('/v1/hello',headers={'Origin':'http://127.0.0.1:3314','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-rh-proof'})
    assert r.status_code==204 and counts==[1]
