/** Explicit 3A archive and replay; never restores the source browser identity. */
import {previewRescue,canonicalLocal,MAX_RESCUE_BYTES,type RescuePackage} from '../local/rescue';
import type {Project,LocalOperation,LocalObject,OperationAudit,Identity} from '../local/model';
import {STORES} from '../local/db';
import {digest} from '../../../../packages/sync-protocol/src/browser';
import {previewBinding} from './binding';
import {payloadFor,WireBlocked,type BindingRecord} from './wire';
import {businessTransaction,request,requireAuthorization} from './authorization';

const PLAN_VERSION=1;
async function validatedPack(raw:string){
 // Add source paths without weakening the shared complete 3A validator.
 if(new TextEncoder().encode(raw).length>MAX_RESCUE_BYTES)throw Error('救援包校验失败：source: 超过 10 MiB');
 const value=JSON.parse(raw),content=value?.content;
 const exact=(o:any,keys:string[],path:string)=>{if(o&&typeof o==='object'&&!Array.isArray(o)){for(const key of Object.keys(o))if(!keys.includes(key))throw Error(`救援包校验失败：${path}.${key}: 未知字段，无法无损适配`);}};
 const object=(o:any,path:string)=>exact(o,['id','project_id','title','local_format_version','local_edit_version','kind',...(o?.kind==='Run'?['run_type','objective','observation','status','scientific_outcome','is_highlighted','highlight_type','highlight_note','context_data']:['body'])],path);
 if(content){
  for(const name of ['objects','drafts'])if(Array.isArray(content[name]))content[name].forEach((o:any,i:number)=>object(o,`source.${name}.${i}`));
  if(Array.isArray(content.operations))content.operations.forEach((o:any,i:number)=>{exact(o?.source,['workspace_id','device_id'],`source.operations.${i}.source`);object(o?.payload,`source.operations.${i}.payload`);});
 }
 return previewRescue(raw);
}
export type ImportPreview={sourceDigest:string;selectedProjectId:string;bindingFingerprint:string;planDigest:string;project:Project;counts:{objects:number;operations:number;archiveProjects:number;drafts:number};blockers:string[];steps:{sourceOperationId:string;event:LocalOperation['operation_type']}[]};
function eventFor(previous:LocalObject|undefined,current:LocalObject):LocalOperation['operation_type']{
 if(!previous)return 'create';
 if(previous.kind==='Run'&&current.kind==='Run'){
  const omit=(o:LocalObject)=>Object.fromEntries(Object.entries(o).filter(([key])=>!['local_edit_version','is_highlighted','highlight_type','highlight_note'].includes(key)));
  if(canonicalLocal(omit(previous))===canonicalLocal(omit(current))&&['is_highlighted','highlight_type','highlight_note'].some(k=>(previous as any)[k]!==(current as any)[k]))return 'highlight';
 }
 return 'update';
}
function selectedOperations(pack:RescuePackage,project:string){return pack.content.operations.filter(o=>o.project_id===project).sort((a,b)=>a.object_id.localeCompare(b.object_id)||a.payload.local_edit_version-b.payload.local_edit_version);}
function completeSourceDocument(object:LocalObject):Record<string,unknown>{
 const {id,project_id,kind,local_format_version,local_edit_version,...fields}=object;
 return kind==='Note'?{title:fields.title,content:(fields as {body:string}).body}:fields;
}
function differingPaths(actual:any,expected:any,path:string):string[]{
 if(canonicalLocal(actual)===canonicalLocal(expected))return [];
 if(actual&&expected&&typeof actual==='object'&&typeof expected==='object'&&!Array.isArray(actual)&&!Array.isArray(expected))return [...new Set([...Object.keys(actual),...Object.keys(expected)])].flatMap(key=>differingPaths(actual[key],expected[key],path+'.'+key));
 return [path+': 重放材料化与完整来源字段不一致'];
}
/** Pure sparse/full wire replay checked independently against every complete source payload. */
export function replayImportHistory(operations:LocalOperation[],project:Project,steps:ImportPreview['steps'],finalObjects:LocalObject[]){
 const documents:Record<string,Record<string,unknown>>={},blockers:string[]=[];
 for(const operation of [...operations].sort((a,b)=>a.object_id.localeCompare(b.object_id)||a.payload.local_edit_version-b.payload.local_edit_version)){
  const step=steps.find(s=>s.sourceOperationId===operation.id);if(!step){blockers.push(`operations.${operation.id}: 缺少重放计划`);continue;}
  try{
   const payload=payloadFor({...operation,operation_type:step.event},project);
   documents[operation.object_id]=step.event==='create'?structuredClone(payload):{...documents[operation.object_id],...structuredClone(payload)};
   blockers.push(...differingPaths(documents[operation.object_id],completeSourceDocument(operation.payload),`operations.${operation.id}.payload`));
  }catch(error){blockers.push(...(error instanceof WireBlocked?error.reasons:[String(error)]).map(reason=>`operations.${operation.id}.${reason}`));}
 }
 for(const object of finalObjects)blockers.push(...differingPaths(documents[object.id],completeSourceDocument(object),`source.objects.${object.id}`));
 return {documents,blockers};
}
export async function sourceProjectDescriptor(raw:string,selectedProjectId:string){const pack=await validatedPack(raw),project=pack.content.projects.find(p=>p.id===selectedProjectId);if(!project)throw Error('SOURCE_PROJECT_MISSING');return {format:'RESEARCHHUB_3A_SOURCE_PROJECT_V1',project};}
/** Pure preview: full pack, binding and all saved steps; no database, IDs, or nonce writes. */
export async function previewImport(raw:string,selectedProjectId:string,targetBinding:BindingRecord):Promise<ImportPreview>{
 const pack=await validatedPack(raw),project=pack.content.projects.find(p=>p.id===selectedProjectId);if(!project)throw Error('SOURCE_PROJECT_MISSING');
 const b=await previewBinding(targetBinding.binding,project),blockers=b.state==='BLOCKED'?[...b.reasons]:[];
 if(targetBinding.state!=='VERIFIED')blockers.push('binding.state: 需要已授权 VERIFIED 目标');
 if(!['owner','writer'].includes(targetBinding.binding.principal.role))blockers.push('binding.principal.role: 目标不可写');
 const previous=new Map<string,LocalObject>();
 const steps=selectedOperations(pack,project.id).map(op=>{
  const event=eventFor(previous.get(op.object_id),op.payload);previous.set(op.object_id,op.payload);
  return {sourceOperationId:op.id,event};
 });
 blockers.push(...replayImportHistory(selectedOperations(pack,project.id),project,steps,pack.content.objects.filter(o=>o.project_id===project.id)).blockers);
 const bindingFingerprint=await digest(targetBinding);
 const plan={version:PLAN_VERSION,sourceDigest:pack.digest,selectedProjectId,bindingFingerprint,steps};
 return {...plan,planDigest:await digest(plan),project,counts:{objects:previous.size,operations:steps.length,archiveProjects:pack.content.projects.length-1,drafts:pack.content.drafts.length},blockers};
}
export type ImportResult={id:string;sourceDigest:string;selectedProjectId:string;bindingFingerprint:string;planDigest:string;operationMap:{source_operation_id:string;operation_id:string;audit_id:string}[];state:'IMPORTED_NOT_SENT'};
export class RescueImporter{
 constructor(private open:()=>Promise<IDBDatabase>){}
 async archives(){return businessTransaction(this.open,['meta'],'readonly',async tx=>{const rows=await request(tx.objectStore('meta').getAll());return rows.filter(row=>row.id.startsWith('import-journal:')).map(journal=>({journal,archive:rows.find(row=>row.id==='import-archive:'+journal.id),wireMap:journal.operationMap.map((entry:ImportResult['operationMap'][number])=>{const mapping=rows.find(row=>row.id==='mapping:'+entry.operation_id);return {...entry,wire:mapping?{transaction_id:mapping.transaction_id,change_id:mapping.change_id,audit_id:mapping.audit_id,message_id:mapping.message_id,revision:mapping.revision,transaction_digest:mapping.transaction_digest,conversion:mapping.conversion}:null};})}));});}
 async binding(project:string){return businessTransaction(this.open,['meta'],'readonly',tx=>request(tx.objectStore('meta').get('binding:'+project))) as Promise<BindingRecord|undefined>;}
 async confirmImport(raw:string,selectedProjectId:string,expectedBindingFingerprint:string,expectedPlanDigest:string,hooks:{beforeCommit?:()=>Promise<void>;abortCommit?:boolean}={}):Promise<ImportResult>{
  const binding=await this.binding(selectedProjectId);if(!binding)throw Error('IMPORT_BINDING_MISSING');
  const preview=await previewImport(raw,selectedProjectId,binding);
  if(preview.blockers.length)throw new WireBlocked(preview.blockers);
  if(preview.bindingFingerprint!==expectedBindingFingerprint||preview.planDigest!==expectedPlanDigest)throw Error('IMPORT_PREVIEW_CHANGED');
  const pack=await previewRescue(raw),ops=selectedOperations(pack,selectedProjectId),created_at=new Date().toISOString();
  const ids=ops.map(()=>({operation_id:crypto.randomUUID(),audit_id:crypto.randomUUID()}));
  const journalId='import-journal:'+await digest({source:pack.digest,project:selectedProjectId,version:PLAN_VERSION,binding:expectedBindingFingerprint});
  await hooks.beforeCommit?.();
  return businessTransaction(this.open,[...STORES],'readwrite',async tx=>{
   const meta=tx.objectStore('meta'),now=await request(meta.get(binding.id)),auth=await request(meta.get('authorization:'+selectedProjectId));
   requireAuthorization(auth,now);if(JSON.stringify(now)!==JSON.stringify(binding))throw Error('IMPORT_BINDING_CHANGED');
   const identity=await request(meta.get('identity')) as Identity;
   if(!identity||identity.scope!=='SYNTHETIC_QA'||identity.device_id!==binding.binding.principal.device_id)throw Error('IMPORT_DEVICE_CHANGED');
   const old=await request(meta.get(journalId)) as ImportResult|undefined;
   if(old){if(old.planDigest!==expectedPlanDigest)throw Error('IMPORT_JOURNAL_CHANGED');return old;}
   const project=await request(tx.objectStore('projects').get(selectedProjectId)) as Project;
   if(!project||project.module_hash!==preview.project.module_hash||canonicalLocal(project.module_snapshot)!==canonicalLocal(preview.project.module_snapshot))throw Error('IMPORT_PROJECT_CHANGED');
   const objects=await request(tx.objectStore('objects').getAll()) as LocalObject[],operations=await request(tx.objectStore('operations').getAll()) as LocalOperation[],audits=await request(tx.objectStore('audit').getAll()),all=await request(meta.getAll());
   const sourceIds=new Set(pack.content.objects.filter(o=>o.project_id===selectedProjectId).map(o=>o.id));
   if(objects.some(o=>o.project_id===selectedProjectId)||operations.some(o=>o.project_id===selectedProjectId)||audits.some(a=>a.project_id===selectedProjectId))throw Error('IMPORT_TARGET_NOT_EMPTY');
   if(objects.some(o=>sourceIds.has(o.id))||operations.some(o=>sourceIds.has(o.object_id)))throw Error('IMPORT_OBJECT_UUID_COLLISION');
   for(const row of all){
    if(row.id==='record-kernel:'+selectedProjectId&&(row.state?.sequence||row.state?.watermark||['revisions','transactions','heads','dependencies','projections','conflicts','audits'].some(key=>Object.keys(row.state?.[key]??{}).length)))throw Error('IMPORT_TARGET_HISTORY');
    if(row.id.startsWith('record-kernel:')&&Object.values(row.state?.revisions??{}).some((r:any)=>sourceIds.has(r.semantic?.object_id)))throw Error('IMPORT_OBJECT_UUID_COLLISION');
    if(row.id==='relay-cursor:'+selectedProjectId&&row.cursor>0)throw Error('IMPORT_TARGET_HISTORY');
    if(/^(import-journal:|mapping:|received:|received-|operation-base:|pending-operation:|local-wire-heads:)/.test(row.id)){
     const scope=row.project_id??row.selectedProjectId??row.transaction?.project_id??operations.find(o=>o.id===row.operation_id)?.project_id;
     if(!scope||scope===selectedProjectId||row.binding_fingerprint===JSON.stringify(binding)||row.id.endsWith(':'+selectedProjectId)||sourceIds.has(row.object_id)||[...sourceIds].some(id=>row.id.endsWith(':'+id)))throw Error('IMPORT_TARGET_HISTORY');
    }
   }
   const source={workspace_id:identity.workspace_id,device_id:identity.device_id},predecessors=new Map<string,string>();
   const result:ImportResult={id:journalId,sourceDigest:pack.digest,selectedProjectId,bindingFingerprint:preview.bindingFingerprint,planDigest:preview.planDigest,operationMap:[],state:'IMPORTED_NOT_SENT'};
   await request(meta.add({id:'import-archive:'+journalId,readonly:true,raw,sourceDigest:pack.digest,content:pack.content}));
   for(let i=0;i<ops.length;i++){
    const original=ops[i],id=ids[i],event=preview.steps[i].event;
    const operation:LocalOperation={...original,id:id.operation_id,source,created_at,operation_type:event,payload:structuredClone(original.payload)};
    const audit:OperationAudit={id:id.audit_id,operation_id:operation.id,object_id:operation.object_id,project_id:selectedProjectId,event,local_edit_version:operation.payload.local_edit_version,source,created_at,local_format_version:1};
    await request(tx.objectStore('operations').add(operation));await request(tx.objectStore('audit').add(audit));
    await request(meta.add({id:'operation-base:'+operation.id,operation_id:operation.id,predecessor_operation_id:predecessors.get(operation.object_id)??null,received_heads:null,working_version:operation.payload.local_edit_version-1,local_edit_version:operation.payload.local_edit_version}));
    await request(meta.put({id:'pending-operation:'+operation.object_id,operation_id:operation.id,local_edit_version:operation.payload.local_edit_version}));
    result.operationMap.push({source_operation_id:original.id,operation_id:operation.id,audit_id:audit.id});predecessors.set(operation.object_id,operation.id);
   }
   for(const object of pack.content.objects.filter(o=>o.project_id===selectedProjectId))await request(tx.objectStore('objects').add(object));
   await request(meta.add(result));if(hooks.abortCommit)throw Error('TEST_ONLY_IMPORT_ABORT');return result;
  });
 }
}
