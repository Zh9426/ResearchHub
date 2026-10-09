import {revision,transactionDigest,validateTransaction,type SyncTransaction,type ChangeSet} from '../../../../packages/sync-protocol/src/browser';
import type {LocalOperation,Project} from '../local/model';
import {previewBinding,type PublicProjectBinding} from './binding';
import {businessTransaction,request,requireAuthorization} from './authorization';
import {applyRecord,emptyRecordState} from '../../../../packages/sync-protocol/src/record-kernel-core';
import {recordContext,type KernelRecord} from './receiver';
export type BindingRecord={id:string;state:'VERIFIED'|'TEST_ONLY'|'BLOCKED';generation:number;binding:PublicProjectBinding};
export type WireMapping={id:string;operation_id:string;object_id:string;operation_fingerprint?:string;prepare_id:string;prepare_token:string;adapter_version:1;transaction_id:string;change_id:string;audit_id:string;message_id:string;binding_generation:number;binding_fingerprint:string;parents:string[];dependencies:string[];base_revision:string|null;revision:string|null;transaction_digest:string|null;transaction:SyncTransaction|null;envelope:Uint8Array|null;envelope_digest?:string;security_blocked_reason?:string;conversion:'PREPARED'|'CONVERTED';transport:'BLOCKED'|'READY';peer:'UNCONFIRMED';review:'NOT_REQUESTED';source:LocalOperation['source']};
export type ReceivedBaseline={id:string;object_id:string;heads:string[];revisions:Record<string,unknown>[];cursor:number};
// Complete immutable revisions remain in record-kernel; this is only a baseline index.
export class WireBlocked extends Error{constructor(public reasons:string[]){super(`BLOCKED: ${reasons.join('; ')}`);}}
export function payloadFor(operation:LocalOperation,project:Project):Record<string,unknown>{
 const o=operation.payload;const common=['id','project_id','kind','local_format_version','local_edit_version','title'];
 const fields=o.kind==='Note'?['body']:['run_type','objective','observation','status','scientific_outcome','is_highlighted','highlight_type','highlight_note','context_data'];
 const reasons=Object.keys(o).filter(k=>![...common,...fields].includes(k)).map(k=>`payload.${k}: unknown field`);
 if(typeof o.title!=='string'||!o.title.trim()||Array.from(o.title).length>200)reasons.push('payload.title: nonblank, at most 200 Unicode code points required by PC Domain');
 if(o.kind==='Run')for(const [key,max] of [['highlight_type',100],['highlight_note',10000]] as const){if(typeof o[key]!=='string'||Array.from(o[key]).length>max)reasons.push(`payload.${key}: at most ${max} Unicode code points required by PC Domain`);}
 if(operation.object_id!==o.id)reasons.push('payload.id: operation object identity mismatch');
 if(operation.project_id!==o.project_id||o.project_id!==project.id)reasons.push('payload.project_id: operation/project identity mismatch');
 if(operation.object_type!==o.kind)reasons.push('payload.kind: operation object type mismatch');
 if(o.kind==='Run'){
  if(!project.module_snapshot.run_types.some(t=>t.id===o.run_type))reasons.push('payload.run_type: unknown module run_type');
  const schema=project.module_snapshot.context_fields as {id:string;value_type:string;required?:boolean}[]|undefined;
  const contextFields=Array.isArray(schema)?schema.filter(f=>f&&typeof f.id==='string'&&typeof f.value_type==='string'):[];
  if(Array.isArray(schema)&&contextFields.length!==schema.length)reasons.push('module_snapshot.context_fields: invalid field declaration');
  const forms=project.module_snapshot.run_forms as {run_type:string;groups:{fields:string[]}[]}[]|undefined;
  if(!Array.isArray(schema))reasons.push('module_snapshot.context_fields: unknown schema');
  if(forms!==undefined&&!Array.isArray(forms))reasons.push('module_snapshot.run_forms: unknown schema');
  let allowed:Set<string>|undefined;
  try{const matches=(forms??[]).filter(f=>f.run_type===o.run_type);allowed=matches.length?new Set(matches.flatMap(f=>f.groups.flatMap(g=>g.fields))):new Set(contextFields.map(f=>f.id));}catch{reasons.push('module_snapshot.run_forms: invalid groups/fields');}
  // Match Python json.dumps(ensure_ascii=False)'s default separators and code-point count.
  const keys=Object.keys(o.context_data),serializedLength=Array.from(JSON.stringify(o.context_data)).length+keys.length+Math.max(0,keys.length-1);
  if(serializedLength>65536)reasons.push('payload.context_data: exceeds Python workflow 65536 character limit');
  for(const [k,v] of Object.entries(o.context_data)){
   const field=contextFields.find(f=>f.id===k);
   if(!field)reasons.push(`payload.context_data.${k}: not defined in frozen module`);
   else if(!allowed?.has(k))reasons.push(`payload.context_data.${k}: not allowed for run_type ${o.run_type}`);
   else if(field.value_type!=='string'||typeof v!=='string')reasons.push(`payload.context_data.${k}: unsupported value type; local adapter supports string only`);
  }
  if(['running','completed'].includes(o.status))for(const field of contextFields){if(field.required&&allowed?.has(field.id)&&(o.context_data[field.id]===undefined||o.context_data[field.id]===null||o.context_data[field.id]===''))reasons.push(`payload.context_data.${field.id}: required before ${o.status}`);}

 }
 if(reasons.length)throw new WireBlocked(reasons);
 if(operation.operation_type==='highlight'&&o.kind==='Run')return {is_highlighted:o.is_highlighted,highlight_type:o.highlight_type,highlight_note:o.highlight_note};
 return o.kind==='Note'?{title:o.title,content:o.body}:Object.fromEntries(['title',...fields].map(k=>[k,(o as unknown as Record<string,unknown>)[k]]));
}
export class StableWireAdapter{
 constructor(private open:()=>Promise<IDBDatabase>,private testOnly=false){}
 private tx<T>(mode:IDBTransactionMode,work:(tx:IDBTransaction)=>Promise<T>){return businessTransaction(this.open,['meta','projects','operations'],mode,work);}
 async convert(operationId:string,hooks:{afterPrepared?:()=>Promise<void>;beforeCommit?:()=>Promise<void>;abortCommit?:boolean;commitGuard?:(tx:IDBTransaction)=>Promise<void>}={}):Promise<WireMapping>{
  const token=crypto.randomUUID();
  const snapshot=await this.tx('readonly',async tx=>{
   const s=tx.objectStore('meta'),operation=await request(tx.objectStore('operations').get(operationId)) as LocalOperation;
   if(!operation)throw new WireBlocked(['operation: missing']);
   const binding=await request(s.get('binding:'+operation.project_id)) as BindingRecord;
   if(!binding||(binding.state!=='VERIFIED'&&!(this.testOnly&&binding.state==='TEST_ONLY')))throw new WireBlocked(['authorization: TRUST_NOT_VERIFIED']);
   const authorization=await request(s.get('authorization:'+operation.project_id));if(!this.testOnly)requireAuthorization(authorization,binding);
   if(!['owner','writer'].includes(binding.binding.principal.role))throw new WireBlocked(['principal.role: read only']);
   return {operation,binding,authorization,project:await request(tx.objectStore('projects').get(operation.project_id)) as Project,
    mapping:await request(s.get('mapping:'+operationId)) as WireMapping|undefined,
    origin:await request(s.get('operation-base:'+operationId)),received:await request(s.get('received-heads:'+operation.object_id)),
    kernel:await request(s.get('record-kernel:'+operation.project_id)) as KernelRecord|undefined};
  });
  const {operation,binding,project,origin}=snapshot;if(!project||!origin)throw new WireBlocked(['operation: frozen source missing']);
  const operationFingerprint=JSON.stringify(operation);
  // Exact retries verify immutable source/identity before considering newer remote heads.
  if(snapshot.mapping?.conversion==='CONVERTED'){
   const m=snapshot.mapping;
   if(m.operation_fingerprint!==operationFingerprint||m.operation_id!==operation.id||m.object_id!==operation.object_id||m.prepare_id!==operation.id||m.binding_fingerprint!==JSON.stringify(binding)||m.binding_generation!==binding.generation||!m.transaction||m.transaction_digest!==await transactionDigest(m.transaction)||m.revision!==await revision(m.transaction.changes[0]))throw new WireBlocked(['IDENTITY_COLLISION: immutable operation or binding changed']);
   return m;
  }
  const preview=await previewBinding(binding.binding,project);if(preview.state==='BLOCKED')throw new WireBlocked(preview.reasons);
  const initial=snapshot.kernel?.state??emptyRecordState(project.id,binding.binding.module_snapshot_hash);
  const verifyBaseline=(value:any)=>{
   if(value===undefined||value===null)return;
   if(!value.verified||value.project_id!==project.id||value.object_id!==operation.object_id||!Array.isArray(value.heads)||!Array.isArray(value.revisions))throw new WireBlocked(['parents: saved baseline changed; unverified baseline']);
   for(const h of value.heads){const row=initial.revisions[h],known=value.revisions.find((r:any)=>r.revision===h);if(!row||!known||known.transaction_id!==row.semantic.transaction_id||JSON.stringify(known.semantic)!==JSON.stringify(row.semantic))throw new WireBlocked(['parents: saved baseline changed; unknown revision']);}
  };
  verifyBaseline(origin.received_heads);verifyBaseline(snapshot.received);
  let parent:{revision:string;transaction_id:string}|null=null;
  if(origin.predecessor_operation_id){
   const previous=await this.tx('readonly',tx=>request(tx.objectStore('meta').get('mapping:'+origin.predecessor_operation_id))) as WireMapping|undefined;
   if(previous?.conversion!=='CONVERTED'||previous.object_id!==operation.object_id||!previous.revision||!initial.revisions[previous.revision])throw new WireBlocked(['parents: predecessor must be converted first']);
   parent={revision:previous.revision,transaction_id:previous.transaction_id};
  }else if(origin.received_heads){
   const base=origin.received_heads;if(base.heads.length!==1||base.accepted_revision!==base.heads[0])throw new WireBlocked(['parents: accepted baseline required']);
   parent={revision:base.heads[0],transaction_id:initial.revisions[base.heads[0]].semantic.transaction_id};
  }
  if(operation.operation_type==='create'&&parent||operation.operation_type!=='create'&&!parent)throw new WireBlocked(['parents: BASELINE_REQUIRED']);
  const ids={transaction_id:crypto.randomUUID(),change_id:crypto.randomUUID(),audit_id:crypto.randomUUID(),message_id:crypto.randomUUID()};
  const prepared:WireMapping=snapshot.mapping?{...snapshot.mapping,prepare_token:token}:{id:'mapping:'+operationId,operation_id:operationId,object_id:operation.object_id,operation_fingerprint:operationFingerprint,prepare_id:operationId,prepare_token:token,adapter_version:1,...ids,binding_generation:binding.generation,binding_fingerprint:JSON.stringify(binding),parents:parent?[parent.revision]:[],dependencies:parent?[parent.transaction_id]:[],base_revision:parent?.revision??null,revision:null,transaction_digest:null,transaction:null,envelope:null,conversion:'PREPARED',transport:'BLOCKED',peer:'UNCONFIRMED',review:'NOT_REQUESTED',source:structuredClone(operation.source)};
  if(prepared.operation_fingerprint!==operationFingerprint||prepared.binding_fingerprint!==JSON.stringify(binding)||JSON.stringify(prepared.parents)!==JSON.stringify(parent?[parent.revision]:[]))throw new WireBlocked(['IDENTITY_COLLISION: preparation changed']);
  await this.tx('readwrite',async tx=>{await hooks.commitGuard?.(tx);const s=tx.objectStore('meta'),old=await request(s.get(prepared.id));if(JSON.stringify(old?{...old,prepare_token:null}:old)!==JSON.stringify(snapshot.mapping?{...snapshot.mapping,prepare_token:null}:snapshot.mapping))throw new WireBlocked(['CAS: preparation changed']);await request(s.put(prepared));});
  await hooks.afterPrepared?.();
  const change:ChangeSet={change_id:prepared.change_id,audit_id:prepared.audit_id,transaction_id:prepared.transaction_id,project_id:operation.project_id,device_id:binding.binding.principal.device_id,actor_id:binding.binding.principal.actor_id,actor_type:binding.binding.principal.actor_type,object_type:operation.object_type==='Run'?'ResearchRun':'Note',object_id:operation.object_id,operation:operation.operation_type==='create'?'create':'update',parents:prepared.parents,payload:payloadFor(operation,project),schema_version:2,module_snapshot_hash:binding.binding.module_snapshot_hash,created_at:operation.created_at};
  const transaction=validateTransaction({transaction_id:prepared.transaction_id,idempotency_key:prepared.transaction_id,project_id:change.project_id,device_id:change.device_id,actor_id:change.actor_id,actor_type:change.actor_type,protocol_version:2,schema_version:2,created_at:change.created_at,ordered_change_ids:[change.change_id],changes:[change],dependencies:prepared.dependencies});
  const staged=await applyRecord(initial,transaction,recordContext(binding,transaction));
  const final:WireMapping={...prepared,transaction,revision:await revision(change),transaction_digest:await transactionDigest(transaction),conversion:'CONVERTED'};
  await hooks.beforeCommit?.();
  return this.tx('readwrite',async tx=>{
   await hooks.commitGuard?.(tx);const s=tx.objectStore('meta'),current=await request(s.get(prepared.id)),now=await request(s.get(binding.id)),a=await request(s.get('authorization:'+project.id)),kernel=await request(s.get('record-kernel:'+project.id)),op=await request(tx.objectStore('operations').get(operation.id)),received=await request(s.get('received-heads:'+operation.object_id));
   if(!this.testOnly)requireAuthorization(a,now);
   if(current?.prepare_token!==token||current.conversion!=='PREPARED'||JSON.stringify(now)!==JSON.stringify(binding)||JSON.stringify(a)!==JSON.stringify(snapshot.authorization)||JSON.stringify(kernel)!==JSON.stringify(snapshot.kernel)||JSON.stringify(op)!==operationFingerprint||JSON.stringify(received)!==JSON.stringify(snapshot.received))throw new WireBlocked(['CAS: preparation, binding or heads changed']);
   await request(s.put(final));await request(s.put({id:'local-wire-heads:'+operation.object_id,revision:final.revision,transaction_id:final.transaction_id}));
   await request(s.put({id:'record-kernel:'+project.id,generation:(kernel?.generation??0)+1,state:staged.snapshot}));
   if(hooks.abortCommit)throw Error('TEST ONLY: conversion commit aborted');return final;
  });
 }
}
