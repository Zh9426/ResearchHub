from uuid import uuid4
from pathlib import Path
from fastapi.testclient import TestClient
from researchhub.sync.pc_qa import create_app

def test_api_host_origin_json_csrf_and_actor(engine):
    app=create_app(engine=engine,runtime=Path('storage/runtime/browser-sync-qa/pc/api-tests')/str(uuid4()))
    with TestClient(app,base_url='http://127.0.0.1:3315',client=('127.0.0.1',50000)) as c:
        assert c.get('/api/session',headers={'host':'evil.example'}).status_code==403
        assert c.get('/api/snapshot').status_code==401
        token=c.get('/api/session').json()['csrf']
        assert c.post('/api/command',json={}).status_code==403
        assert c.post('/api/command',json={},headers={'origin':'http://evil.example','x-pc-csrf':token}).status_code==403
        assert c.post('/api/command',content='{}',headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':token}).status_code==415
        assert c.options('/api/command',headers={'origin':'http://127.0.0.1:3314'}).status_code==403
        snap=c.get('/api/snapshot').json()
        assert snap['snapshot']['objects']==[]
        assert c.post('/api/command',json={'actor_type':'human'},headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':token}).status_code==409

def test_manual_endpoint_preserves_normal_boundary_and_requires_explicit_peer(engine):
    app=create_app(engine=engine,runtime=Path('storage/runtime/browser-sync-qa/pc/api-tests')/str(uuid4()))
    with TestClient(app,base_url='http://127.0.0.1:3315',client=('127.0.0.1',50000)) as c:
        token=c.get('/api/session').json()['csrf']
        assert c.post('/api/sync',json={}).status_code==403
        response=c.post('/api/sync',json={},headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':token})
        assert response.status_code==409
        assert response.json()['error']=='EXACT_PEER_TARGET_REQUIRED'

def test_sync_route_preserves_primary_and_close_failure(engine,monkeypatch):
    import httpx
    import pytest
    from researchhub.sync.secure.keys import Device,transition
    from researchhub.sync.secure.transport_pg import advance_history
    from researchhub.sync.pc_transport import PcTransport
    from researchhub.sync import pc_pairing
    app=create_app(engine=engine,runtime=Path('storage/runtime/browser-sync-qa/pc/api-tests')/str(uuid4()))
    node=app.state.node;peer=Device.generate();old=node.binding['trust']['manifest_chain'][-1]
    advance_history(engine,old['opaque_project_id'],transition(old,node.owner,add=peer.member('writer',1)))
    class BrokenClose:
        def close(self):raise RuntimeError('SYNTHETIC_CLOSE_FAILURE')
    monkeypatch.setattr(pc_pairing,'make_transport',lambda *args:BrokenClose())
    def fail(*args):raise httpx.ReadTimeout('SYNTHETIC_PRIMARY_NETWORK_FAILURE')
    monkeypatch.setattr(PcTransport,'cycle',fail)
    with TestClient(app,base_url='http://127.0.0.1:3315',client=('127.0.0.1',50000)) as c:
        token=c.get('/api/session').json()['csrf']
        with pytest.raises(ExceptionGroup) as result:
            c.post('/api/sync',json={},headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':token})
        def leaves(exc):
            return sum((leaves(e) for e in exc.exceptions),[]) if isinstance(exc,BaseExceptionGroup) else [exc]
        errors=leaves(result.value)
        assert any(isinstance(e,httpx.ReadTimeout) for e in errors)
        assert any(str(e)=='SYNTHETIC_CLOSE_FAILURE' for e in errors)
