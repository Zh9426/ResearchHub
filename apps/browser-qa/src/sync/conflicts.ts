import {commonBase,applyRecord,type RecordState} from '../../../../packages/sync-protocol/src/record-kernel-core';
import {revision,transactionDigest,validateTransaction} from '../../../../packages/sync-protocol/src/browser';
import {businessTransaction,request,requireAuthorization} from './authorization';
import {recordContext,type KernelRecord} from './receiver';
import {payloadFor,type BindingRecord,type WireMapping} from './wire';
import type {LocalObject,LocalOperation,Project} from '../local/model';
export type ConflictDocument=Record<string,unknown>;
export type ConflictRecord={object_id:string;object_type:string;local_device_id:string;work:{document:ConflictDocument;version:number;pending:boolean}|null;trusted:{status:string;heads:string[];base:ConflictDocument|null;base_revision:string|null;accepted:ConflictDocument|null;candidates:{revision:string;transaction_id:string;device_id:string;document:ConflictDocument;state:string}[]};audit:unknown[];pending:unknown;cas:unknown};
export type ConflictService={list:(project:string)=>Promise<ConflictRecord[]>;resolve:(record:ConflictRecord,document:ConflictDocument)=>Promise<void>};
/** A proposal must include the saved local predecessor, never overtake it. */
async function requireComparedPredecessor(tx:IDBTransaction,pending:any,kernel:KernelRecord,heads:string[],project:string,objectId:string){
 if(!pending)return;
 const operation=await request(tx.objectStore('operations').get(pending.operation_id)) as LocalOperation|undefined;
 const mapping=await request(tx.objectStore('meta').get('mapping:'+pending.operation_id)) as WireMapping|undefined;
 const row=mapping?.revision?kernel.state.revisions[mapping.revision]:undefined;
 if(!operation||operation.project_id!==project||operation.object_id!==objectId||operation.payload.local_edit_version!==pending.local_edit_version||
    !mapping||mapping.conversion!=='CONVERTED'||mapping.operation_id!==operation.id||mapping.object_id!==objectId||mapping.operation_fingerprint!==JSON.stringify(operation)||
    !mapping.revision||!heads.includes(mapping.revision)||!row||row.semantic.transaction_id!==mapping.transaction_id||row.semantic.object_id!==objectId||row.semantic.project_id!==project||
    !mapping.transaction||JSON.stringify(kernel.state.transactions[mapping.transaction_id]?.raw)!==JSON.stringify(mapping.transaction)){
  throw Error('PENDING_OPERATION_REQUIRES_SYNC: 本地工作尚未进入比较分支，请先显式同步，再重新比较；输入已保留');
 }
}
export function localDocument(project:string,kind:string,id:string,d:ConflictDocument,version:number):LocalObject{
 const base={id,project_id:project,local_format_version:1 as const,local_edit_version:version,title:d.title as string};
 return kind==='Note'?{...base,kind:'Note',body:(d.content??'') as string}:{...base,kind:'Run',run_type:d.run_type as string,objective:(d.objective??'') as string,observation:(d.observation??'') as string,status:(d.status??'planned') as any,scientific_outcome:(d.scientific_outcome??'unknown') as any,is_highlighted:(d.is_highlighted??false) as boolean,highlight_type:(d.highlight_type??'') as string,highlight_note:(d.highlight_note??'') as string,context_data:(d.context_data??{}) as Record<string,string>};
}
export class BrowserConflicts implements ConflictService{
 constructor(private open:()=>Promise<IDBDatabase>){}
 list=(project:string)=>businessTransaction(this.open,['meta','objects'],'readonly',async tx=>{
  const meta=tx.objectStore('meta'),binding=await request(meta.get('binding:'+project)) as BindingRecord|undefined;
  if(!binding)return [];
  const authorization=await request(meta.get('authorization:'+project));requireAuthorization(authorization,binding);
  const kernel=await request(meta.get('record-kernel:'+project)) as KernelRecord|undefined;if(!kernel)return [];
  const state=kernel.state,graph=Object.fromEntries(Object.entries(state.revisions).map(([h,r])=>[h,r.semantic.parents]));const records:ConflictRecord[]=[];
  for(const [key,heads] of Object.entries(state.heads)){
   const [kind,id]=key.split(':');if(!['Note','ResearchRun'].includes(kind))continue;
   const candidates=heads.map(h=>{const r=state.revisions[h];return {revision:h,transaction_id:r.semantic.transaction_id,device_id:r.semantic.device_id,document:r.document,state:state.transactions[r.semantic.transaction_id].state};});
   if(heads.length<2&&candidates.every(c=>c.state==='ACCEPTED'))continue;
   const base=heads.length>1?commonBase(graph,heads):null,object=await request(tx.objectStore('objects').get(id)),pending=await request(meta.get('pending-operation:'+id));
   records.push({object_id:id,object_type:kind,local_device_id:binding.binding.principal.device_id,work:object?{document:kind==='Note'?{title:object.title,content:object.body}:{...object},version:object.local_edit_version,pending:!!pending}:null,trusted:{status:heads.length>1?'conflicted':'candidate',heads,base:base?state.revisions[base].document:null,base_revision:base,accepted:state.projections[key]?state.revisions[state.projections[key]].document:null,candidates},audit:state.audits.filter(a=>state.transactions[a.transaction_id]?.raw.changes.some(c=>c.object_id===id&&c.object_type===kind)),pending:pending??null,cas:{project,kernel,object:object??null,pending:pending??null,binding,authorization}});
  }return records;
 });
 resolve=async(record:ConflictRecord,document:ConflictDocument)=>{
  const frozen=structuredClone(record),d=structuredClone(document),cas=frozen.cas as any,{project,binding,kernel}=cas;
  if(!cas||!kernel||!frozen.trusted.heads.length)throw Error('CONFLICT_CHANGED');
  const data=await businessTransaction(this.open,['projects','meta','operations'],'readonly',async tx=>{
   await requireComparedPredecessor(tx,cas.pending,kernel,frozen.trusted.heads,project,frozen.object_id);
   return {project:await request(tx.objectStore('projects').get(project)) as Project,identity:await request(tx.objectStore('meta').get('identity')),operations:await request(tx.objectStore('operations').getAll())};
  });
  const time=new Date().toISOString(),opid=crypto.randomUUID(),tid=crypto.randomUUID(),cid=crypto.randomUUID(),aid=crypto.randomUUID();
  const previousVersion=Math.max(cas.object?.local_edit_version??0,...data.operations.filter(o=>o.object_id===frozen.object_id).map(o=>o.payload.local_edit_version));
  const object=localDocument(project,frozen.object_type,frozen.object_id,d,previousVersion+1);
  const source={workspace_id:data.identity.workspace_id,device_id:data.identity.device_id};
  const operation:LocalOperation={id:opid,project_id:project,object_id:object.id,object_type:object.kind,operation_type:'resolve',payload:object,known_base_revision:null,local_format_version:1,source,state:'pending',wire_adapter:'NEEDS_WIRE_ADAPTER',created_at:time};
  payloadFor(operation,data.project);
  const p=binding.binding.principal,heads=[...frozen.trusted.heads];
  const dependencies=[...new Set(heads.map(h=>(kernel.state as RecordState).revisions[h].semantic.transaction_id))].sort();
  const change={change_id:cid,audit_id:aid,transaction_id:tid,project_id:project,device_id:p.device_id,actor_id:p.actor_id,actor_type:p.actor_type,object_type:frozen.object_type,object_id:object.id,operation:'resolve',parents:heads,payload:d,schema_version:2,module_snapshot_hash:binding.binding.module_snapshot_hash,created_at:time};
  const transaction=validateTransaction({transaction_id:tid,idempotency_key:tid,project_id:project,device_id:p.device_id,actor_id:p.actor_id,actor_type:p.actor_type,protocol_version:2,schema_version:2,created_at:time,ordered_change_ids:[cid],changes:[change],dependencies});
  const staged=await applyRecord(kernel.state,transaction,recordContext(binding,transaction));
  const mapping:WireMapping={id:'mapping:'+opid,operation_id:opid,object_id:object.id,operation_fingerprint:JSON.stringify(operation),prepare_id:opid,prepare_token:crypto.randomUUID(),adapter_version:1,transaction_id:tid,change_id:cid,audit_id:aid,message_id:crypto.randomUUID(),binding_generation:binding.generation,binding_fingerprint:JSON.stringify(binding),parents:heads,dependencies,base_revision:frozen.trusted.base_revision,revision:await revision(transaction.changes[0]),transaction_digest:await transactionDigest(transaction),transaction,envelope:null,conversion:'CONVERTED',transport:'BLOCKED',peer:'UNCONFIRMED',review:'NOT_REQUESTED',source};
  await businessTransaction(this.open,['meta','objects','operations','audit'],'readwrite',async tx=>{
   const meta=tx.objectStore('meta'),b=await request(meta.get(binding.id)),a=await request(meta.get('authorization:'+project));requireAuthorization(a,b);
   const now=await request(meta.get('record-kernel:'+project)),work=await request(tx.objectStore('objects').get(object.id)),pending=await request(meta.get('pending-operation:'+object.id));
   if(JSON.stringify([now,work??null,pending??null,b,a])!==JSON.stringify([kernel,cas.object,cas.pending,binding,cas.authorization]))throw Error('CONFLICT_CHANGED: 比较后版本已变化，输入已保留');
   await requireComparedPredecessor(tx,pending,now,heads,project,object.id);
   if(!['owner','writer'].includes(b.binding.principal.role))throw Error('READ_ONLY');
   await request(tx.objectStore('operations').add(operation));await request(tx.objectStore('objects').put(object));
   await request(tx.objectStore('audit').add({id:crypto.randomUUID(),operation_id:opid,object_id:object.id,project_id:project,event:'resolve',local_edit_version:object.local_edit_version,source,created_at:time,local_format_version:1}));
   await request(meta.add({id:'operation-base:'+opid,operation_id:opid,resolve_heads:heads,resolve_document:d,predecessor_operation_id:cas.pending?.operation_id??null,received_heads:null,working_version:previousVersion,local_edit_version:object.local_edit_version}));
   await request(meta.put(mapping));await request(meta.put({id:'pending-operation:'+object.id,operation_id:opid,local_edit_version:object.local_edit_version}));
   await request(meta.put({id:'local-wire-heads:'+object.id,revision:mapping.revision,transaction_id:tid}));
   await request(meta.put({id:'record-kernel:'+project,generation:kernel.generation+1,state:staged.snapshot}));
  });
 };
}
