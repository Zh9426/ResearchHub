import generic from '../../../../packages/project-modules/generic/manifest.json';
import hdsp from '../../../../packages/project-modules/hdsp/manifest.json';
import ice from '../../../../packages/project-modules/ice-sonocuring/manifest.json';
import {openLocalDatabase,readSnapshot,STORES} from './db';
import {RUN_STATUSES,OUTCOMES,type Identity,type Project,type LocalObject,type LocalOperation,type LocalAudit,type RestoreAudit} from './model';

// Deliberately separate local QA format. Never a wire transaction or Recovery Kit.
export type RescueContent={format_version:1;scope:'SYNTHETIC_QA_ONLY';plaintext:true;projects:Project[];objects:LocalObject[];operations:LocalOperation[];audit:LocalAudit[];drafts:LocalObject[]};
export type RescuePackage={content:RescueContent;digest:string};
export const MAX_RESCUE_BYTES=10*1024*1024;
export function canonicalLocal(value:unknown):string {
 if(value===null||typeof value!=='object')return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(canonicalLocal).join(',')+']';
 const object=value as Record<string,unknown>;
 return '{'+Object.keys(object).sort().map(key=>JSON.stringify(key)+':'+canonicalLocal(object[key])).join(',')+'}';
}
async function hash(text:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),x=>x.toString(16).padStart(2,'0')).join('');}
function check(condition:unknown,message:string):asserts condition {if(!condition)throw Error('救援包校验失败：'+message);}
function record(v:unknown):asserts v is Record<string,any>{check(!!v&&typeof v==='object'&&!Array.isArray(v),'应为对象');}
function exact(v:unknown,keys:string[]){record(v);check(Object.keys(v).sort().join('|')===[...keys].sort().join('|'),'未知或缺失字段（禁止密钥、授权与凭据字段）');}
function text(v:unknown,max=100000):asserts v is string {check(typeof v==='string'&&v.length<=max,'文本类型或长度无效');}
function uuid(v:unknown){check(typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v),'UUID 无效');}
function digest(v:unknown){check(typeof v==='string'&&/^[0-9a-f]{64}$/.test(v),'摘要无效');}
function source(v:unknown){exact(v,['workspace_id','device_id']);record(v);uuid(v.workspace_id);uuid(v.device_id);}
function time(v:unknown){check(typeof v==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString()===v,'事件时间无效');}
function list(v:unknown):asserts v is any[]{check(Array.isArray(v)&&v.length<=10000,'数组类型或数量无效');}
function unique(items:{id:string}[]){check(new Set(items.map(x=>x.id)).size===items.length,'重复 ID');}
const common=['id','project_id','title','local_format_version','local_edit_version','kind'];
function validateObject(v:any,projects:Project[],draft=false){
 record(v);exact(v,v.kind==='Run'?[...common,'run_type','objective','observation','status','scientific_outcome','is_highlighted','highlight_type','highlight_note','context_data']:[...common,'body']);
 uuid(v.id);uuid(v.project_id);text(v.title,500);check(draft||v.title.trim().length>0,'已保存记录标题为空');check(v.local_format_version===1&&Number.isSafeInteger(v.local_edit_version)&&v.local_edit_version>=(draft?0:1),'本地版本无效');
 const p=projects.find(x=>x.id===v.project_id);check(p,'记录引用的项目不存在');
 if(v.kind==='Run'){
  check(RUN_STATUSES.includes(v.status)&&OUTCOMES.includes(v.scientific_outcome)&&typeof v.is_highlighted==='boolean','Run 状态无效');
  for(const key of ['run_type','objective','observation','highlight_type','highlight_note'])text(v[key]);
  check(p.module_snapshot.run_types.some(t=>t.id===v.run_type),'模块记录类型无效');record(v.context_data);
  // Local UI additions are explicit; this does not extend frozen wire fields.
  const allowed=new Set(['context',...(p.route_alias==='ice'?['experiment_conditions']:[]),...(p.module_snapshot.context_fields as {id:string}[]).map(f=>f.id)]);
  for(const [key,value] of Object.entries(v.context_data)){check(allowed.has(key),'未知语境字段');text(value);}
 }else {check(v.kind==='Note','未知记录类型');text(v.body);}
}
/** No writes occur here. Only exact frozen synthetic manifests are accepted. */
export async function previewRescue(raw:string):Promise<RescuePackage>{
 check(new TextEncoder().encode(raw).length<=MAX_RESCUE_BYTES,'文件超过 10 MiB');
 const pack=JSON.parse(raw);exact(pack,['content','digest']);digest(pack.digest);const c=pack.content;
 exact(c,['format_version','scope','plaintext','projects','objects','operations','audit','drafts']);check(c.format_version===1&&c.scope==='SYNTHETIC_QA_ONLY'&&c.plaintext===true,'不是受支持的合成明文格式');
 for(const key of ['projects','objects','operations','audit','drafts']){list(c[key]);for(const value of c[key])record(value);unique(c[key]);}
 check(c.projects.length===3,'必须包含三个冻结合成项目');
 const frozen=[generic,hdsp,ice];const aliases=['generic','hdsp','ice'];
 for(const p of c.projects){
  exact(p,['id','route_alias','title','scope','module_id','module_version','module_snapshot','module_hash','local_format_version']);uuid(p.id);text(p.title,500);digest(p.module_hash);check(p.scope==='SYNTHETIC'&&p.local_format_version===1,'项目范围无效');
  const i=aliases.indexOf(p.route_alias);check(i>=0,'项目别名无效');const expected=frozen[i];check(p.module_id===expected.id&&p.module_version===expected.version&&canonicalLocal(p.module_snapshot)===canonicalLocal(expected),'冻结模块快照不匹配或包含额外字段');
  check(await hash(JSON.stringify(p.module_snapshot))===p.module_hash,'模块快照摘要不匹配');
 }
 check(new Set(c.projects.map((p:Project)=>p.route_alias)).size===3,'项目别名重复');
 for(const o of c.objects)validateObject(o,c.projects);for(const d of c.drafts)validateObject(d,c.projects,true);
 for(const op of c.operations){
  exact(op,['id','project_id','object_id','object_type','operation_type','payload','known_base_revision','local_format_version','source','state','wire_adapter','created_at']);uuid(op.id);source(op.source);time(op.created_at);
  check(op.known_base_revision===null&&op.local_format_version===1&&op.state==='pending'&&op.wire_adapter==='NEEDS_WIRE_ADAPTER'&&['create','update','highlight'].includes(op.operation_type),'操作不是未签名本地 pending');validateObject(op.payload,c.projects);
  const o=c.objects.find((x:LocalObject)=>x.id===op.object_id);check(o&&o.project_id===op.project_id&&o.kind===op.object_type&&op.payload.id===o.id&&op.payload.project_id===o.project_id&&op.payload.kind===o.kind&&op.payload.local_edit_version<=o.local_edit_version,'操作引用不一致');
  check(op.operation_type!=='highlight'||op.object_type==='Run','Note 不支持星标事件');
 }
 for(const o of c.objects){
  const ops=c.operations.filter((op:LocalOperation)=>op.object_id===o.id).sort((a:LocalOperation,b:LocalOperation)=>a.payload.local_edit_version-b.payload.local_edit_version);
  check(ops.length===o.local_edit_version&&ops.every((op:LocalOperation,i:number)=>op.payload.local_edit_version===i+1&&(i===0?op.operation_type==='create':op.operation_type!=='create')),'操作历史版本不连续');check(canonicalLocal(ops.at(-1)?.payload)===canonicalLocal(o),'当前记录与最后操作不一致');
 }
 for(const a of c.audit){
  if(a.event==='restore'){exact(a,['id','event','package_digest','source','created_at','local_format_version']);digest(a.package_digest);}
  else{
   exact(a,['id','operation_id','object_id','project_id','event','local_edit_version','source','created_at','local_format_version']);const op=c.operations.find((x:LocalOperation)=>x.id===a.operation_id);
   check(op&&a.object_id===op.object_id&&a.project_id===op.project_id&&a.event===op.operation_type&&a.local_edit_version===op.payload.local_edit_version&&a.created_at===op.created_at&&canonicalLocal(a.source)===canonicalLocal(op.source),'审计引用不一致');
  }
  uuid(a.id);source(a.source);time(a.created_at);check(a.local_format_version===1,'审计版本无效');
 }
 for(const op of c.operations)check(c.audit.filter((a:LocalAudit)=>a.event!=='restore'&&a.operation_id===op.id).length===1,'操作必须有唯一审计');
 check(await hash(canonicalLocal(c))===pack.digest,'完整性摘要不匹配；摘要不证明来源');return pack as RescuePackage;
}
export async function exportRescue(currentDraft:LocalObject|null):Promise<string>{
 const snapshot=await readSnapshot();check(snapshot.identity?.scope==='SYNTHETIC_QA','请先初始化合成工作区');
 const drafts=snapshot.drafts.filter(x=>x.id!==currentDraft?.id);if(currentDraft)drafts.push(structuredClone(currentDraft));
 const content:RescueContent={format_version:1,scope:'SYNTHETIC_QA_ONLY',plaintext:true,projects:snapshot.projects,objects:snapshot.objects,operations:snapshot.operations,audit:snapshot.audit,drafts};
 const serialized=JSON.stringify({content,digest:await hash(canonicalLocal(content))},null,2);await previewRescue(serialized);return serialized;
}
/** Validate again, then short transaction with all-store emptiness/id checks. */
export async function restoreRescue(input:RescuePackage):Promise<'restored'|'already_restored'>{
 const pack=await previewRescue(JSON.stringify(input));
 const identity:Identity={id:'identity',workspace_id:crypto.randomUUID(),device_id:crypto.randomUUID(),scope:'SYNTHETIC_QA',authorization:'none'};
 const event:RestoreAudit={id:crypto.randomUUID(),event:'restore',package_digest:pack.digest,source:{workspace_id:identity.workspace_id,device_id:identity.device_id},created_at:new Date().toISOString(),local_format_version:1};
 const db=await openLocalDatabase();return new Promise((resolve,reject)=>{
  const tx=db.transaction([...STORES],'readwrite');let error:Error|undefined;let result:'restored'|'already_restored'='restored';
  const reads=STORES.map(name=>tx.objectStore(name).getAll());let remaining=reads.length;
  for(const request of reads)request.onsuccess=()=>{
   if(--remaining)return;const meta=reads[0].result;
   if(meta.some(x=>x.id==='rescue-import'&&x.digest===pack.digest)){result='already_restored';return;}
   for(let i=1;i<STORES.length;i++){
    const incoming=pack.content[STORES[i] as 'projects'|'objects'|'operations'|'audit'];
    if(reads[i].result.some(old=>incoming.some(x=>x.id===old.id&&canonicalLocal(x)!==canonicalLocal(old)))){error=Error('ID 相同但内容不同：整包冲突，未覆盖任何数据。');tx.abort();return;}
   }
   if(reads.some(r=>r.result.length)){error=Error('工作区非空：只允许空工作区恢复或同包幂等重试，未合并或覆盖。');tx.abort();return;}
   tx.objectStore('meta').add(identity);tx.objectStore('meta').add({id:'rescue-import',digest:pack.digest});tx.objectStore('meta').add({id:'rescue-drafts',drafts:pack.content.drafts});
   for(const name of ['projects','objects','operations','audit'] as const)for(const value of pack.content[name])tx.objectStore(name).add(value);
   tx.objectStore('audit').add(event);
  };
  tx.oncomplete=()=>{db.close();resolve(result);};tx.onabort=()=>{db.close();reject(error??tx.error??Error('救援恢复事务中止；未写入任何部分数据。'));};
 });
}
