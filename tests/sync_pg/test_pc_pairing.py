"""FAULT_INJECTED_ONLY boundaries with real QA PG and SQLite; network separate."""
from pathlib import Path
from uuid import uuid4
import importlib
import time
import pytest
from sqlalchemy.orm import Session
from packages.secure_wire.canonical import digest
from researchhub.sync.pc_identity import setup_node
from researchhub.sync.secure.keys import Device, TrustedStore, open_grant
from researchhub.sync.secure import pairing


class FaultRelay:
    """Explicit fault injection, never counted as TLS/network acceptance."""
    def __init__(self, manifest):self.manifest=manifest;self.posts=0;self.unknown=False
    def request(self,method,path,body=None,query=None):
        if path=='/v1/hello':return {'manifest_digest':digest(self.manifest),'sequence':0}
        if path=='/v1/membership':return self.manifest
        raise AssertionError(path)
    def pairing_request(self,session_id,operation,*,db):
        pc=importlib.import_module('researchhub.sync.pc_pairing')
        row=db.get(pc.PairingJournal,session_id)
        candidate=row.receipt['manifest']
        if operation=='receipt':
            if digest(self.manifest)!=digest(candidate):raise pc.RelayOldHead()
        elif operation=='current':return self.manifest
        elif operation=='publish':
            self.posts+=1;self.manifest=candidate
            if self.unknown:self.unknown=False;raise OSError('INJECTED_ACK_UNKNOWN')
        return {'manifest_digest':digest(candidate),'membership_epoch':candidate['membership_epoch'],'key_epoch':candidate['key_epoch']}


def world(engine):
    pc=importlib.import_module('researchhub.sync.pc_pairing')
    node=setup_node(engine,Path('storage/runtime/browser-sync-qa/pc/b2a-tests')/str(uuid4()))
    relay=FaultRelay(node.binding['trust']['manifest_chain'][-1])
    owner=pc.OwnerPairing(engine,node,relay)
    return pc,node,relay,owner,Device.generate()


@pytest.mark.parametrize('point',['after_reserved','after_challenge_create','after_challenge','after_consume','before_pg_commit',None])
def test_durable_boundaries_exact_receipt_restart_principal(engine,point):
    pc,node,relay,owner,b=world(engine)
    now=int(time.time())
    def fault(stage):
        if stage==point:raise RuntimeError('INJECTED_BOUNDARY')
    if point in ('after_reserved','after_challenge_create','after_challenge'):
        with pytest.raises(RuntimeError):owner.start(b.member('writer',1),now=now,fault=fault)
        sid=owner.status()['session_id'];started=owner.resume(sid,now=now)
    else:started=owner.start(b.member('writer',1),now=now)
    sid=started['session_id'];challenge=started['challenge'];old=relay.manifest
    proof=pairing.answer_challenge(challenge,old,b,confirmation=pairing.confirmation(challenge),now=now)
    if point in ('after_consume','before_pg_commit'):
        with pytest.raises(RuntimeError):owner.confirm(sid,proof,now=now,fault=fault)
        # Recovery after expiry must use the exact SQLite receipt, never consume again.
        restarted=setup_node(engine,node.runtime,pairing_transport=relay)
        owner=pc.OwnerPairing(engine,restarted,relay)
        result=owner.resume(sid,now=now+400)
    else:result=owner.confirm(sid,proof,now=now)
    again=owner.confirm(sid,proof,now=now+400)
    assert again==result
    # JS JSON.stringify preserves returned insertion order. JSONB must not alter
    # the frozen module hash when a completed journal is fetched after restart.
    import json,hashlib
    wire_binding=again['signed_binding']['binding']
    encoded=json.dumps(wire_binding['module_snapshot'],ensure_ascii=False,separators=(',',':')).encode()
    assert hashlib.sha256(encoded).hexdigest()==wire_binding['local_module_hash']['value']
    assert bool(open_grant(result['pairing_receipt']['grant'],result['pairing_receipt']['manifest'],b)==node.project_key)
    binding=result['signed_binding']['binding']
    assert binding['principal']['device_id']==b.device_id
    assert len(binding['principal_map'])==2
    assert relay.posts==1
    restarted=setup_node(engine,node.runtime)
    assert restarted.binding['principal_map']==binding['principal_map']
    assert restarted.binding['trust']==binding['trust']
    with TrustedStore(node.runtime/'trust.sqlite').transaction() as db:
        assert db.execute('SELECT attempts,used FROM challenges WHERE session=?',(sid,)).fetchone()==(1,1)


def test_failure_before_reservation_commit_leaves_no_challenge(engine):
    _,node,relay,owner,b=world(engine)
    def fault(stage):
        if stage=='before_reserved_commit':raise RuntimeError('INJECTED_BEFORE_RESERVATION')
    with pytest.raises(RuntimeError):owner.start(b.member('writer',1),fault=fault)
    assert owner.status()=={'stage':'IDLE'}
    with owner.store.transaction() as db:
        assert db.execute('SELECT count(*) FROM challenges').fetchone()[0]==0


def test_unknown_ack_recovers_receipt_without_second_publish(engine):
    _,node,relay,owner,b=world(engine);now=int(time.time())
    started=owner.start(b.member('writer',1),now=now);challenge=started['challenge']
    proof=pairing.answer_challenge(challenge,relay.manifest,b,confirmation=pairing.confirmation(challenge),now=now)
    relay.unknown=True
    result=owner.confirm(started['session_id'],proof,now=now)
    assert result['stage']=='RELAY_UNKNOWN'
    assert owner.resume(started['session_id'],now=now+400)['stage']=='COMPLETE'
    assert relay.posts==1


def test_active_journal_and_invalid_recipient_reject(engine):
    _,node,relay,owner,b=world(engine);now=int(time.time())
    with pytest.raises(ValueError):owner.start(b.member('owner',1),now=now)
    with pytest.raises(ValueError):owner.start({**b.member('writer',1),'fingerprint':'a'*64},now=now)
    start=owner.start(b.member('writer',1),now=now)
    with pytest.raises(ValueError,match='ACTIVE_PAIRING'):owner.start(Device.generate().member('writer',2),now=now)
    with pytest.raises(ValueError):owner.resume(str(uuid4()),now=now)
    assert owner.resume(start['session_id'],now=now+301)['stage']=='EXPIRED'


def test_active_pairing_blocks_baseline_command(engine):
    from researchhub.sync.pc_records import execute_command
    from researchhub.sync.protocol import ProtocolError
    _,node,relay,owner,b=world(engine)
    owner.start(b.member('writer',1))
    command=dict(command_id=str(uuid4()),transaction_id=str(uuid4()),object_id=str(uuid4()),
        object_type='Note',operation='create',expected_work_version=0,expected_heads=[],patch={'title':'SYNTHETIC'})
    with Session(engine) as db,db.begin(),pytest.raises(ProtocolError,match='PAIRING_IN_PROGRESS'):
        execute_command(db,node.context,node.binding['semantic_project_id'],command)


def test_signed_binding_endpoint_rebuilds_after_pairing(engine):
    from fastapi.testclient import TestClient
    from researchhub.sync.pc_qa import create_app
    pc,node,relay,owner,b=world(engine)
    app=create_app(engine=engine,runtime=node.runtime,pairing_transport=relay)
    with TestClient(app,base_url='http://127.0.0.1:3315',client=('127.0.0.1',50000)) as client:
        csrf=client.get('/api/session').json()['csrf']
        headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':csrf,'content-type':'application/json'}
        from packages.secure_wire.canonical import canonical_bytes
        start=client.post('/api/pairing/start',content=canonical_bytes({'recipient':b.member('writer',1)}),headers=headers).json()
        proof=pairing.answer_challenge(start['challenge'],relay.manifest,b,confirmation=start['confirmation'],now=int(time.time()))
        response=client.post('/api/pairing/confirm',content=canonical_bytes({'session_id':start['session_id'],'proof':proof}),headers=headers)
        assert response.status_code==200
        assert len(client.get('/api/binding').json()['binding']['principal_map'])==2
        bad=client.post('/api/pairing/resume',content='{"session_id": "noncanonical"}',headers=headers)
        assert bad.status_code==422


def test_nonempty_kernel_or_relay_cannot_skip_history(engine):
    from researchhub.sync.pc_records import execute_command
    _,node,relay,owner,b=world(engine)
    with Session(engine) as db,db.begin():
        execute_command(db,node.context,node.binding['semantic_project_id'],dict(
            command_id=str(uuid4()),transaction_id=str(uuid4()),object_id=str(uuid4()),object_type='Note',
            operation='create',expected_work_version=0,expected_heads=[],patch={'title':'SYNTHETIC baseline'}))
    with pytest.raises(ValueError,match='EMPTY_PROJECT_REQUIRED'):owner.start(b.member('writer',1))
    _,node,relay,owner,b=world(engine)
    relay.request=lambda *args,**kwargs:{'sequence':1,'manifest_digest':digest(relay.manifest)}
    with pytest.raises(ValueError,match='EMPTY_RELAY_REQUIRED'):owner.start(b.member('writer',1))


def test_parallel_confirm_and_head_map_immutable(engine):
    from concurrent.futures import ThreadPoolExecutor
    from researchhub.sync.pc_identity import current_binding
    from researchhub.sync.models import Principal
    from researchhub.sync.secure.transport_pg import Trust
    from packages.secure_wire.canonical import strict_loads
    _,node,relay,owner,b=world(engine);now=int(time.time())
    start=owner.start(b.member('writer',1),now=now)
    proof=pairing.answer_challenge(start['challenge'],relay.manifest,b,confirmation=start['confirmation'],now=now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(owner.confirm,start['session_id'],proof,now=now) for _ in range(2)]
        first,second=[f.result() for f in futures]
    assert first==second
    assert relay.posts==1
    with Session(engine) as db,db.begin():
        trust=db.get(Trust,node.binding['opaque_project_id'])
        principal=db.get(Principal,strict_loads(trust.principals)[b.device_id]);principal.actor_id=str(uuid4())
    with pytest.raises(ValueError,match='PRINCIPAL_MAP_CHANGED'):current_binding(engine,node)


def test_third_relay_head_blocks_without_publish(engine):
    from researchhub.sync.secure.keys import transition
    _,node,relay,owner,b=world(engine);now=int(time.time())
    start=owner.start(b.member('writer',1),now=now)
    proof=pairing.answer_challenge(start['challenge'],relay.manifest,b,confirmation=start['confirmation'],now=now)
    relay.manifest=transition(relay.manifest,node.owner,add=Device.generate().member('reader',17))
    assert owner.confirm(start['session_id'],proof,now=now)['stage']=='BLOCKED'
    assert relay.posts==0


def test_completed_receipt_cannot_authorize_revoked_recipient(engine):
    from researchhub.sync.secure.keys import transition
    from researchhub.sync.secure.transport_pg import advance_history
    _,node,relay,owner,b=world(engine);now=int(time.time())
    start=owner.start(b.member('writer',1),now=now)
    proof=pairing.answer_challenge(start['challenge'],relay.manifest,b,confirmation=start['confirmation'],now=now)
    result=owner.confirm(start['session_id'],proof,now=now)
    revoked=transition(result['pairing_receipt']['manifest'],node.owner,revoke=b.device_id,now=now+1)
    owner.store.accept(revoked);advance_history(engine,owner.project,revoked)
    with pytest.raises(ValueError):owner.resume(start['session_id'],now=now+400)
    with pytest.raises(ValueError):owner.status(start['session_id'])


@pytest.mark.parametrize('failure',['server_503','stream_deadline'])
def test_server_failure_after_publish_remains_unknown(engine,failure):
    import httpx
    _,node,relay,owner,b=world(engine);now=int(time.time())
    start=owner.start(b.member('writer',1),now=now)
    proof=pairing.answer_challenge(start['challenge'],relay.manifest,b,confirmation=start['confirmation'],now=now)
    original=relay.pairing_request
    def server_fault(session,operation,*,db):
        result=original(session,operation,db=db)
        if operation=='publish':
            if failure=='stream_deadline':raise ValueError('RESPONSE_TIMEOUT')
            request=httpx.Request('POST','https://127.0.0.1:38001/v1/membership')
            response=httpx.Response(503,request=request)
            raise httpx.HTTPStatusError('INJECTED_503_AFTER_COMMIT',request=request,response=response)
        return result
    relay.pairing_request=server_fault
    assert owner.confirm(start['session_id'],proof,now=now)['stage']=='RELAY_UNKNOWN'
    relay.pairing_request=original
    assert owner.resume(start['session_id'],now=now+400)['stage']=='COMPLETE'
    assert relay.posts==1


def test_pairing_api_slow_relay_does_not_block_session(engine,monkeypatch):
    """FAULT_INJECTED_ONLY: one ASGI loop, bounded independent Relay release."""
    import asyncio
    import threading
    import httpx
    from packages.secure_wire.canonical import canonical_bytes
    from researchhub.sync.pc_qa import create_app
    pc,node,relay,owner,b=world(engine)
    app=create_app(engine=engine,runtime=node.runtime)
    entered=threading.Event();release=threading.Event();session_done=threading.Event()
    times={};threads={};ordering={}
    original=relay.request
    def request(*args,**kwargs):
        threads['action']=threading.get_ident();times['entered']=time.perf_counter();entered.set()
        assert release.wait(5), 'Independent Relay release did not run'
        return original(*args,**kwargs)
    def construct(*args):
        threads['construct']=threading.get_ident()
        return relay
    def close():threads['close']=threading.get_ident()
    relay.request=request;relay.close=close
    monkeypatch.setattr(pc,'make_transport',construct)
    def bounded_release():
        if entered.wait(5):session_done.wait(2)
        times['released']=time.perf_counter();release.set()
    watchdog=threading.Thread(target=bounded_release,daemon=True)
    async def scenario():
        threads['loop']=threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',50000)),
                                     base_url='http://127.0.0.1:3315') as client:
            csrf=(await client.get('/api/session')).json()['csrf']
            headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':csrf,'content-type':'application/json'}
            pending=asyncio.create_task(client.post('/api/pairing/start',
                content=canonical_bytes({'recipient':b.member('writer',1)}),headers=headers))
            assert await asyncio.to_thread(entered.wait,5)
            response=await client.get('/api/session')
            times['session_returned']=time.perf_counter()
            ordering['session_before_release']=not release.is_set();session_done.set()
            assert response.status_code==200
            assert (await pending).status_code==200
    watchdog.start()
    try:asyncio.run(scenario())
    finally:release.set();watchdog.join(timeout=6)
    print('FAULT_INJECTED_ONLY timing', {key:round(value-times['entered'],3) for key,value in times.items()})
    assert ordering['session_before_release'], 'Session waited for blocked Relay'
    assert all(threads[key]!=threads['loop'] for key in ('construct','action','close'))


@pytest.mark.parametrize('failure,expected,error',[
    (FileNotFoundError('INJECTED_MISSING_RELAY_STATE'),503,'RELAY_UNAVAILABLE_RESUME_REQUIRED'),
    (FileNotFoundError('INJECTED_MISSING_CA'),503,'RELAY_UNAVAILABLE_RESUME_REQUIRED'),
    (ValueError('RELAY_QA_SETUP_REQUIRED'),503,'RELAY_UNAVAILABLE_RESUME_REQUIRED'),
    (ValueError('QA_CA_PATH_REQUIRED'),409,'PAIRING_REJECTED_CHECK_STATUS'),
    (RuntimeError('INJECTED_PROGRAMMING_ERROR'),500,None),
])
def test_pairing_api_transport_setup_failure_is_actionable(engine,monkeypatch,failure,expected,error):
    """FAULT_INJECTED_ONLY construction failure, never a TLS acceptance test."""
    from fastapi.testclient import TestClient
    from packages.secure_wire.canonical import canonical_bytes
    from researchhub.sync.pc_qa import create_app
    pc,node,relay,owner,b=world(engine)
    app=create_app(engine=engine,runtime=node.runtime)
    def unavailable(*args):raise failure
    monkeypatch.setattr(pc,'make_transport',unavailable)
    with TestClient(app,base_url='http://127.0.0.1:3315',client=('127.0.0.1',50000),
                    raise_server_exceptions=False) as client:
        csrf=client.get('/api/session').json()['csrf']
        result=client.post('/api/pairing/start',content=canonical_bytes({'recipient':b.member('writer',1)}),
            headers={'origin':'http://127.0.0.1:3315','x-pc-csrf':csrf,'content-type':'application/json'})
        assert result.status_code==expected
        if error:assert result.json()=={'error':error}
    assert owner.status()=={'stage':'IDLE'}
