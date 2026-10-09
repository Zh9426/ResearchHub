"""Real PC QA PostgreSQL, durable transport boundary tests (not network E2E)."""
from uuid import uuid4
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy.orm import Session
from researchhub.sync.pc_identity import setup_node
from researchhub.sync.pc_records import execute_command
from researchhub.sync.secure.transport import SecureTransport
from researchhub.sync.secure.transport_pg import locked
from test_pc_records import command

@pytest.fixture
def pc(engine):
    return setup_node(engine,Path('storage/runtime/browser-sync-qa/pc/transport-tests')/str(uuid4()))

def bridge(engine,pc):
    assert importlib.util.find_spec('researchhub.sync.pc_transport'),'PC durable transport bridge missing'
    from researchhub.sync.pc_transport import PcTransport
    return PcTransport(engine,pc)

def create(engine,pc):
    c=command()
    with Session(engine) as db,db.begin():execute_command(db,pc.context,pc.binding['semantic_project_id'],c)
    return c

def test_bridge_identity_survives_preseal_crash_and_exact_retry(engine,pc):
    c=create(engine,pc);b=bridge(engine,pc)
    def crash(point):
        if point=='after_prepare':raise RuntimeError('SYNTHETIC crash')
    with pytest.raises(RuntimeError,match='SYNTHETIC'):b.prepare(c['transaction_id'],barrier=crash)
    before=b.snapshot(c['transaction_id']); assert before['body'] is None
    ready=b.prepare(c['transaction_id']);again=b.prepare(c['transaction_id'])
    assert ready['message_id']==before['message_id']
    assert ready['body']==again['body'] and ready['message_id']==again['message_id']

def test_ordinary_request_releases_trust_lock_before_network(engine,pc):
    client=object.__new__(SecureTransport);client.engine=engine;client.project=pc.binding['opaque_project_id']
    def simulated_network(manifest,*args):
        with Session(engine) as other,other.begin():
            from sqlalchemy import text
            other.execute(text("SET LOCAL lock_timeout='200ms'"))
            row,_=locked(other,client.project)
            assert row.project==client.project
        return 'unlocked'
    client._request_manifest=simulated_network
    assert client.request('GET','/v1/membership')=='unlocked'

def test_receipt_requires_durable_receive_and_caches_exact_signed_bytes(engine,pc):
    from packages.secure_wire.canonical import strict_loads,digest
    from packages.secure_wire.checkpoint import extend_chain
    from researchhub.sync.secure.receiver import receive
    from researchhub.sync.secure.transport_pg import initialize
    from packages.secure_wire.peer_receipt import verify_peer_receipt
    initialize(engine);b=bridge(engine,pc);c=create(engine,pc);sealed=b.prepare(c['transaction_id'])
    client=object.__new__(SecureTransport);client.engine=engine;client.project=pc.binding['opaque_project_id'];client.device=pc.owner
    assert hasattr(client,'prepare_peer_receipt'),'durable receipt API missing'
    with pytest.raises(ValueError,match='DURABLE'):client.prepare_peer_receipt(1)
    env=strict_loads(sealed['body']);ed=digest(env);chain=extend_chain('0'*64,0,[{'sequence':1,'envelope_digest':ed}])
    page={'rows':[{'sequence':1,'envelope_digest':ed,'chain_digest':chain,'envelope':env}],'cursor':1,'chain_digest':chain,'has_more':False}
    receive(engine,client.project,pc.owner,{1:pc.project_key},page,0)
    one=client.prepare_peer_receipt(1);two=client.prepare_peer_receipt(1);assert one==two
    with Session(engine) as db,db.begin():_,history=locked(db,client.project)
    assert verify_peer_receipt(strict_loads(one),history[-1],env,1,pc.owner.device_id)['state_at_commit']=='ACCEPTED'

def test_receiver_trusted_policy_failure_rolls_back_page(engine,pc):
    import inspect
    from packages.secure_wire.canonical import strict_loads,digest
    from packages.secure_wire.checkpoint import extend_chain
    from researchhub.sync.secure.receiver import receive
    from researchhub.sync.secure.transport_pg import Received
    assert 'apply_record' in inspect.signature(receive).parameters,'trusted record policy injection missing'
    c=create(engine,pc);sealed=bridge(engine,pc).prepare(c['transaction_id']);env=strict_loads(sealed['body']);ed=digest(env)
    chain=extend_chain('0'*64,0,[{'sequence':1,'envelope_digest':ed}])
    page={'rows':[{'sequence':1,'envelope_digest':ed,'chain_digest':chain,'envelope':env}],'cursor':1,'chain_digest':chain,'has_more':False}
    def reject(db,tx,context):raise ValueError('trusted scope rejects')
    with pytest.raises(ValueError,match='trusted scope'):
        receive(engine,pc.binding['opaque_project_id'],pc.owner,{1:pc.project_key},page,0,apply_record=reject)
    with Session(engine) as db:assert db.get(Received,(pc.binding['opaque_project_id'],1)) is None

def test_manual_claim_excludes_concurrent_rpc_and_stale_token(engine,pc):
    b=bridge(engine,pc)
    assert hasattr(b,'claim'),'persistent manual claim missing'
    token=b.claim()
    with pytest.raises(ValueError,match='BUSY'):b.claim()
    b.release(token);replacement=b.claim()
    with pytest.raises(ValueError,match='CLAIM'):b.check(token)
    b.check(replacement);b.release(replacement)

def test_manual_cycle_available(engine,pc):
    assert hasattr(bridge(engine,pc),'cycle'),'bounded manual cycle missing'

def test_fresh_prepare_does_not_relabel_loaded_old_key(engine,pc):
    from researchhub.sync.secure.keys import Device,transition
    from researchhub.sync.secure.transport_pg import advance_history
    c=create(engine,pc);b=bridge(engine,pc)
    with Session(engine) as db,db.begin():_,history=locked(db,pc.binding['opaque_project_id'])
    peer=Device.generate();added=transition(history[-1],pc.owner,add=peer.member('writer',1))
    advance_history(engine,pc.binding['opaque_project_id'],added)
    advance_history(engine,pc.binding['opaque_project_id'],transition(added,pc.owner,revoke=peer.device_id))
    with pytest.raises(ValueError,match='LOADED_KEY_EPOCH_BLOCKED'):b.prepare(c['transaction_id'])
    assert b.snapshot(c['transaction_id']) is None

def test_cached_valid_ciphertext_cannot_be_rebound_to_other_command(engine,pc):
    from researchhub.sync.pc_transport import PcWire
    from researchhub.sync.secure.transport_pg import SealedOutbox
    a=create(engine,pc);b=create(engine,pc);bridge_=bridge(engine,pc)
    one=bridge_.prepare(a['transaction_id']);two=bridge_.prepare(b['transaction_id'])
    # Explicit component corruption fixture: two independently valid synthetic envelopes.
    with Session(engine) as db,db.begin():
        row=db.get(PcWire,a['transaction_id']);row.body=two['body']
        db.get(SealedOutbox,(pc.binding['opaque_project_id'],one['message_id'])).body=two['body']
    with pytest.raises(ValueError,match='BINDING'):bridge_.prepare(a['transaction_id'])

def test_status_is_latest_local_operation_not_old_receipt(engine,pc):
    from researchhub.sync import pc_transport
    assert hasattr(pc_transport,'record_status'),'per-record persisted sync status missing'
    c=create(engine,pc)
    with Session(engine) as db,db.begin():
        _,history=locked(db,pc.binding['opaque_project_id'])
        state=pc_transport.record_status(db,pc,'ResearchRun',c['object_id'],history[-1])
    assert state['transaction_id']==c['transaction_id'] and state['local']=='SAVED'
    assert state['conversion']=='NOT_CONVERTED' and state['transport']=='NOT_SENT' and state['peer']=='UNCONFIRMED'
    b=bridge(engine,pc);b.prepare(c['transaction_id'])
    with Session(engine) as db,db.begin():
        _,history=locked(db,pc.binding['opaque_project_id'])
        state=pc_transport.record_status(db,pc,'ResearchRun',c['object_id'],history[-1])
    assert state['conversion']=='SEALED' and state['review']=='NOT_REQUESTED'


def test_status_verified_history_never_confirms_new_command_or_science(engine,pc):
    from copy import deepcopy
    from researchhub.sync.pc_transport import record_status,PcTransportFact,PcWire
    from researchhub.sync.pc_records import read_record
    from researchhub.sync.secure.keys import Device,transition,signed_object
    from researchhub.sync.secure.transport_pg import advance_history
    from researchhub.sync.record_policy import apply_record_in_session
    from packages.secure_wire.peer_receipt import receipt_body
    from packages.secure_wire.canonical import canonical_bytes,strict_loads,digest
    peer=Device.generate()
    with Session(engine) as db,db.begin():_,history=locked(db,pc.binding['opaque_project_id'])
    manifest=transition(history[-1],pc.owner,add=peer.member('writer',1));advance_history(engine,pc.binding['opaque_project_id'],manifest)
    c=create(engine,pc);b=bridge(engine,pc)
    def status():
        with Session(engine) as db,db.begin():return record_status(db,pc,'ResearchRun',c['object_id'],manifest)
    def confirm(cmd):
        sealed=b.prepare(cmd['transaction_id']);env=strict_loads(sealed['body'])
        # TEST_ONLY component projection facts, not network or business E2E evidence.
        ack=dict(stage='RELAY_STORED',message_id=env['message_id'],sequence=1,envelope_digest=digest(env),chain_digest='0'*64)
        with Session(engine) as db,db.begin():db.add(PcTransportFact(project=env['opaque_project_id'],message=env['message_id'],kind='relay',body=canonical_bytes(ack)))
        assert status()['transport']=='RELAY_STORED' and status()['peer']=='UNCONFIRMED'
        proof=signed_object('PeerApplyReceipt',receipt_body(manifest,env,1,peer.device_id,'ACCEPTED'),peer.signing_seed)
        with Session(engine) as db,db.begin():db.add(PcTransportFact(project=env['opaque_project_id'],message=env['message_id'],kind='peer:'+peer.device_id,body=canonical_bytes(proof)))
        assert status()['peer']=='VERIFIED'
    confirm(c)
    with Session(engine) as db:view_=read_record(db,pc.binding['semantic_project_id'],'ResearchRun',c['object_id'])
    newer={**command(),'object_id':c['object_id'],'operation':'update','expected_work_version':1,'expected_heads':view_['trusted']['heads'],'patch':{'observation':'SYNTHETIC newer'}}
    with Session(engine) as db,db.begin():execute_command(db,pc.context,pc.binding['semantic_project_id'],newer)
    state=status();assert state['peer']=='UNCONFIRMED' and state['transport']=='NOT_SENT' and state['transaction_id']==newer['transaction_id']
    confirm(newer)
    with Session(engine) as db:branch=deepcopy(strict_loads(db.get(PcWire,newer['transaction_id']).source))
    tid=str(uuid4());cid=str(uuid4());branch.update(transaction_id=tid,idempotency_key=tid,ordered_change_ids=[cid])
    branch['changes'][0].update(transaction_id=tid,change_id=cid,audit_id=str(uuid4()),payload={'observation':'SYNTHETIC competing branch'})
    with Session(engine) as db,db.begin():apply_record_in_session(db,branch,pc.context,pc.binding['module_snapshot'],project_id=pc.binding['semantic_project_id'])
    state=status();assert state['peer']=='VERIFIED' and state['current_record']=='CONFLICTED' and state['state_at_commit']=='ACCEPTED' and state['review']=='NOT_REQUESTED'
    assert 'body' not in state and 'envelope' not in state
