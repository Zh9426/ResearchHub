import * as importer from '../src/sync/rescue-import';
import {prepareSyntheticProjects} from '../src/local/seeds';
import {newDraft} from '../src/local/model';
import {canonicalLocal} from '../src/local/rescue';
import {digest} from '../../../packages/sync-protocol/src/browser';
import {openLocalDatabase,readSnapshot} from '../src/local/db';
import {businessTransaction,request} from '../src/sync/authorization';
import {StableWireAdapter,type BindingRecord} from '../src/sync/wire';
import type {LocalObject,LocalOperation} from '../src/local/model';
const assert=(ok:unknown,message:string)=>{if(!ok)throw Error(message);};
async function rejected(work:()=>Promise<unknown>,contains:string){try{await work();throw Error('UNEXPECTED_SUCCESS');}catch(e){assert(String(e).includes(contains),`${contains}: ${e}`);}}
async function fixture(module:string){
 const projects=await prepareSyntheticProjects(),project=projects.find(p=>p.module_id===module)!,source={workspace_id:crypto.randomUUID(),device_id:crypto.randomUUID()};
 const run={...newDraft(project,'Run'),title:' 初始中文 ',objective:' 目标\n',observation:' 初始观察 ',status:'blocked',scientific_outcome:'negative_result',highlight_type:' 初始类型 ',local_edit_version:1} as any;
 const versions=[run,{...run,title:' 编辑正文 ',is_highlighted:true,highlight_note:'混合修改',local_edit_version:2},{...run,title:' 编辑正文 ',is_highlighted:true,highlight_note:'纯星标',local_edit_version:3},{...run,title:' 编辑正文 ',is_highlighted:true,highlight_note:'纯星标',observation:'\n最终观察\n',local_edit_version:4}];
 const note={...newDraft(project,'Note'),title:'中文笔记',body:' 保留空白\n',local_edit_version:1} as LocalObject;
 const other={...newDraft(projects.find(p=>p.id!==project.id)!,'Note'),title:'仅归档',body:'不发送',local_edit_version:1} as LocalObject;
 const operations:LocalOperation[]=[...versions,note,other].map((payload,i)=>({id:crypto.randomUUID(),project_id:payload.project_id,object_id:payload.id,object_type:payload.kind,operation_type:i===0||i>=4?'create':i<3?'highlight':'update',payload,known_base_revision:null,local_format_version:1,source,state:'pending',wire_adapter:'NEEDS_WIRE_ADAPTER',created_at:'2026-10-09T00:00:00.000Z'}));
 const content={format_version:1,scope:'SYNTHETIC_QA_ONLY',plaintext:true,projects,objects:[versions[3],note,other],operations,audit:operations.map(o=>({id:crypto.randomUUID(),operation_id:o.id,object_id:o.object_id,project_id:o.project_id,event:o.operation_type,local_edit_version:o.payload.local_edit_version,source,created_at:o.created_at,local_format_version:1})),drafts:[newDraft(project,'Note')]};
 const raw=JSON.stringify({content,digest:await digest(content)});
 const principal={device_id:crypto.randomUUID(),actor_id:crypto.randomUUID(),actor_type:'human' as const,role:'writer' as const};
 const binding:BindingRecord={id:'binding:'+project.id,generation:1,state:'VERIFIED',binding:{binding_version:1,semantic_project_id:project.id,opaque_project_id:crypto.randomUUID(),module_snapshot:project.module_snapshot,module_snapshot_hash:await digest(project.module_snapshot),local_module_hash:{algorithm:'sha256-json-stringify',value:project.module_hash},capabilities:{protocol_version:2,schema_version:2,object_types:['ResearchRun','Note']},principal,principal_map:[principal],trust:{membership_epoch:1,key_epoch:1,manifest_head:'a'.repeat(64),owner_root:'b'.repeat(64),recovery_root:'c'.repeat(64),manifest_chain:[{}]}}};
 const name='import-unit-'+crypto.randomUUID(),dbOpen=()=>openLocalDatabase(name);
 await businessTransaction(dbOpen,['meta','projects'],'readwrite',async tx=>{
  await request(tx.objectStore('projects').add(project));await request(tx.objectStore('meta').add(binding));
  await request(tx.objectStore('meta').add({id:'identity',workspace_id:crypto.randomUUID(),device_id:principal.device_id,scope:'SYNTHETIC_QA',authorization:'none'}));
  await request(tx.objectStore('meta').add({id:'authorization:'+project.id,state:'READY',phase:'INSTALLED',generation:1,head:binding.binding.trust.manifest_head,binding_fingerprint:JSON.stringify(binding)}));
 });
 const all=()=>businessTransaction(dbOpen,['meta','projects','objects','operations','audit'],'readonly',async tx=>{const out:any={};for(const store of ['meta','projects','objects','operations','audit'])out[store]=await request(tx.objectStore(store).getAll());return canonicalLocal(out);});
 return {raw,content,project,binding,open:dbOpen,all,run,note};
}
(window as any).importUnit=async()=>{
 assert(typeof (importer as any).previewImport==='function','explicit previewImport missing');
 assert(typeof (importer as any).replayImportHistory==='function','pure full-document replay verification missing');
 for(const module of ['hdsp','ice-sonocuring']){
  const f=await fixture(module),before=await f.all(),preview=await importer.previewImport(f.raw,f.project.id,f.binding),service=new importer.RescueImporter(f.open);
  assert(await f.all()===before,'preview wrote data');assert(preview.blockers.length===0,preview.blockers.join(';'));
  const runSteps=preview.steps.filter(s=>f.content.operations.find(o=>o.id===s.sourceOperationId)?.object_id===f.run.id);
  assert(runSteps.map(s=>s.event).join(',')==='create,update,highlight,update','mixed star update lost');
  const selectedOps=f.content.operations.filter(o=>o.project_id===f.project.id),selectedObjects=f.content.objects.filter(o=>o.project_id===f.project.id);
  const wrongSteps=preview.steps.map(step=>step.sourceOperationId===selectedOps[1].id?{...step,event:'highlight' as const}:step);
  // A bad sparse step can be masked by a later full update: truncate exactly at that version.
  const bad=(importer as any).replayImportHistory(selectedOps.slice(0,2),f.project,wrongSteps, [selectedOps[1].payload]);
  assert(bad.blockers.some((b:string)=>b.includes('.title')),'lost full-field replay not blocked');
  const replay=(importer as any).replayImportHistory(selectedOps,f.project,preview.steps,selectedObjects);
  assert(replay.blockers.length===0,'valid complete replay blocked');
  const confirm=(hooks={})=>service.confirmImport(f.raw,f.project.id,preview.bindingFingerprint,preview.planDigest,hooks);
  await rejected(()=>confirm({abortCommit:true}),'TEST_ONLY_IMPORT_ABORT');assert(await f.all()===before,'abort partially imported');
  const result=await confirm();assert(result.operationMap.length===5,'all saved operations replayed');
  assert(canonicalLocal(await confirm())===canonicalLocal(result),'retry generated new IDs');
  const snapshot=await readSnapshot(f.open);assert(snapshot.objects.length===2&&snapshot.operations.length===5,'other projects or drafts enqueued');
  assert(snapshot.operations.every(o=>o.source.device_id===f.binding.binding.principal.device_id),'old device impersonated');
  assert(canonicalLocal(snapshot.objects.find(o=>o.id===f.run.id))===canonicalLocal(f.content.objects[0]),'final materialization differs');
  const adapter=new StableWireAdapter(f.open);for(const entry of result.operationMap)await adapter.convert(entry.operation_id);
  const kernel=await businessTransaction(f.open,['meta'],'readonly',tx=>request(tx.objectStore('meta').get('record-kernel:'+f.project.id)));
  const head=kernel.state.projections['ResearchRun:'+f.run.id];assert(kernel.state.revisions[head].document.title===' 编辑正文 ','replayed title lost');
  assert(kernel.state.revisions[head].document.observation==='\n最终观察\n','replayed observation lost');
  for(const object of selectedObjects){const {id,project_id,kind,local_format_version,local_edit_version,...fields}=object;const expected=kind==='Note'?{title:fields.title,content:(fields as any).body}:fields;const accepted=kernel.state.projections[(kind==='Run'?'ResearchRun':'Note')+':'+id];assert(canonicalLocal(kernel.state.revisions[accepted].document)===canonicalLocal(expected),'all-field kernel materialization differs');assert(canonicalLocal(replay.documents[id])===canonicalLocal(expected),'all-field preview materialization differs');}
  const archive=(await service.archives())[0];assert(archive.archive.raw===f.raw,'original raw lost');
  assert(canonicalLocal((await new importer.RescueImporter(f.open).archives())[0].journal)===canonicalLocal(result),'reopen changed journal');
 }
 for(const kind of ['actor','unknown','length','module','identity','null','context']){
  const f=await fixture('hdsp'),pack=JSON.parse(f.raw);
  if(kind==='actor')pack.content.operations[0].source.actor='human';
  if(kind==='unknown')pack.content.objects[0].unexpected='x';
  if(kind==='module')pack.content.projects[1].module_snapshot.extra='x';
  if(kind==='identity')pack.content.operations[0].payload.project_id=crypto.randomUUID();
  if(kind==='null')pack.content.objects[0].observation=null;
  if(kind==='context'){for(const o of pack.content.operations.filter((o:any)=>o.object_id===f.run.id))o.payload.context_data={context:'3A local only field'};pack.content.objects[0].context_data={context:'3A local only field'};}
  if(kind==='length'){for(const o of pack.content.operations.filter((o:any)=>o.object_id===f.run.id))o.payload.title='长'.repeat(201);pack.content.objects[0].title='长'.repeat(201);}
  pack.digest=await digest(pack.content);const raw=JSON.stringify(pack);
  if(kind==='length')assert((await importer.previewImport(raw,f.project.id,f.binding)).blockers.some(x=>x.includes('title')),'Domain title too long allowed');
  else if(kind==='context')assert((await importer.previewImport(raw,f.project.id,f.binding)).blockers.some(x=>x.includes('context_data.context')),'local-only context silently deleted');
  else await rejected(()=>importer.previewImport(raw,f.project.id,f.binding),'救援包校验失败');
 }
 for(const race of ['authorization','history','collision','orphan-pending']){
  const f=await fixture('hdsp'),preview=await importer.previewImport(f.raw,f.project.id,f.binding),service=new importer.RescueImporter(f.open);
  await rejected(()=>service.confirmImport(f.raw,f.project.id,preview.bindingFingerprint,preview.planDigest,{beforeCommit:async()=>{
   await businessTransaction(f.open,['meta','objects'],'readwrite',async tx=>{
    if(race==='authorization'){const a=await request(tx.objectStore('meta').get('authorization:'+f.project.id));await request(tx.objectStore('meta').put({...a,state:'BLOCKED'}));}
    if(race==='history')await request(tx.objectStore('meta').put({id:'record-kernel:'+f.project.id,state:{revisions:{old:{}},transactions:{}}}));
    if(race==='collision')await request(tx.objectStore('objects').put({...f.run,project_id:crypto.randomUUID()}));
    if(race==='orphan-pending')await request(tx.objectStore('meta').put({id:'pending-operation:'+crypto.randomUUID(),operation_id:crypto.randomUUID()}));
   });
  }}),race==='authorization'?'AUTHORIZATION_NOT_READY':race==='collision'?'IMPORT_OBJECT_UUID_COLLISION':'IMPORT_TARGET_HISTORY');
  assert((await readSnapshot(f.open)).operations.length===0,'race imported operations');
 }
 return {passed:true};
};
