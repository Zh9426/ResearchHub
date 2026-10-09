import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const v=JSON.parse(readFileSync(new URL('../../../fixtures/sync/secure-v1/peer-receipt.TEST_ONLY.json',import.meta.url),'utf8'));
async function api(){assert.ok(existsSync(new URL('../src/peer-receipt.ts',import.meta.url)),'PeerApplyReceipt API missing');return import('../src/peer-receipt.ts');}
test('Python signature verifies in native WebCrypto and binds exact peer and envelope',async()=>{
 const {verifyPeerReceipt}=await api();
 assert.deepEqual(await verifyPeerReceipt(v.receipt,v.manifest,v.envelope,v.sequence,v.target),v.receipt);
 for(const [field,value] of Object.entries({target_device_id:v.envelope.sender_device_id,sequence:2,envelope_digest:'0'.repeat(64),semantic_transaction_digest:'0'.repeat(64),membership_epoch:99,key_epoch:99,manifest_digest:'0'.repeat(64),stage:'SCIENTIFIC_ACCEPTED',state_at_commit:'TRANSPORT_QUARANTINED',signature:'A'.repeat(86)})){
  await assert.rejects(verifyPeerReceipt({...v.receipt,[field]:value},v.manifest,v.envelope,v.sequence,v.target));
 }
 await assert.rejects(verifyPeerReceipt(v.receipt,v.manifest,v.envelope,v.sequence,v.envelope.sender_device_id));
});
test('receipt rejects alternate schema and numeric spellings',async()=>{
 const {validatePeerReceipt}=await api();
 for(const patch of [{extra:1},{sequence:true},{version:2},{sequence:-0},{sequence:1.5}])assert.throws(()=>validatePeerReceipt({...v.receipt,...patch}));
});
test('async verification snapshots caller-owned inputs before crypto awaits',async()=>{
 const {verifyPeerReceipt}=await api(),receipt=structuredClone(v.receipt),manifest=structuredClone(v.manifest),envelope=structuredClone(v.envelope);
 const pending=verifyPeerReceipt(receipt,manifest,envelope,v.sequence,v.target);
 receipt.state_at_commit='CANDIDATE';envelope.message_id='11111111-1111-4111-8111-111111111111';manifest.members=[];
 assert.deepEqual(await pending,v.receipt);
});
