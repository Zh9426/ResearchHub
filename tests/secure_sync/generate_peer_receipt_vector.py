"""Generate public interop vectors using deliberately fixed TEST ONLY seeds."""
import json
import sys
from pathlib import Path
sys.path[:0]=['.','apps/api']
from researchhub.sync.secure import keys
from researchhub.sync.secure.crypto import sign
from packages.secure_wire.envelope import signature_preimage,b64encode
from packages.secure_wire.canonical import digest
from packages.secure_wire.peer_receipt import receipt_body

def generate():
    v=json.loads(Path('fixtures/sync/v2/envelope.TEST_ONLY.json').read_text(encoding='utf-8'))
    env=v['cases'][0]['envelope']
    sender=keys.Device(env['sender_device_id'],bytes.fromhex(v['signing_seed_TEST_ONLY']),bytes([31])*32)
    target=keys.Device('33333333-3333-4333-8333-333333333333',bytes([32])*32,bytes([33])*32)
    kit=keys.RecoveryKit.from_public_test_vectors(bytes(range(128,160)),bytes(range(160,192)),device_id='44444444-4444-4444-8444-444444444444')
    manifest=keys.transition(keys.bootstrap(env['opaque_project_id'],sender,kit),sender,add=target.member('writer',1))
    env.update(nonce='000000000000000000000001',membership_epoch=manifest['membership_epoch'])
    env['signature']=b64encode(sign(sender.signing_seed,signature_preimage(env)))
    receipt=keys.signed_object('PeerApplyReceipt',receipt_body(manifest,env,1,target.device_id,'ACCEPTED'),target.signing_seed)
    return dict(label='SYNTHETIC TEST ONLY public verification vector',envelope=env,manifest=manifest,target=target.device_id,sequence=1,receipt=receipt)
if __name__=='__main__':
    Path('fixtures/sync/secure-v1/peer-receipt.TEST_ONLY.json').write_text(json.dumps(generate(),indent=2)+'\n',encoding='utf-8')
