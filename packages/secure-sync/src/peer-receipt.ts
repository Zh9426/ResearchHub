/** Public receipt verification. Caller supplies pinned history and concrete expected peer. */
import {digest} from '../../sync-protocol/src/browser.ts';
import {fields,integer,uuid,hex,memberOf,verifySigned,verifyActiveEnvelope,type PublicObject} from './membership-core.ts';
import {b64decode} from './binary.ts';
const RECEIPT_FIELDS='version opaque_project_id sender_device_id target_device_id message_id sequence envelope_digest semantic_transaction_digest membership_epoch key_epoch manifest_digest stage state_at_commit signature'.split(' ');
export function validatePeerReceipt(value:PublicObject){
 fields(value,RECEIPT_FIELDS);integer(value.version,1,1);
 for(const key of ['opaque_project_id','sender_device_id','target_device_id','message_id'])uuid(value[key]);
 for(const key of ['sequence','membership_epoch','key_epoch'])integer(value[key],1);
 for(const key of ['envelope_digest','semantic_transaction_digest','manifest_digest'])hex(value[key],32);
 b64decode(value.signature,64);
 if(value.stage!=='KERNEL_APPLIED'||!['ACCEPTED','CANDIDATE'].includes(value.state_at_commit))throw Error('INVALID_PEER_RECEIPT');
 return value;
}
export async function receiptBody(manifest:PublicObject,envelope:PublicObject,sequence:number,target:string,state:string){
 integer(sequence,1);uuid(target);
 return {version:1,opaque_project_id:envelope.opaque_project_id,sender_device_id:envelope.sender_device_id,target_device_id:target,message_id:envelope.message_id,sequence,envelope_digest:await digest(envelope),semantic_transaction_digest:envelope.semantic_transaction_digest,membership_epoch:envelope.membership_epoch,key_epoch:envelope.key_epoch,manifest_digest:await digest(manifest),stage:'KERNEL_APPLIED',state_at_commit:state};
}
export async function verifyPeerReceipt(value:PublicObject,manifest:PublicObject,envelope:PublicObject,sequence:number,target:string){
 value=structuredClone(value);manifest=structuredClone(manifest);envelope=structuredClone(envelope);
 validatePeerReceipt(value);await verifyActiveEnvelope(envelope as any,manifest);
 const expected=await receiptBody(manifest,envelope,sequence,target,value.state_at_commit);
 if(Object.entries(expected).some(([key,item])=>value[key]!==item))throw Error('PEER_RECEIPT_BINDING_MISMATCH');
 await verifySigned('PeerApplyReceipt',value,memberOf(manifest,target).signing_public_key);
 return value;
}
