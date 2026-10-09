import {canonicalBytes,strictLoads,digest} from '../../../../packages/sync-protocol/src/browser';
import {businessTransaction,request,requireAuthorization} from './authorization';
import {WireSealer} from './seal';
import {StableWireAdapter} from './wire';
import {receiptBody,verifyPeerReceipt} from '../../../../packages/secure-sync/src/peer-receipt';
import {preimage,fields,integer,type PublicObject} from '../../../../packages/secure-sync/src/membership-core';
import {sign} from '../../../../packages/secure-sync/src/crypto-web';
import {b64encode,equal} from '../../../../packages/secure-sync/src/binary';
import {relayFetch} from '../../../../packages/secure-sync/src/request-browser';
/** Explicit, bounded, durable manual work. No automatic retries or background loops. */
export class ManualSync{
 readonly sealer:WireSealer;
 constructor(private open:()=>Promise<IDBDatabase>){this.sealer=new WireSealer(open);}
 private tx<T>(mode:IDBTransactionMode,fn:(tx:IDBTransaction)=>Promise<T>){return businessTransaction(this.open,['meta','operations'],'readwrite'===mode?'readwrite':'readonly',fn);}
 async claim(project:string){return this.tx('readwrite',async tx=>{
  const s=tx.objectStore('meta'),a=await request(s.get('authorization:'+project)),b=await request(s.get('binding:'+project));requireAuthorization(a,b);
  const id='manual-claim:'+project,old=await request(s.get(id));if(old?.expires>Date.now())throw Error('MANUAL_SYNC_BUSY');
  const token=crypto.randomUUID();await request(s.put({id,token,expires:Date.now()+120000,generation:a.generation,head:a.head}));return token;
 });}
 async checkIn(tx:IDBTransaction,project:string,token:string){
  const s=tx.objectStore('meta'),a=await request(s.get('authorization:'+project)),b=await request(s.get('binding:'+project));requireAuthorization(a,b);
  const c=await request(s.get('manual-claim:'+project));if(!c||c.token!==token||c.expires<=Date.now())throw Error('MANUAL_CLAIM_LOST');
  if(c.generation!==a.generation||c.head!==a.head)throw Error('AUTHORIZATION_CHANGED');
  if(tx.mode==='readwrite')await request(s.put({...c,expires:Date.now()+120000}));
 }
 async check(project:string,token:string){return this.tx('readwrite',tx=>this.checkIn(tx,project,token));}
 async release(project:string,token:string){return this.tx('readwrite',async tx=>{const s=tx.objectStore('meta'),c=await request(s.get('manual-claim:'+project));if(c?.token===token)await request(s.put({...c,expires:0}));});}
 private async authorization(project:string){
  const snapshot=await this.tx('readonly',async tx=>{const s=tx.objectStore('meta'),a=await request(s.get('authorization:'+project)),b=await request(s.get('binding:'+project));requireAuthorization(a,b);return {a,b};});
  const vault=await this.sealer.vault(),trust=await vault.trust(snapshot.b.binding.opaque_project_id);
  if(trust.headDigest!==snapshot.a.head||trust.membershipEpoch!==snapshot.a.membership_epoch||trust.keyEpoch!==snapshot.a.key_epoch)throw Error('VAULT_AUTHORIZATION_MISMATCH');
  return {...snapshot,vault,trust,device:await vault.device()};
 }
 async preparePeerReceipt(project:string,sequence:number,token?:string):Promise<Uint8Array>{
  const auth=await this.authorization(project),id=`signed-receipt:${project}:${sequence}`;
  const snapshot=await this.tx('readonly',async tx=>{if(token)await this.checkIn(tx,project,token);const s=tx.objectStore('meta');return {row:await request(s.get(`received:${project}:${sequence}`)),saved:await request(s.get(id))};});
  const r=snapshot.row;if(!r||r.stage!=='KERNEL_APPLIED'||!['ACCEPTED','CANDIDATE'].includes(r.receipt?.state))throw Error('DURABLE_RECEIPT_REQUIRED');
  if(r.manifest_digest!==auth.a.head)throw Error('HISTORICAL_EPOCH_BLOCKED');
  const manifest=auth.trust.chain.at(-1)!;
  const body=await receiptBody(manifest,r.envelope,sequence,auth.device.deviceId,r.receipt.state);
  const value=snapshot.saved?strictLoads(snapshot.saved.raw) as PublicObject:{...body,signature:b64encode(await sign(auth.device.signing.privateKey,preimage('PeerApplyReceipt',body)))};
  await verifyPeerReceipt(value,manifest,r.envelope,sequence,auth.device.deviceId);const raw=canonicalBytes(value);
  return this.tx('readwrite',async tx=>{
   if(token)await this.checkIn(tx,project,token);const s=tx.objectStore('meta'),a=await request(s.get(auth.a.id)),b=await request(s.get(auth.b.id));requireAuthorization(a,b);
   if(JSON.stringify(a)!==JSON.stringify(auth.a)||JSON.stringify(await request(s.get(r.id)))!==JSON.stringify(r))throw Error('RECEIPT_CAS');
   const old=await request(s.get(id));if(old&&!equal(old.raw,raw))throw Error('PEER_RECEIPT_CHANGED');
   if(!old)await request(s.add({id,raw}));return Uint8Array.from(old?.raw??raw);
  });
 }
 async cycle(project:string){
  const token=await this.claim(project);let sent=0,received=0,confirmed=0,more=false,unfinished=false;let primary:unknown;
  try{
   const auth=await this.authorization(project),target=auth.b.binding.trust.manifest_chain.at(-1)!.authority_device_id as string;
   if(target===auth.device.deviceId)throw Error('EXACT_PEER_TARGET_REQUIRED');
   const check=(tx?:IDBTransaction)=>tx?this.checkIn(tx,project,token):this.check(project,token);
   const send=async(method:'GET'|'POST',path:string,query:PublicObject={},body?:unknown)=>{
    await check();const result=await relayFetch(auth.device,auth.trust,method,path,query,body);await check();return result;
   };
   const receiver=await this.sealer.receiver(),wire=new StableWireAdapter(this.open);
   const pull=async()=>{
    const cursor=await this.tx('readonly',tx=>request(tx.objectStore('meta').get('relay-cursor:'+project)));
    const page=await send('GET','/v1/messages',{cursor:cursor?.cursor??0,limit:100});
    await receiver.receive(project,page,{commitGuard:check});received+=page.rows.length;return page.has_more as boolean;
   };
   more=await pull();
   const operations=await this.tx('readonly',async tx=>{
    const s=tx.objectStore('meta'),ops=(await request(tx.objectStore('operations').getAll())).filter(o=>o.project_id===project);
    const pending=[];for(const op of ops)if(!await request(s.get('peer-confirmed:'+op.id))||(await request(s.get('pending-operation:'+op.object_id)))?.operation_id===op.id)pending.push(op);
    const ordered=[];const todo=new Map(pending.map(op=>[op.id,op]));
    while(todo.size){let progress=false;for(const op of [...todo.values()].sort((a,b)=>a.payload.local_edit_version-b.payload.local_edit_version)){
     const base=await request(s.get('operation-base:'+op.id));if(!base)throw Error('OPERATION_BASE_REQUIRED');
     if(base.predecessor_operation_id&&todo.has(base.predecessor_operation_id))continue;
     ordered.push(op);todo.delete(op.id);progress=true;
    }if(!progress)throw Error('OPERATION_DEPENDENCY_CYCLE');}return ordered;
   });
   const sendQueue=await this.tx('readonly',async tx=>{const s=tx.objectStore('meta'),queue=[];for(const op of operations)if(!await request(s.get('relay-stored:'+op.id)))queue.push(op);return queue;});
   unfinished=sendQueue.length>16||operations.length>100;
   if(!more){
    for(const op of sendQueue.slice(0,16)){
     await check();const mapping=await wire.convert(op.id,{commitGuard:check});await check();await this.sealer.seal(op.id,check);await check();
     const raw=await this.sealer.ready(op.id,check),env=strictLoads(raw) as PublicObject;
     const result=await send('POST','/v1/messages',{}, {envelopes:[env]});fields(result,['receipts']);
     if(!Array.isArray(result.receipts)||result.receipts.length!==1)throw Error('RELAY_RECEIPT_MISMATCH');
     const ack=result.receipts[0];fields(ack,['stage','message_id','sequence','envelope_digest','chain_digest']);integer(ack.sequence,1);
     if(ack.stage!=='RELAY_STORED'||ack.message_id!==mapping.message_id||ack.envelope_digest!==await digest(env))throw Error('RELAY_RECEIPT_MISMATCH');
     await this.tx('readwrite',async tx=>{await check(tx);const s=tx.objectStore('meta'),id='relay-stored:'+op.id,old=await request(s.get(id));if(old&&JSON.stringify(old.receipt)!==JSON.stringify(ack))throw Error('RELAY_RECEIPT_CHANGED');await request(s.put({id,receipt:ack}));});sent++;
    }
    more=await pull();
   }
   const rows=await this.tx('readonly',tx=>request(tx.objectStore('meta').getAll()));
   const receiptQueue=rows.filter(r=>r.id.startsWith('received:'+project+':')&&r.sender_device_id!==auth.device.deviceId&&r.manifest_digest===auth.a.head&&!rows.some(x=>x.id===`receipt-published:${project}:${r.sequence}`)).sort((a,b)=>a.sequence-b.sequence);
   unfinished ||= receiptQueue.length>100;
   for(const r of receiptQueue.slice(0,100)){
    await check();const raw=await this.preparePeerReceipt(project,r.sequence,token);const result=await send('POST','/v1/peer-receipts',{},strictLoads(raw));
    if(!equal(canonicalBytes(result),raw))throw Error('PEER_RECEIPT_RELAY_MISMATCH');
    await this.tx('readwrite',async tx=>{await check(tx);const s=tx.objectStore('meta'),saved=await request(s.get(`signed-receipt:${project}:${r.sequence}`));if(!saved||!equal(saved.raw,raw))throw Error('PEER_RECEIPT_CHANGED');await request(s.put({id:`receipt-published:${project}:${r.sequence}`,raw}));});
   }
   for(const op of operations.slice(0,100)){
    const snapshot=await this.tx('readonly',async tx=>{const s=tx.objectStore('meta');return {mapping:await request(s.get('mapping:'+op.id)),relay:await request(s.get('relay-stored:'+op.id))};});
    if(!snapshot.mapping?.envelope||!snapshot.relay)continue;
    const result=await send('GET','/v1/peer-receipts',{message_id:snapshot.mapping.message_id,target_device_id:target});fields(result,['receipt']);if(result.receipt===null){unfinished=true;continue;}
    const env=strictLoads(snapshot.mapping.envelope) as PublicObject;
    const value=await verifyPeerReceipt(result.receipt,auth.trust.chain.at(-1)!,env,snapshot.relay.receipt.sequence,target),raw=canonicalBytes(value);
    await this.tx('readwrite',async tx=>{
     await check(tx);const s=tx.objectStore('meta'),m=await request(s.get('mapping:'+op.id)),r=await request(s.get('relay-stored:'+op.id));
     if(!equal(m.envelope,snapshot.mapping.envelope)||JSON.stringify(r)!==JSON.stringify(snapshot.relay))throw Error('PEER_RECEIPT_CAS');
     const id='peer-confirmed:'+op.id,old=await request(s.get(id));if(old&&!equal(old.raw,raw))throw Error('PEER_RECEIPT_CHANGED');await request(s.put({id,raw,target,transaction_id:m.transaction_id,version:op.payload.local_edit_version}));
    });
    await receiver.completeHandoff(op.id,snapshot.mapping.transaction_id,op.payload.local_edit_version,check);confirmed++;
   }
   return {sent,received,confirmed,has_more:more||unfinished,peer:confirmed?'VERIFIED':'UNCONFIRMED',review:'NOT_REQUESTED'};
  }catch(error){primary=error;throw error;}finally{try{await this.release(project,token);}catch(cleanup){throw primary?new AggregateError([primary,cleanup],'SYNC_AND_CLEANUP_FAILED'):cleanup;}}
 }

 async recordStatus(project:string,objectId:string){
  const saved=await this.tx('readonly',async tx=>({rows:await request(tx.objectStore('meta').getAll()),ops:await request(tx.objectStore('operations').getAll())}));
  const row=(id:string)=>saved.rows.find(r=>r.id===id),ops=saved.ops.filter(o=>o.project_id===project&&o.object_id===objectId).sort((a,b)=>b.payload.local_edit_version-a.payload.local_edit_version),op=ops[0];
  const state=row('record-kernel:'+project)?.state,kind=op?(op.object_type==='Run'?'ResearchRun':'Note'):Object.values(state?.revisions??{}).find((r:any)=>r.semantic.object_id===objectId) as any;
  const typed=typeof kind==='string'?kind:kind?.semantic.object_type,key=typed+':'+objectId,heads=state?.heads[key]??[];
  const value={object_id:objectId,operation_id:op?.id??null,transaction_id:null as string|null,local_version:op?.payload.local_edit_version??null,local:op?'SAVED':'REMOTE_ONLY',conversion:op?'NOT_CONVERTED':'NOT_APPLICABLE',transport:op?'NOT_SENT':'NOT_APPLICABLE',peer:'UNCONFIRMED',target_device_id:null as string|null,review:'NOT_REQUESTED',current_record:heads.length>1?'CONFLICTED':state?.projections[key]?'ACCEPTED':heads.length?'CANDIDATE':'UNKNOWN',state_at_commit:null as string|null};
  const a=row('authorization:'+project),b=row('binding:'+project);
  if(!a||a.state!=='READY'||!b){if(op){value.conversion='BLOCKED';value.transport='BLOCKED';}return value;}
  const auth=await this.authorization(project);if(JSON.stringify(auth.a)!==JSON.stringify(a))throw Error('STATUS_AUTHORIZATION_CHANGED');
  const target=auth.trust.chain.at(-1)!.authority_device_id as string;value.target_device_id=target;
  if(!op)return value;
  const mapping=row('mapping:'+op.id);if(!mapping)return value;
  if(mapping.operation_id!==op.id||mapping.operation_fingerprint!==JSON.stringify(op))throw Error('STATUS_OPERATION_MISMATCH');
  value.transaction_id=mapping.transaction_id;value.conversion=mapping.transport==='BLOCKED'&&mapping.security_blocked_reason?'BLOCKED':mapping.envelope?'SEALED':mapping.conversion;
  if(mapping.binding_fingerprint!==JSON.stringify(b)){value.conversion='BLOCKED';value.transport='BLOCKED';return value;}
  const relay=row('relay-stored:'+op.id);if(!relay||!mapping.envelope)return value;
  const env=strictLoads(mapping.envelope) as PublicObject,ack=relay.receipt;
  if(env.message_id!==mapping.message_id||env.semantic_transaction_digest!==mapping.transaction_digest||ack.message_id!==mapping.message_id||ack.envelope_digest!==await digest(env)||ack.stage!=='RELAY_STORED')throw Error('STATUS_RELAY_MISMATCH');
  integer(ack.sequence,1);value.transport='RELAY_STORED';
  const peer=row('peer-confirmed:'+op.id);
  if(peer){
   if(peer.target!==target||peer.transaction_id!==mapping.transaction_id||peer.version!==op.payload.local_edit_version)throw Error('STATUS_PEER_MISMATCH');
   const receipt=await verifyPeerReceipt(strictLoads(peer.raw) as PublicObject,auth.trust.chain.at(-1)!,env,ack.sequence,target);
   value.peer='VERIFIED';value.state_at_commit=receipt.state_at_commit;
  }
  return value;
 }

}
