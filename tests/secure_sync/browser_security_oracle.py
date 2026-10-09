"""TEST ONLY independent Python oracle. All secret artifacts remain in ignored attempt paths."""
import json, os, sys, copy
from pathlib import Path
from uuid import uuid4
from researchhub.sync.secure.crypto import wrap_key, sign, signing_public
from researchhub.sync.secure.envelope import seal_transaction, open_transaction
from researchhub.sync.secure.nonce import NonceVault
from researchhub.sync.secure.keys import Device, signed_object
from packages.secure_wire.canonical import digest
from packages.secure_wire.membership import fingerprint, preimage, verify_signed, challenge_sas
from packages.secure_wire.envelope import b64encode, b64decode

request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
out = Path(sys.argv[2])
if request['action'] == 'init':
    d = request['device']; owner = Device.generate(); recovery = Device.generate()
    project = str(uuid4()); key = os.urandom(32); response = os.urandom(32)
    owner_member = owner.member('owner', 1)
    recipient = dict(device_id=d['deviceId'], signing_public_key=d['signingPublic'], recipient_public_key=d['recipientPublic'], fingerprint=fingerprint(d['signingPublic'], d['recipientPublic']), role='writer', status='ACTIVE', nonce_prefix=2, granted_at=0, revoked_at=None)
    bootstrap = signed_object('Membership', dict(version=1,opaque_project_id=project,membership_epoch=1,key_epoch=1,previous_digest='0'*64,operation='bootstrap',authority_device_id=owner.device_id,recovery_device_id=recovery.device_id,recovery_signing_public_key=recovery.signing_public,recovery_recipient_public_key=recovery.recipient_public,members=[owner_member]), owner.signing_seed)
    manifest = signed_object('Membership', dict(**{k:v for k,v in bootstrap.items() if k!='signature'}, **{}), owner.signing_seed)
    manifest.update(membership_epoch=2,previous_digest=digest(bootstrap),operation='grant',members=[owner_member,recipient]);manifest=signed_object('Membership',{k:v for k,v in manifest.items() if k!='signature'},owner.signing_seed)
    context=dict(opaque_project_id=project,recipient_device_id=d['deviceId'],key_epoch=1,membership_epoch=2,session_id=str(uuid4()),recipient_signing_public_key=d['signingPublic'],recipient_public_key=d['recipientPublic'])
    grant=signed_object('ProjectGrant',dict(version=1,authority_device_id=owner.device_id,context=context,role='writer',manifest_digest=digest(manifest),wrapped_key=b64encode(wrap_key(bytes.fromhex(d['recipientPublic']),key,context))),owner.signing_seed)
    challenge_context={**context,'membership_epoch':1,'session_id':str(uuid4())}
    challenge=dict(version=1,session_id=challenge_context['session_id'],opaque_project_id=project,manifest_digest=digest(bootstrap),membership_epoch=1,key_epoch=1,authority_device_id=owner.device_id,recipient=recipient,issued_at=1000,expires_at=1300,wrapped_challenge=b64encode(wrap_key(bytes.fromhex(d['recipientPublic']),response,challenge_context)))
    challenge['sas']=challenge_sas(challenge);challenge=signed_object('PairingChallenge',challenge,owner.signing_seed)
    fixture=json.loads(Path('fixtures/sync/v2/envelope.TEST_ONLY.json').read_text(encoding='utf-8'))
    tx=copy.deepcopy(fixture['transaction']);tx['device_id']=owner.device_id
    for change in tx['changes']:change['device_id']=owner.device_id
    nv=NonceVault(out.parent/'python-nonce.sqlite');nv.register_new(key,1)
    env=seal_transaction(tx,key,owner.signing_seed,nv,1,opaque_project_id=project,sender_device_id=owner.device_id,membership_epoch=2,key_epoch=1,message_id=str(uuid4()))
    fork=copy.deepcopy(manifest);fork['members'][1]['nonce_prefix']=3;fork=signed_object('Membership',{k:v for k,v in fork.items() if k!='signature'},owner.signing_seed)
    revoked=copy.deepcopy(manifest);revoked.update(membership_epoch=3,key_epoch=2,previous_digest=digest(manifest),operation='revoke');revoked['members'][1].update(status='REVOKED',revoked_at=1);revoked=signed_object('Membership',{k:v for k,v in revoked.items() if k!='signature'},owner.signing_seed)
    checkpoint=signed_object('Checkpoint',dict(version=1,opaque_project_id=project,membership_epoch=2,key_epoch=1,cursor=0,chain_digest='0'*64,creator_device_id=owner.device_id),owner.signing_seed)
    changed_grant=copy.deepcopy(grant);changed_grant['wrapped_key']=b64encode(wrap_key(bytes.fromhex(d['recipientPublic']),os.urandom(32),context));changed_grant=signed_object('ProjectGrant',{k:v for k,v in changed_grant.items() if k!='signature'},owner.signing_seed)
    state=dict(key=key.hex(),response=response.hex(),signing_public=d['signingPublic'],challenge=challenge,project=project,semantic_project=request['semanticProject'])
    (out.parent/'python-private.TEST_ONLY.json').write_text(json.dumps(state),encoding='utf-8')
    result=dict(ownerRoot=owner.signing_public,recoveryRoot=recovery.signing_public,chain=[bootstrap,manifest],grant=grant,challenge=challenge,semanticProject=request['semanticProject'],actorId=str(uuid4()),pythonEnvelope=env,pythonTransaction=tx,fork=fork,revoked=revoked,checkpoint=checkpoint,changedGrant=changed_grant)
elif request['action']=='verify':
    state=json.loads((out.parent/'python-private.TEST_ONLY.json').read_text(encoding='utf-8'));proof=request['proof'];verify_signed('PairingProof',proof,state['signing_public'])
    if proof['challenge_digest']!=digest(state['challenge']) or proof['challenge_response']!=state['response']:raise ValueError('PAIRING_PROOF_INVALID')
    count=0
    for envelope in request['envelopes']:
        tx=open_transaction(envelope,bytes.fromhex(state['key']),bytes.fromhex(state['signing_public']),project_id=state['semantic_project'],opaque_project_id=state['project'],sender_device_id=envelope['sender_device_id'],membership_epoch=2,key_epoch=1,nonce_prefix=2)
        if tx['protocol_version']!=2 or tx['schema_version']!=2:raise ValueError('VERSION_MISMATCH')
        count+=1
    result={'verified_envelopes':count,'verified_pairing_proof':True}
else:raise ValueError('UNKNOWN_ACTION')
out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
print('TEST_ONLY_ORACLE_OK')
