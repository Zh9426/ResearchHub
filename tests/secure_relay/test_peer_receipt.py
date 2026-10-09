"""Real dedicated Relay PG service transactions; no HTTP/E2E claim."""
from uuid import uuid4
import hashlib
import time
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import delete
from conftest import qa_module,device
from researchhub.sync.secure import keys
from researchhub_relay import service
from researchhub_relay.models import Base,Project
from researchhub_relay.qa import connect
from packages.secure_wire.canonical import canonical_bytes,digest,strict_loads
from packages.secure_wire.peer_receipt import receipt_body
from packages.secure_wire.request import AUDIENCE,validate_query,POST_PATHS
import json
from pathlib import Path


def test_peer_receipt_request_allowlists():
    assert '/v1/peer-receipts' in POST_PATHS
    q=b'message_id=11111111-1111-4111-8111-111111111111&target_device_id=22222222-2222-4222-8222-222222222222'
    assert validate_query('/v1/peer-receipts',q)['message_id'].startswith('1111')


def test_real_pg_immutable_exact_retry_and_private_visibility():
    lifecycle=qa_module(); engine=connect(lifecycle.url(lifecycle.config()),profile='host')
    service.initialize(engine)
    owner,target,third=device(),device(),device();kit=keys.RecoveryKit.generate();pid=str(uuid4())
    old=keys.bootstrap(pid,owner,kit);current=keys.transition(old,owner,add=target.member('writer',1))
    current2=keys.transition(current,owner,add=third.member('writer',2))
    service.pin_bootstrap(engine,old,owner.signing_public,kit.signing_public)
    try:
        with Session(engine) as db,db.begin():
            p=db.get(Project,pid);service.membership_update(db,p,old,current,recovery=False);service.membership_update(db,p,current,current2,recovery=False)
        env=json.loads(Path('fixtures/sync/secure-v1/peer-receipt.TEST_ONLY.json').read_text(encoding='utf-8'))['envelope']
        env.update(opaque_project_id=pid,sender_device_id=owner.device_id,membership_epoch=current2['membership_epoch'])
        from researchhub.sync.secure.crypto import sign
        from packages.secure_wire.envelope import signature_preimage,b64encode
        env['signature']=b64encode(sign(owner.signing_seed,signature_preimage(env)))
        def call(who,method,path,body=None,query=None):
            raw=canonical_bytes(body) if body is not None else b'';query=query or {}
            proof=keys.signed_object('RelayRequest',dict(version=1,audience=AUDIENCE,method=method,path=path,query=query,opaque_project_id=pid,device_id=who.device_id,membership_epoch=current2['membership_epoch'],key_epoch=current2['key_epoch'],manifest_digest=digest(current2),body_digest=hashlib.sha256(raw).hexdigest(),request_id=str(uuid4()),issued_at=int(time.time())),who.signing_seed)
            return strict_loads(service.execute(engine,proof,method,path,query,raw))
        assert call(owner,'POST','/v1/messages',{'envelopes':[env]})['ok']
        receipt=keys.signed_object('PeerApplyReceipt',receipt_body(current2,env,1,target.device_id,'ACCEPTED'),target.signing_seed)
        query={'message_id':env['message_id'],'target_device_id':target.device_id}
        assert call(target,'POST','/v1/peer-receipts',receipt)=={'ok':True,'result':receipt}
        assert call(target,'POST','/v1/peer-receipts',receipt)=={'ok':True,'result':receipt}
        assert call(owner,'GET','/v1/peer-receipts',query=query)=={'ok':True,'result':{'receipt':receipt}}
        assert call(target,'GET','/v1/peer-receipts',query=query)['ok']
        assert call(third,'GET','/v1/peer-receipts',query=query)['ok'] is False
        changed=keys.signed_object('PeerApplyReceipt',{**receipt,'state_at_commit':'CANDIDATE'},target.signing_seed)
        assert call(target,'POST','/v1/peer-receipts',changed)['ok'] is False
        assert call(owner,'POST','/v1/peer-receipts',receipt)['ok'] is False
    finally:
        with Session(engine) as db,db.begin():
            for table in reversed(Base.metadata.sorted_tables):
                if 'project' in table.c:db.execute(delete(table).where(table.c.project==pid))
            db.execute(delete(Project).where(Project.id==pid))
        engine.dispose()


def test_pc_bounded_cycle_real_isolated_databases_without_peer_confirmation():
    """Two real PG services with an in-process HTTP boundary; not browser/TLS E2E."""
    from researchhub.sync.secure.transport_pg import client_engine,advance_history
    from researchhub.sync.secure.transport import SecureTransport
    from researchhub.sync.pc_identity import setup_node
    from researchhub.sync.pc_transport import PcTransport
    from researchhub.sync.pc_records import execute_command,read_record
    lifecycle=qa_module();relay=connect(lifecycle.url(lifecycle.config()),profile='host');service.initialize(relay)
    engine=client_engine();node=setup_node(engine,Path('storage/runtime/browser-sync-qa/pc/two-pg-tests')/str(uuid4()))
    old=node.binding['trust']['manifest_chain'][0];pid=old['opaque_project_id'];target=device()
    current=keys.transition(old,node.owner,add=target.member('writer',1))
    service.pin_bootstrap(relay,old,node.owner.signing_public,node.binding['trust']['recovery_root'])
    try:
        with Session(relay) as db,db.begin():service.membership_update(db,db.get(Project,pid),old,current,recovery=False)
        advance_history(engine,pid,current)
        def command(operation,version,heads,oid,title):
            return dict(command_id=str(uuid4()),transaction_id=str(uuid4()),object_id=oid,object_type='Note',operation=operation,expected_work_version=version,expected_heads=heads,patch={'title':title,'content':title})
        oid=str(uuid4());one=command('create',0,[],oid,'SYNTHETIC causal first')
        with Session(engine) as db,db.begin():first=execute_command(db,node.context,node.binding['semantic_project_id'],one)
        two=command('update',1,first['heads'],oid,'SYNTHETIC causal second')
        with Session(engine) as db,db.begin():execute_command(db,node.context,node.binding['semantic_project_id'],two)
        client=object.__new__(SecureTransport);client.engine=engine;client.device=node.owner;client.project=pid
        def request(method,path,body=None,query=None):
            raw=canonical_bytes(body) if body is not None else b'';query=query or {}
            proof=keys.signed_object('RelayRequest',dict(version=1,audience=AUDIENCE,method=method,path=path,query=query,opaque_project_id=pid,device_id=node.owner.device_id,membership_epoch=current['membership_epoch'],key_epoch=current['key_epoch'],manifest_digest=digest(current),body_digest=hashlib.sha256(raw).hexdigest(),request_id=str(uuid4()),issued_at=int(time.time())),node.owner.signing_seed)
            result=strict_loads(service.execute(relay,proof,method,path,query,raw))
            assert result['ok'],result.get('code');return result['result']
        client.request=request;bridge=PcTransport(engine,node);result=bridge.cycle(client)
        assert result['sent']==2 and result['received']==2 and result['confirmed']==0 and result['has_more']
        saved=[bridge.snapshot(c['transaction_id']) for c in (one,two)]
        retry=bridge.cycle(client);assert retry['sent']==0 and retry['received']==0 and retry['confirmed']==0
        assert saved==[bridge.snapshot(c['transaction_id']) for c in (one,two)]
        with Session(engine) as db:assert read_record(db,node.binding['semantic_project_id'],'Note',oid)['work']['pending']
    finally:
        with Session(relay) as db,db.begin():
            for table in reversed(Base.metadata.sorted_tables):
                if 'project' in table.c:db.execute(delete(table).where(table.c.project==pid))
            db.execute(delete(Project).where(Project.id==pid))
        engine.dispose();relay.dispose()
