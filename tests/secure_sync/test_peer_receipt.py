import copy
import importlib.util
import json
from pathlib import Path
import pytest
from researchhub.sync.secure import keys
from packages.secure_wire.canonical import digest

V = json.loads(Path('fixtures/sync/v2/envelope.TEST_ONLY.json').read_text(encoding='utf-8'))

def api():
    assert importlib.util.find_spec('packages.secure_wire.peer_receipt'), 'PeerApplyReceipt API missing'
    from packages.secure_wire.peer_receipt import verify_peer_receipt
    return verify_peer_receipt

@pytest.fixture
def case():
    sender = keys.Device.generate(); target = keys.Device.generate(); kit = keys.RecoveryKit.generate()
    env = copy.deepcopy(V['cases'][0]['envelope'])
    manifest = keys.transition(keys.bootstrap(env['opaque_project_id'],sender,kit),sender,add=target.member('writer',1))
    env.update(nonce='000000000000000000000001',sender_device_id=sender.device_id,membership_epoch=manifest['membership_epoch'],key_epoch=manifest['key_epoch'])
    from researchhub.sync.secure.crypto import sign
    from packages.secure_wire.envelope import signature_preimage,b64encode
    env['signature']=b64encode(sign(sender.signing_seed,signature_preimage(env)))
    value = dict(version=1,opaque_project_id=env['opaque_project_id'],sender_device_id=sender.device_id,target_device_id=target.device_id,message_id=env['message_id'],sequence=1,envelope_digest=digest(env),semantic_transaction_digest=env['semantic_transaction_digest'],membership_epoch=env['membership_epoch'],key_epoch=env['key_epoch'],manifest_digest=digest(manifest),stage='KERNEL_APPLIED',state_at_commit='ACCEPTED')
    return env,manifest,sender,target,value

def test_valid_receipt_binds_exact_target_and_history(case):
    env,m,s,t,v=case
    receipt=keys.signed_object('PeerApplyReceipt',v,t.signing_seed)
    assert api()(receipt,m,env,1,t.device_id)==receipt
    v['state_at_commit']='CANDIDATE'
    assert api()(keys.signed_object('PeerApplyReceipt',v,t.signing_seed),m,env,1,t.device_id)['state_at_commit']=='CANDIDATE'

@pytest.mark.parametrize('field,value',[('target_device_id','11111111-1111-1111-1111-111111111111'),('sender_device_id','11111111-1111-1111-1111-111111111111'),('sequence',2),('sequence',True),('envelope_digest','0'*64),('semantic_transaction_digest','0'*64),('membership_epoch',999),('key_epoch',999),('manifest_digest','0'*64),('stage','SCIENTIFIC_ACCEPTED'),('state_at_commit','TRANSPORT_QUARANTINED'),('extra',1)])
def test_receipt_signed_but_wrong_binding_rejected(case,field,value):
    env,m,s,t,v=case;v[field]=value
    with pytest.raises(ValueError):api()(keys.signed_object('PeerApplyReceipt',v,t.signing_seed),m,env,1,t.device_id)

def test_other_member_cannot_sign_target_receipt(case):
    env,m,s,t,v=case
    with pytest.raises(ValueError):api()(keys.signed_object('PeerApplyReceipt',v,s.signing_seed),m,env,1,t.device_id)

def test_old_receipt_cannot_validate_as_current_after_revoke(case):
    env,m,s,t,v=case; receipt=keys.signed_object('PeerApplyReceipt',v,t.signing_seed)
    with pytest.raises(ValueError):api()(receipt,keys.transition(m,s,revoke=t.device_id),env,1,t.device_id)



def test_shared_public_vector():
    v=json.loads(Path('fixtures/sync/secure-v1/peer-receipt.TEST_ONLY.json').read_text(encoding='utf-8'))
    assert api()(v['receipt'],v['manifest'],v['envelope'],v['sequence'],v['target'])==v['receipt']
