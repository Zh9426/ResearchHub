import {remoteOnlyWorkbench} from './workbench';
/** TEST_ONLY synthetic native WebCrypto fixture; never included in app builds. */
import {manualReceipts} from './manual';
import {WireSealer} from '../src/sync/seal';
import {openLocalDatabase} from '../src/local/db';
import {prepareSyntheticProjects} from '../src/local/seeds';
import {LocalCommandService} from '../src/local/commands';
import {StableWireAdapter} from '../src/sync/wire';
import {adversarial} from './scenarios';
import {identityCollisions} from './identity-collisions';
import * as security from '../../../packages/secure-sync/src/browser';
import {canonicalBytes,digest} from '../../../packages/sync-protocol/src/browser';
const open=()=>openLocalDatabase('researchhub-browser-sync-qa-receive-TEST_ONLY');
const sealer=new WireSealer(open),commands=new LocalCommandService(open,'receive-TEST_ONLY',true),adapter=new StableWireAdapter(open);
async function meta(id:string,value?:any){const db=await open();try{return await new Promise<any>((ok,no)=>{const tx=db.transaction('meta',value===undefined?'readonly':'readwrite');const r=value===undefined?tx.objectStore('meta').get(id):tx.objectStore('meta').put({...value,id});tx.oncomplete=()=>ok(r.result);tx.onabort=()=>no(tx.error);});}finally{db.close();}}
const signed=async(kind:string,obj:any,key:CryptoKey)=>({...obj,signature:security.b64encode(await security.sign(key,security.preimage(kind,obj)))});
async function fixture(){
 const vault=await sealer.initialize(),device=await vault.device(),owner=await security.generateDevice(),recovery=await security.generateDevice(),project=(await prepareSyntheticProjects())[0],opaque=crypto.randomUUID();
 const member=async(d:any,role:string,prefix:number)=>({device_id:d.deviceId,signing_public_key:d.signingPublic,recipient_public_key:d.recipientPublic,fingerprint:await security.fingerprint(d.signingPublic,d.recipientPublic),role,status:'ACTIVE',nonce_prefix:prefix,granted_at:0,revoked_at:null});
 const boot=await signed('Membership',{version:1,opaque_project_id:opaque,membership_epoch:1,key_epoch:1,previous_digest:'0'.repeat(64),operation:'bootstrap',authority_device_id:owner.deviceId,recovery_device_id:recovery.deviceId,recovery_signing_public_key:recovery.signingPublic,recovery_recipient_public_key:recovery.recipientPublic,members:[await member(owner,'owner',1)]},owner.signing.privateKey);
 const head=await signed('Membership',{...boot,membership_epoch:2,previous_digest:await digest(boot),operation:'grant',members:[...boot.members,await member(device,'writer',2)]},owner.signing.privateKey);
 const local={device_id:device.deviceId,actor_id:crypto.randomUUID(),actor_type:'human',role:'writer'},remote={device_id:owner.deviceId,actor_id:crypto.randomUUID(),actor_type:'human',role:'owner'};
 const binding={binding_version:1,semantic_project_id:project.id,opaque_project_id:opaque,module_snapshot:project.module_snapshot,module_snapshot_hash:await digest(project.module_snapshot),local_module_hash:{algorithm:'sha256-json-stringify',value:project.module_hash},capabilities:{protocol_version:2,schema_version:2,object_types:['ResearchRun','Note']},principal:local,principal_map:[remote,local],trust:{owner_root:owner.signingPublic,recovery_root:recovery.signingPublic,manifest_chain:[boot,head],manifest_head:await digest(head),membership_epoch:2,key_epoch:1}};
 const raw=crypto.getRandomValues(new Uint8Array(32)),context={opaque_project_id:opaque,recipient_device_id:device.deviceId,key_epoch:1,membership_epoch:2,session_id:crypto.randomUUID(),recipient_signing_public_key:device.signingPublic,recipient_public_key:device.recipientPublic};
 const grant=await signed('ProjectGrant',{version:1,authority_device_id:owner.deviceId,context,role:'writer',manifest_digest:await digest(head),wrapped_key:security.b64encode(await security.wrapKey(security.hexDecode(device.recipientPublic),raw,context))},owner.signing.privateKey);
 const wrapper=await signed('PcProjectBinding',{version:1,binding},owner.signing.privateKey);
 const db=await open();await new Promise<void>((ok,no)=>{const tx=db.transaction(['projects','meta'],'readwrite');tx.objectStore('projects').put(project);tx.objectStore('meta').put({id:'identity',workspace_id:crypto.randomUUID(),device_id:device.deviceId,scope:'SYNTHETIC_QA',authorization:'none'});tx.oncomplete=()=>ok();tx.onabort=()=>no(tx.error);});db.close();
 let counter=0;
 const transaction=(title:string,oid=crypto.randomUUID(),parents:string[]=[],dependencies:string[]=[])=>{const tid=crypto.randomUUID(),cid=crypto.randomUUID(),common={project_id:project.id,device_id:owner.deviceId,actor_id:remote.actor_id,actor_type:'human',schema_version:2,created_at:'2026-10-09T00:00:00.000Z'};return {...common,transaction_id:tid,idempotency_key:tid,protocol_version:2,ordered_change_ids:[cid],dependencies,changes:[{...common,transaction_id:tid,change_id:cid,audit_id:crypto.randomUUID(),object_type:'Note',object_id:oid,operation:parents.length?'update':'create',parents,payload:{title,content:title},module_snapshot_hash:binding.module_snapshot_hash}]};};
 const envelope=async(tx:any)=>{const nonce=new Uint8Array(12);new DataView(nonce.buffer).setUint32(0,1);new DataView(nonce.buffer).setBigUint64(4,BigInt(++counter));return security.sealWithNonce(tx,raw,x=>security.sign(owner.signing.privateKey,x),nonce,{opaque_project_id:opaque,sender_device_id:owner.deviceId,membership_epoch:2,key_epoch:1,message_id:crypto.randomUUID(),record_type:'transaction',protocol_version:2,schema_version:2,dependencies:tx.dependencies});};
 const page=async(txs:any[],start=0,chain='0'.repeat(64))=>{const rows:any[]=[];for(const tx of txs){const env=await envelope(tx),sequence=start+rows.length+1,envelope_digest=await digest(env);chain=await security.extendChain(chain,sequence-1,[{sequence,envelope_digest}]);rows.push({sequence,envelope_digest,chain_digest:chain,envelope:env});}return {rows,cursor:start+rows.length,chain_digest:chain,has_more:false};};
 return {vault,device,owner,project,binding,grant,wrapper,transaction,page,boot,head};
}
(window as any).receiveQA={remoteOnlyWorkbench,manualReceipts,open,sealer,commands,adapter,meta,fixture,digest,canonicalBytes,security,signed,adversarial,identityCollisions};
