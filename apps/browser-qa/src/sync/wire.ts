import {revision,transactionDigest,validateTransaction,type SyncTransaction,type ChangeSet} from '../../../../packages/sync-protocol/src/browser';
import type {LocalOperation,Project} from '../local/model';
import {previewBinding,type PublicProjectBinding} from './binding';
export type BindingRecord={id:string;state:'VERIFIED'|'TEST_ONLY';generation:number;binding:PublicProjectBinding};
export type WireMapping={id:string;operation_id:string;object_id:string;prepare_id:string;prepare_token:string;adapter_version:1;transaction_id:string;change_id:string;audit_id:string;message_id:string;binding_generation:number;binding_fingerprint:string;parents:string[];dependencies:string[];base_revision:string|null;revision:string|null;transaction_digest:string|null;transaction:SyncTransaction|null;envelope:Uint8Array|null;envelope_digest?:string;security_blocked_reason?:string;conversion:'PREPARED'|'CONVERTED';transport:'BLOCKED'|'READY';peer:'UNCONFIRMED';review:'NOT_REQUESTED';source:LocalOperation['source']};
export type ReceivedBaseline={id:string;object_id:string;heads:string[];revisions:Record<string,unknown>[];cursor:number};
// Receiver must atomically commit verified pages + heads + cursor; never replace objects/drafts/pending.
// Receiver implementation and offline_proposal remain NOT IMPLEMENTED in this boundary.
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
 private async transaction<T>(work:(tx:IDBTransaction,finish:(value:T)=>void,fail:(e:Error)=>void)=>void):Promise<T>{
  const db=await this.open();return new Promise((resolve,reject)=>{const tx=db.transaction(['meta','projects','operations'],'readwrite');let result:T,error:Error|undefined;tx.oncomplete=()=>{db.close();resolve(result);};tx.onabort=()=>{db.close();reject(error??tx.error??Error('IDB aborted'));};work(tx,v=>{result=v;},e=>{error=e;tx.abort();});});
 }
 async convert(operationId:string,hooks:{afterPrepared?:()=>Promise<void>;beforeCommit?:()=>Promise<void>;abortCommit?:boolean}={}):Promise<WireMapping>{
  const ids={transaction_id:crypto.randomUUID(),change_id:crypto.randomUUID(),audit_id:crypto.randomUUID(),message_id:crypto.randomUUID()},token=crypto.randomUUID();
  const prepared=await this.transaction<{mapping:WireMapping;operation:LocalOperation;project:Project;binding:BindingRecord;head:unknown;received:unknown} >((tx,finish,fail)=>{
   const opReq=tx.objectStore('operations').get(operationId);opReq.onsuccess=()=>{
    const operation=opReq.result as LocalOperation;if(!operation){fail(new WireBlocked(['operation: missing']));return;}
    const reqs=[tx.objectStore('meta').get(`binding:${operation.project_id}`),tx.objectStore('meta').get(`mapping:${operationId}`),tx.objectStore('meta').get(`local-wire-heads:${operation.object_id}`),tx.objectStore('projects').get(operation.project_id),tx.objectStore('operations').getAll(),tx.objectStore('meta').get(`operation-base:${operationId}`),tx.objectStore('meta').get(`received-heads:${operation.object_id}`)];let count=reqs.length;
    for(const r of reqs)r.onsuccess=()=>{if(--count)return;const [binding,old,head,project,ops,origin,received]=reqs.map(x=>x.result) as [BindingRecord,WireMapping|undefined,{revision:string;transaction_id:string}|undefined,Project,LocalOperation[],{received_heads:unknown}|undefined,unknown];
     if(!binding||(binding.state!=='VERIFIED'&&!(this.testOnly&&binding.state==='TEST_ONLY'))){fail(new WireBlocked(['authorization: TRUST_NOT_VERIFIED']));return;}
     if(!origin||JSON.stringify(origin.received_heads)!==JSON.stringify(received??null)){fail(new WireBlocked(['parents: saved baseline changed; explicit reconciliation required']));return;}
     if(!['owner','writer'].includes(binding.binding.principal.role)){fail(new WireBlocked(['principal.role: read only']));return;}
     if(!project){fail(new WireBlocked(['project: missing']));return;}
     if(old?.conversion==='CONVERTED'){finish({mapping:old,operation,project,binding,head,received});return;}
     const predecessors=ops.filter(x=>x.object_id===operation.object_id&&x.payload.local_edit_version<operation.payload.local_edit_version).sort((a,b)=>b.payload.local_edit_version-a.payload.local_edit_version);
     const complete=()=>{
      if(operation.operation_type!=='create'&&!head){fail(new WireBlocked(['parents: BASELINE_REQUIRED']));return;}
      if(operation.operation_type==='create'&&head){fail(new WireBlocked(['parents: create already has head']));return;}
      const mapping:WireMapping=old?{...old,prepare_token:token}:{id:`mapping:${operationId}`,operation_id:operationId,object_id:operation.object_id,prepare_id:operationId,prepare_token:token,adapter_version:1,...ids,binding_generation:binding.generation,binding_fingerprint:JSON.stringify(binding),parents:head?[head.revision]:[],dependencies:head?[head.transaction_id]:[],base_revision:head?.revision??null,revision:null,transaction_digest:null,transaction:null,envelope:null,conversion:'PREPARED',transport:'BLOCKED',peer:'UNCONFIRMED',review:'NOT_REQUESTED',source:structuredClone(operation.source)};
      if(JSON.stringify(mapping.parents)!==JSON.stringify(head?[head.revision]:[])||mapping.binding_fingerprint!==JSON.stringify(binding)){fail(new WireBlocked(['binding: changed since preparation']));return;}
      tx.objectStore('meta').put(mapping);finish({mapping,operation,project,binding,head,received});
     };
     if(predecessors[0]){const prev=tx.objectStore('meta').get(`mapping:${predecessors[0].id}`);prev.onsuccess=()=>{if(prev.result?.conversion!=='CONVERTED'||head?.revision!==prev.result.revision){fail(new WireBlocked(['parents: predecessor must be converted first']));return;}complete();};}else complete();
    };
   };
  });
  if(prepared.mapping.conversion==='CONVERTED')return prepared.mapping;
  await hooks.afterPrepared?.();
  const {mapping,operation,project,binding}=prepared;
  const preview=await previewBinding(binding.binding,project);if(preview.state==='BLOCKED')throw new WireBlocked(preview.reasons);
  const change:ChangeSet={change_id:mapping.change_id,audit_id:mapping.audit_id,transaction_id:mapping.transaction_id,project_id:operation.project_id,device_id:binding.binding.principal.device_id,actor_id:binding.binding.principal.actor_id,actor_type:binding.binding.principal.actor_type,object_type:operation.object_type==='Run'?'ResearchRun':'Note',object_id:operation.object_id,operation:operation.operation_type==='create'?'create':'update',parents:mapping.parents,payload:payloadFor(operation,project),schema_version:2,module_snapshot_hash:binding.binding.module_snapshot_hash,created_at:operation.created_at};
  const transaction=validateTransaction({transaction_id:mapping.transaction_id,idempotency_key:mapping.transaction_id,project_id:change.project_id,device_id:change.device_id,actor_id:change.actor_id,actor_type:change.actor_type,protocol_version:2,schema_version:2,created_at:change.created_at,ordered_change_ids:[change.change_id],changes:[change],dependencies:mapping.dependencies});
  const final:WireMapping={...mapping,transaction,revision:await revision(change),transaction_digest:await transactionDigest(transaction),conversion:'CONVERTED'};
  await hooks.beforeCommit?.();
  return this.transaction((tx,finish,fail)=>{const reqs=[tx.objectStore('meta').get(mapping.id),tx.objectStore('meta').get(binding.id),tx.objectStore('meta').get(`local-wire-heads:${operation.object_id}`),tx.objectStore('meta').get(`received-heads:${operation.object_id}`)];let count=reqs.length;for(const r of reqs)r.onsuccess=()=>{if(--count)return;const [current,now,head,received]=reqs.map(r=>r.result);if(current?.prepare_token!==token||current.conversion!=='PREPARED'||JSON.stringify(now)!==JSON.stringify(binding)||JSON.stringify(head)!==JSON.stringify(prepared.head)||JSON.stringify(received)!==JSON.stringify(prepared.received)){fail(new WireBlocked(['CAS: preparation, binding or heads changed']));return;}tx.objectStore('meta').put(final);tx.objectStore('meta').put({id:`local-wire-heads:${operation.object_id}`,revision:final.revision,transaction_id:final.transaction_id});if(hooks.abortCommit){fail(Error('TEST ONLY: conversion commit aborted'));return;}finish(final);};});
 }
}
