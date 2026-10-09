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
