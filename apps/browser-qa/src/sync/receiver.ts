/** Entire verified pages commit once. Kernel sequence and Relay cursor are distinct. */
import {canonicalBytes,strictLoads,digest,type SyncTransaction} from '../../../../packages/sync-protocol/src/browser';
import {applyRecord,emptyRecordState,type RecordState,type RecordContext} from '../../../../packages/sync-protocol/src/record-kernel-core';
import {fields,integer,type PublicObject} from '../../../../packages/secure-sync/src/membership-core';
import {extendChain} from '../../../../packages/secure-sync/src/checkpoint-core';
import type {BrowserVault} from '../../../../packages/secure-sync/src/vault-browser';
import {businessTransaction,request,requireAuthorization,type Authorization} from './authorization';
import type {BindingRecord} from './wire';
export type KernelRecord={id:string;generation:number;state:RecordState};
export function recordContext(binding:BindingRecord,tx:SyncTransaction):RecordContext{
 const b=binding.binding,p=b.principal_map.find(p=>p.device_id===tx.device_id);
 if(!p||!['owner','writer'].includes(p.role)||p.actor_id!==tx.actor_id||p.actor_type!==tx.actor_type)throw Error('ACTOR_CONTEXT_MISMATCH');
 return {project_id:b.semantic_project_id,module:b.module_snapshot as unknown as Record<string,unknown>,module_hash:b.module_snapshot_hash,mode:tx.changes.every(c=>c.operation==='resolve')?'offline_proposal':'online',principal:{principal_id:p.device_id,project_id:b.semantic_project_id,device_id:p.device_id,actor_id:p.actor_id,actor_type:p.actor_type,active:true}};
}
/** Kernel identities are typed. The current local stores are keyed only by UUID. */
function localIdentities(state:RecordState):Map<string,string>{
 const kinds=new Map<string,string>();
 for(const {semantic:c} of Object.values(state.revisions)){
  if(c.project_id!==state.project_id||!['Note','ResearchRun'].includes(c.object_type))throw Error('LOCAL_IDENTITY_UNREPRESENTABLE');
  const previous=kinds.get(c.object_id);if(previous&&previous!==c.object_type)throw Error('LOCAL_IDENTITY_UNREPRESENTABLE');
  kinds.set(c.object_id,c.object_type);
 }
 return kinds;
}
function checkLocalObject(old:any,project:string,kind:string){
 if(old&&(old.project_id!==project||old.kind!==(kind==='ResearchRun'?'Run':'Note')))throw Error('LOCAL_OBJECT_SCOPE_COLLISION');
}
/** Runs before any page/handoff writes, including when pending work is retained. */
async function checkLocalScopes(tx:IDBTransaction,state:RecordState){
 for(const [oid,kind] of localIdentities(state)){
  checkLocalObject(await request(tx.objectStore('objects').get(oid)),state.project_id,kind);
  const meta=tx.objectStore('meta'),baseline=await request(meta.get('received-heads:'+oid));
  if(baseline?.project_id&&baseline.project_id!==state.project_id)throw Error('LOCAL_OBJECT_SCOPE_COLLISION');
  const pending=await request(meta.get('pending-operation:'+oid));
  if(pending){const op=await request(tx.objectStore('operations').get(pending.operation_id));if(!op||op.project_id!==state.project_id||op.object_type!==(kind==='ResearchRun'?'Run':'Note'))throw Error('LOCAL_OBJECT_SCOPE_COLLISION');}
 }
}
export function verifiedBaseline(state:RecordState,objectId:string,generation:number,cursor:number){
 const kind=localIdentities(state).get(objectId),entries=Object.entries(state.revisions).filter(([,r])=>r.semantic.object_id===objectId);
 return {id:'received-heads:'+objectId,object_id:objectId,project_id:state.project_id,verified:true,kernel_generation:generation,heads:kind?state.heads[kind+':'+objectId]??[]:[],accepted_revision:kind?state.projections[kind+':'+objectId]??null:null,revisions:entries.map(([revision,row])=>({revision,transaction_id:row.semantic.transaction_id,semantic:row.semantic})),cursor};
}
/** LocalObject is the existing narrow UI DTO; full documents remain in immutable Kernel. */
async function projectObject(tx:IDBTransaction,state:RecordState,oid:string){
 const kind=localIdentities(state).get(oid);if(!kind)return;
 const rev=state.projections[kind+':'+oid],row=rev?state.revisions[rev]:null,objects=tx.objectStore('objects'),old=await request(objects.get(oid));
 checkLocalObject(old,state.project_id,kind);
 if(!row||row.lifecycle!=='active'){await request(objects.delete(oid));return;}
 const d=row.document,base={id:oid,project_id:state.project_id,kind:kind==='Note'?'Note':'Run',local_format_version:1,local_edit_version:(old?.local_edit_version??0)+1,title:d.title};
 const object=kind==='Note'?{...base,body:d.content??''}:{...base,run_type:d.run_type,objective:d.objective??'',observation:d.observation??'',status:d.status??'planned',scientific_outcome:d.scientific_outcome??'unknown',is_highlighted:d.is_highlighted??false,highlight_type:d.highlight_type??'',highlight_note:d.highlight_note??'',context_data:d.context_data??{}};
 // Echo and unrelated pages do not manufacture new editor versions.
 const stable=(v:any)=>new TextDecoder().decode(canonicalBytes({...v,local_edit_version:0}));
 if(!old||stable(old)!==stable(object))await request(objects.put(object));
}
export class PageReceiver{
 constructor(private open:()=>Promise<IDBDatabase>,private vault:BrowserVault){}
 /** Called only after a durable verified transport handoff, with its frozen identity. */
 async completeHandoff(operationId:string,transactionId:string,version:number,commitGuard?:(tx:IDBTransaction)=>Promise<void>){
  return businessTransaction(this.open,['meta','operations','objects'],'readwrite',async tx=>{
   await commitGuard?.(tx);
   const s=tx.objectStore('meta'),op=await request(tx.objectStore('operations').get(operationId)),mapping=await request(s.get('mapping:'+operationId));
   if(!op||mapping?.conversion!=='CONVERTED'||mapping.transaction_id!==transactionId||op.payload.local_edit_version!==version)throw Error('HANDOFF_IDENTITY_MISMATCH');
   const pending=await request(s.get('pending-operation:'+op.object_id));
   if(pending?.operation_id!==operationId||pending.local_edit_version!==version)return false;
   const kernel=await request(s.get('record-kernel:'+op.project_id)) as KernelRecord|undefined,cursor=await request(s.get('relay-cursor:'+op.project_id));
   if(!kernel?.state.transactions[transactionId])throw Error('HANDOFF_KERNEL_MISSING');
   await checkLocalScopes(tx,kernel.state);
   await request(s.delete(pending.id));await request(s.put({id:'handoff:'+operationId,operation_id:operationId,transaction_id:transactionId,local_edit_version:version}));
   await request(s.put(verifiedBaseline(kernel.state,op.object_id,kernel.generation,cursor?.cursor??0)));await projectObject(tx,kernel.state,op.object_id);return true;
  });
 }
 async receive(project:string,input:unknown,hooks:{beforeCommit?:()=>Promise<void>;abortCommit?:boolean;commitGuard?:(tx:IDBTransaction)=>Promise<void>}={}){
  const bytes=canonicalBytes(input);if(bytes.length>26*1024*1024)throw Error('PAGE_TOO_LARGE');
  const page=strictLoads(bytes) as PublicObject;fields(page,['rows','cursor','chain_digest','has_more']);integer(page.cursor);
  if(!Array.isArray(page.rows)||page.rows.length>100||typeof page.has_more!=='boolean'||(!page.rows.length&&page.has_more))throw Error('INVALID_PAGE');
  const snapshot=await businessTransaction(this.open,['meta'],'readonly',async tx=>{
   const s=tx.objectStore('meta'),a=await request(s.get('authorization:'+project)) as Authorization,b=await request(s.get('binding:'+project)) as BindingRecord;
   requireAuthorization(a,b);return {a,b,kernel:await request(s.get('record-kernel:'+project)) as KernelRecord|undefined,cursor:await request(s.get('relay-cursor:'+project))};
  });
  const {a,b}=snapshot,vaultTrust=await this.vault.trust(b.binding.opaque_project_id);
  if(vaultTrust.headDigest!==a.head||vaultTrust.membershipEpoch!==a.membership_epoch||vaultTrust.keyEpoch!==a.key_epoch)throw Error('VAULT_AUTHORIZATION_MISMATCH');
  if(await digest(b.binding.principal_map)!==a.principal_map_digest)throw Error('PRINCIPAL_MAP_MISMATCH');
  let cursor=snapshot.cursor?.cursor??0,chain=snapshot.cursor?.chain_digest??'0'.repeat(64),state=snapshot.kernel?.state??emptyRecordState(project,b.binding.module_snapshot_hash);
  if(page.cursor!==cursor+page.rows.length)throw Error('CURSOR_GAP');
  const receipts:PublicObject[]=[],seen=new Set<string>();
  for(const item of page.rows){
   fields(item,['sequence','envelope_digest','chain_digest','envelope']);integer(item.sequence,1);
   if(item.sequence!==cursor+1||await digest(item.envelope)!==item.envelope_digest)throw Error('PAGE_BINDING_MISMATCH');
   chain=await extendChain(chain,cursor,[{sequence:item.sequence,envelope_digest:item.envelope_digest}]);if(chain!==item.chain_digest)throw Error('CHAIN_DIGEST_MISMATCH');
   const env=item.envelope;if(seen.has(env.message_id))throw Error('DUPLICATE_MESSAGE');seen.add(env.message_id);
   if(env.membership_epoch!==a.membership_epoch||env.key_epoch!==a.key_epoch)throw Error('HISTORICAL_OR_UNKNOWN_EPOCH_BLOCKED');
   const transaction=await this.vault.openTransaction(env,project) as SyncTransaction;
   const applied=await applyRecord(state,transaction,recordContext(b,transaction));state=applied.snapshot;
   receipts.push({id:`received:${project}:${item.sequence}`,project_id:project,sequence:item.sequence,chain_digest:chain,envelope_digest:item.envelope_digest,envelope:item.envelope,transaction_id:transaction.transaction_id,semantic_transaction_digest:env.semantic_transaction_digest,message_id:env.message_id,sender_device_id:env.sender_device_id,membership_epoch:env.membership_epoch,key_epoch:env.key_epoch,manifest_digest:a.head,receipt:applied.receipt,stage:'KERNEL_APPLIED'});cursor++;
  }
  if(chain!==page.chain_digest)throw Error('CHAIN_DIGEST_MISMATCH');
  localIdentities(state);
  await hooks.beforeCommit?.();
  return businessTransaction(this.open,['meta','objects','operations'],'readwrite',async tx=>{
   await hooks.commitGuard?.(tx);
   const s=tx.objectStore('meta'),now=await request(s.get(a.id)),binding=await request(s.get(b.id)),kernel=await request(s.get('record-kernel:'+project)),oldCursor=await request(s.get('relay-cursor:'+project));
   requireAuthorization(now,binding);
   if(JSON.stringify(now)!==JSON.stringify(a)||JSON.stringify(binding)!==JSON.stringify(b)||JSON.stringify(kernel)!==JSON.stringify(snapshot.kernel)||JSON.stringify(oldCursor)!==JSON.stringify(snapshot.cursor))throw Error('RECEIVE_CAS_MISMATCH');
   await checkLocalScopes(tx,state);
   const generation=(kernel?.generation??0)+1;
   for(const receipt of receipts){if(await request(s.get(receipt.id)))throw Error('RECEIVED_IDENTITY_COLLISION');await request(s.add(receipt));}
   await request(s.put({id:'record-kernel:'+project,generation,state}));
   for(const oid of new Set(Object.values(state.revisions).map(r=>r.semantic.object_id))){
    await request(s.put(verifiedBaseline(state,oid,generation,cursor)));
    // Pending work is a separate local branch; no received page rewrites it.
    if(await request(s.get('pending-operation:'+oid)))continue;
    await projectObject(tx,state,oid);
   }
   await request(s.put({id:'relay-cursor:'+project,cursor,chain_digest:chain}));if(hooks.abortCommit)throw Error('TEST_ONLY_RECEIVE_ABORT');
   return {cursor,chain_digest:chain,receipts:receipts.map(r=>r.receipt),kernel_sequence:state.sequence};
  });
 }
}
