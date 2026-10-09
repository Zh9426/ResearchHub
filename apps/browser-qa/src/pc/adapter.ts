import type {RecordSyncStatus} from '../sync/status';
import type {WorkbenchAdapter,SyncResult} from '../Workbench';
import type {LocalObject,LocalSnapshot,Run} from '../local/model';
import {LocalConflictError} from '../local/commands';
import {canonicalBytes} from '../../../../packages/sync-protocol/src/browser';
export type PcRecord={sync_status?:RecordSyncStatus;object_id:string;object_type:string;work:{document:Record<string,unknown>;version:number;pending:boolean;base_heads:string[]}|null;trusted:{status:string;heads:string[];accepted:unknown;candidates:unknown[]};history:unknown[]};
export type PcSnapshot={snapshot:LocalSnapshot;records:PcRecord[];outbox_count:number};
let csrf='';let records:PcRecord[]=[];
let sessionRequest:Promise<void>|null=null;
const prepared=new Map<string,Record<string,unknown>>();
export async function request<T>(path:string,body?:unknown):Promise<T>{
 if(!csrf){if(!sessionRequest)sessionRequest=(async()=>{const response=await fetch('/api/session',{credentials:'same-origin',redirect:'error',cache:'no-store'});if(!response.ok)throw Error('PC 会话不可用');csrf=(await response.json()).csrf;})().finally(()=>{sessionRequest=null;});await sessionRequest;}
 const requestCsrf=csrf;
 const pairing=['/api/pairing/start','/api/pairing/confirm','/api/pairing/resume'].includes(path);
 const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:body===undefined?{}:{'content-type':'application/json','x-pc-csrf':csrf},body:body===undefined?undefined:pairing?new TextDecoder().decode(canonicalBytes(body)):JSON.stringify(body)});
 const result=await response.json();if(!response.ok){if(['SESSION_REQUIRED','CSRF_REQUIRED'].includes(result.error)){if(csrf===requestCsrf)csrf='';throw Error('PC 会话已失效，输入与命令身份已保留；请再次点击保存以建立新会话');}if(['WORK_CAS','HEADS_CAS'].includes(result.error))throw new LocalConflictError();throw Error(result.error||'PC 操作失败');}return result as T;
}
export async function snapshot(){const value=await request<PcSnapshot>('/api/snapshot');for(const incoming of value.records){const old=records.find(r=>r.object_id===incoming.object_id);if(!old)records.push(incoming);else if((incoming.work?.version??0)>=(old.work?.version??0))Object.assign(old,incoming);}return value;}
type DraftBaseline={objectId:string;version:number;heads:string[]};
function captureBaseline(object:LocalObject):DraftBaseline{return {objectId:object.id,version:object.local_edit_version,heads:[...(records.find(r=>r.object_id===object.id)?.trusted.heads??[])]};}
async function command(object:LocalObject,operation:string,patch:Record<string,unknown>,baseline?:DraftBaseline){
 if(baseline&&(baseline.objectId!==object.id||baseline.version!==object.local_edit_version))throw new LocalConflictError();
 const record=records.find(r=>r.object_id===object.id);
 const input={object_id:object.id,object_type:object.kind==='Run'?'ResearchRun':'Note',operation,expected_work_version:object.local_edit_version,expected_heads:baseline?.heads??record?.trusted.heads??[],patch};
 const key=JSON.stringify(input);let cmd=prepared.get(key);
 if(!cmd){cmd={...input,command_id:crypto.randomUUID(),transaction_id:crypto.randomUUID()};prepared.set(key,cmd);}
 const saved=await request<{object:LocalObject;heads:string[]}>('/api/command',cmd);
 // Keep response-loss retries bound to the original command identity until process reload.
 const current=records.find(r=>r.object_id===object.id);if(current){current.trusted.heads=saved.heads;current.work={document:{},version:saved.object.local_edit_version,pending:true,base_heads:saved.heads};}
 else records.push({object_id:object.id,object_type:input.object_type,work:{document:{},version:saved.object.local_edit_version,pending:true,base_heads:saved.heads},trusted:{status:'accepted',heads:saved.heads,accepted:null,candidates:[]},history:[]});
 return saved.object;
}
function saveDraft(object:LocalObject,baseline?:DraftBaseline){
 const patch=object.kind==='Note'?{title:object.title,content:object.body}:{title:object.title,run_type:object.run_type,objective:object.objective,observation:object.observation,status:object.status,scientific_outcome:object.scientific_outcome,context_data:object.context_data,is_highlighted:object.is_highlighted,highlight_type:object.highlight_type,highlight_note:object.highlight_note};
 return command(object,object.local_edit_version>0||records.some(r=>r.object_id===object.id)?'update':'create',patch,baseline);
}
export const pcAdapter:WorkbenchAdapter={recordStatus:async object=>{const result=(await snapshot()).records.find(r=>r.object_id===object.id)?.sync_status;if(!result)throw Error('RECORD_STATUS_MISSING');return result;},captureBaseline,saveDraft:(object,baseline)=>saveDraft(object,baseline as DraftBaseline),highlightDraft:(id,version,patch,baseline)=>command({id,kind:'Run',local_edit_version:version} as Run,'highlight',patch,baseline as DraftBaseline),synchronize:()=>request<SyncResult>('/api/sync',{}),sync:true,pc:true,initialize:async()=>{throw Error('PC 项目由受控启动流程建立');},commands:{
 notifications:null,injectNextAbort(){throw Error('正常 PC 页面没有故障注入接口');},
 snapshot:async()=>(await snapshot()).snapshot,
 save:saveDraft,
 setHighlight:async(id:string,expectedVersion:number,patch:Pick<Run,'is_highlighted'|'highlight_type'|'highlight_note'>)=>command({id,kind:'Run',local_edit_version:expectedVersion} as Run,'highlight',patch),
}};
