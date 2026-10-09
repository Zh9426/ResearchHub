/** Joining is vault-first, followed by a short business transaction. */
import {canonicalBytes,digest,strictLoads} from '../../../../packages/sync-protocol/src/browser';
import {fingerprint,verifyBootstrap,verifyTransition,verifySigned,verifyGrant,memberOf,type PublicObject} from '../../../../packages/secure-sync/src/membership-core';
import {answerChallenge,confirmation} from '../../../../packages/secure-sync/src/pairing-browser';
import {relayFetch,AUDIENCE} from '../../../../packages/secure-sync/src/request-browser';
import {WireSealer} from './seal';
import {previewBinding,type PublicProjectBinding} from './binding';
const req=<T>(r:IDBRequest<T>)=>new Promise<T>((ok,no)=>{r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});
const same=async(a:unknown,b:unknown)=>(await digest(a))===(await digest(b));
export function parsePublic(text:string):PublicObject{if(new TextEncoder().encode(text).length>524288)throw Error('INPUT_TOO_LARGE');return strictLoads(text) as PublicObject;}
export class BrowserJoin {
 constructor(private open:()=>Promise<IDBDatabase>){}
 private async tx<T>(mode:IDBTransactionMode,work:(tx:IDBTransaction)=>Promise<T>):Promise<T>{
  const db=await this.open(),tx=db.transaction(['meta','projects','objects','operations','audit'],mode);let value:T,error:unknown;
  const done=new Promise<T>((ok,no)=>{tx.oncomplete=()=>ok(value);tx.onabort=()=>no(error??tx.error);});
  try{value=await work(tx);}catch(e){error=e;tx.abort();}try{return await done;}finally{db.close();}
 }
 async state(){return this.tx('readonly',tx=>req(tx.objectStore('meta').get('join-session')));}
 async recipient(){
  await this.tx('readonly',async tx=>{if(await req(tx.objectStore('projects').count())||await req(tx.objectStore('meta').get('identity')))throw Error('EMPTY_WORKSPACE_REQUIRED');});
  const d=await (await new WireSealer(this.open).initialize()).device();
  return {device_id:d.deviceId,signing_public_key:d.signingPublic,recipient_public_key:d.recipientPublic,fingerprint:await fingerprint(d.signingPublic,d.recipientPublic),role:'writer',status:'ACTIVE',nonce_prefix:0,granted_at:Math.floor(Date.now()/1000),revoked_at:null};
 }
 async answer(start:PublicObject,owner:string,recovery:string,sas:string){
  if(start.stage!=='CHALLENGE_READY'||!owner||!recovery||sas!==start.challenge?.sas||owner!==start.bootstrap?.owner_root||recovery!==start.bootstrap?.recovery_root)throw Error('INDEPENDENT_CONFIRMATION_REQUIRED');
  const chain=start.bootstrap.manifest_chain;
  let head=await verifyBootstrap(chain[0],owner,recovery);for(const next of chain.slice(1))head=await verifyTransition(head,next,recovery);
  if(start.session_id!==start.challenge.session_id)throw Error('PAIRING_SESSION_MISMATCH');
  const device=await (await new WireSealer(this.open).vault()).device();
  const proof=await answerChallenge(start.challenge,head,device,{confirmation:confirmation(start.challenge),now:Math.floor(Date.now()/1000)});
  const record={id:'join-session',stage:'ANSWERED',start,owner,recovery,proof};
  await this.tx('readwrite',async tx=>{
   if(await req(tx.objectStore('projects').count())||await req(tx.objectStore('meta').get('identity')))throw Error('EMPTY_WORKSPACE_REQUIRED');
   const old=await req(tx.objectStore('meta').get('join-session'));
   if(old&&JSON.stringify(old)!==JSON.stringify(record))throw Error('JOIN_SESSION_ALREADY_PINNED');
   await req(tx.objectStore('meta').put(record));
  });
  return {session_id:start.session_id,proof};
 }
 async complete(result:PublicObject){
  const saved=await this.state();if(!saved)throw Error('JOIN_CONFIRMATION_REQUIRED');
  const {start,owner,recovery}=saved,receipt=result.pairing_receipt,wrapper=result.signed_binding,b=wrapper?.binding as PublicProjectBinding;
  if(result.stage!=='COMPLETE'||result.session_id!==start.session_id||receipt?.challenge_digest!==await digest(start.challenge)||wrapper?.version!==1)throw Error('PAIRING_RECEIPT_MISMATCH');
  const preview=await previewBinding(b);if(preview.state==='BLOCKED')throw Error('BINDING_INVALID');
  const chain=b.trust.manifest_chain;
  if(chain.length!==start.bootstrap.manifest_chain.length+1||b.trust.owner_root!==owner||b.trust.recovery_root!==recovery)throw Error('CHAIN_MISMATCH');
  let head=await verifyBootstrap(chain[0],owner,recovery);
  for(let i=0;i<start.bootstrap.manifest_chain.length;i++)if(!await same(chain[i],start.bootstrap.manifest_chain[i]))throw Error('CHAIN_MISMATCH');
  for(const next of chain.slice(1))head=await verifyTransition(head,next,recovery);
  const previous=chain.at(-2)!;
  if(!await same(head,receipt.manifest)||head.previous_digest!==start.challenge.manifest_digest||head.key_epoch!==previous.key_epoch||head.membership_epoch!==b.trust.membership_epoch||head.key_epoch!==b.trust.key_epoch||await digest(head)!==b.trust.manifest_head||head.opaque_project_id!==b.opaque_project_id)throw Error('RECEIPT_HEAD_MISMATCH');
  const vault=await new WireSealer(this.open).vault(),device=await vault.device(),member=memberOf(head,device.deviceId,['writer']);
  if(!await same(member,start.challenge.recipient)||member.signing_public_key!==device.signingPublic||member.recipient_public_key!==device.recipientPublic||b.principal.device_id!==device.deviceId||b.principal.role!==member.role)throw Error('TARGET_PRINCIPAL_MISMATCH');
  const active=head.members.filter((m:PublicObject)=>m.status==='ACTIVE');
  if(active.length!==b.principal_map.length||active.some((m:PublicObject)=>!b.principal_map.some(p=>p.device_id===m.device_id&&p.role===m.role)))throw Error('PRINCIPAL_MAP_MISMATCH');
  await verifySigned('PcProjectBinding',wrapper,memberOf(head,head.authority_device_id,['owner']).signing_public_key);
  await verifyGrant(receipt.grant,head);
  if(receipt.grant.context.session_id!==start.session_id||receipt.grant.context.recipient_device_id!==device.deviceId)throw Error('GRANT_SESSION_MISMATCH');
  // No business authorization can exist before these independently durable gates.
  const trust=await vault.pin(owner,recovery,chain);await vault.acceptGrant(receipt.grant);
  const hello=await relayFetch(device,trust,'POST','/v1/hello',{},{});
  if(hello.audience!==AUDIENCE||hello.manifest_digest!==trust.headDigest||!Array.isArray(hello.transaction_version_pairs)||!hello.transaction_version_pairs.some((p:unknown)=>JSON.stringify(p)==='[2,2]'))throw Error('HELLO_CAPABILITY_OR_HEAD_MISMATCH');
  if(hello.sequence!==0&&saved.stage!=='COMPLETE')throw Error('BOOTSTRAP_REQUIRED');
  const canonicalBinding=strictLoads(canonicalBytes(b)) as PublicProjectBinding;
  const resultDigest=await digest(result);
  await this.tx('readwrite',async tx=>{
   const meta=tx.objectStore('meta'),current=await req(meta.get('join-session'));
   if(JSON.stringify(current)!==JSON.stringify(saved))throw Error('JOIN_CAS_MISMATCH');
   const old=await req(meta.get(`binding:${b.semantic_project_id}`));
   if(saved.stage==='COMPLETE'){
    if(saved.resultDigest!==resultDigest||old?.state!=='VERIFIED'||JSON.stringify(old.binding)!==JSON.stringify(canonicalBinding))throw Error('BINDING_CHANGED');return;
   }
   if(await req(tx.objectStore('projects').count())||await req(meta.get('identity'))||await req(tx.objectStore('objects').count())||await req(tx.objectStore('operations').count())||await req(tx.objectStore('audit').count()))throw Error('EMPTY_WORKSPACE_REQUIRED');
   await req(tx.objectStore('projects').add({id:b.semantic_project_id,route_alias:b.module_snapshot.id==='ice-sonocuring'?'ice':b.module_snapshot.id,title:'SYNTHETIC · 已配对项目',scope:'SYNTHETIC',module_id:b.module_snapshot.id,module_version:b.module_snapshot.version,module_snapshot:b.module_snapshot,module_hash:b.local_module_hash.value,local_format_version:1}));
   await req(meta.add({id:'identity',workspace_id:crypto.randomUUID(),device_id:device.deviceId,scope:'SYNTHETIC_QA',authorization:'none'}));
   await req(meta.add({id:`binding:${b.semantic_project_id}`,state:'VERIFIED',generation:1,binding:canonicalBinding}));
   await req(meta.put({...saved,stage:'COMPLETE',resultDigest,manifestHead:trust.headDigest,principalMap:b.principal_map,helloSequence:0}));
  });
 }
}
