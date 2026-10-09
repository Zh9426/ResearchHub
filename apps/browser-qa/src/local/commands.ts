import {openLocalDatabase,STORES,readSnapshot} from './db';
import {RUN_STATUSES,OUTCOMES,type Identity,type LocalObject,type LocalOperation,type LocalAudit,type Project} from './model';
export class LocalConflictError extends Error {constructor(){super('检测到其他标签页修改，请比较后保存；本次修改尚未保存。');this.name='LocalConflictError';}}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function validate(object:LocalObject){
 if(!object||!uuid.test(object.id)||!uuid.test(object.project_id)||object.local_format_version!==1||!Number.isSafeInteger(object.local_edit_version)||object.local_edit_version<0)throw Error('本地记录标识或版本无效');
 if(typeof object.title!=='string'||!object.title.trim()||object.title.length>500)throw Error('请填写标题（最多 500 字）');
 if(object.kind==='Run'){
  if(!RUN_STATUSES.includes(object.status)||!OUTCOMES.includes(object.scientific_outcome)||typeof object.is_highlighted!=='boolean')throw Error('运行状态或科研结果无效');
  for(const value of [object.run_type,object.objective,object.observation,object.highlight_type,object.highlight_note])if(typeof value!=='string'||value.length>100000)throw Error('记录文本格式无效或过长');
  if(!object.context_data||typeof object.context_data!=='object'||Array.isArray(object.context_data)||Object.values(object.context_data).some(x=>typeof x!=='string'||x.length>100000))throw Error('语境格式无效');
 }else if(object.kind==='Note'){if(typeof object.body!=='string'||object.body.length>100000)throw Error('笔记格式无效或过长');}else throw Error('不支持的本地记录类型');
}
export class LocalCommandService {
 private abortNext=false;
 private quotaNext=false;
 readonly notifications=typeof BroadcastChannel==='undefined'?null:new BroadcastChannel('researchhub-synthetic-local-changes-v1');
 snapshot=readSnapshot;
 // QA-only fault hook; abort follows successful write requests, before commit.
 injectNextAbort(){this.abortNext=true;}
 injectNextQuota(){this.quotaNext=true;}
 async save(input:LocalObject):Promise<LocalObject>{
  const object=structuredClone(input);validate(object);
  const operationId=crypto.randomUUID(),auditId=crypto.randomUUID(),time=new Date().toISOString();
  const abort=this.abortNext,quota=this.quotaNext;this.abortNext=false;this.quotaNext=false;const db=await openLocalDatabase();
  return new Promise((resolve,reject)=>{
   const tx=db.transaction([...STORES],'readwrite');let failure:Error|undefined;let result:LocalObject;
   const fail=(error:Error)=>{failure=error;tx.abort();};
   tx.oncomplete=()=>{
    db.close();resolve(result);
    // Notifications are optional hints. A failed channel cannot undo a commit.
    try{this.notifications?.postMessage({object_id:object.id});}catch(error){console.warn('Local commit succeeded; cross-tab notification unavailable',error);}
   };
   tx.onabort=()=>{db.close();reject(failure??tx.error??Error('事务已中止，本次修改尚未保存'));};
   const currentRequest=tx.objectStore('objects').get(object.id);
   currentRequest.onsuccess=()=>{
    const current=currentRequest.result as LocalObject|undefined;
    if((current?.local_edit_version??0)!==object.local_edit_version){fail(new LocalConflictError());return;}
    if(current&&(current.kind!==object.kind||current.project_id!==object.project_id)){fail(Error('对象类型或所属项目不可改变'));return;}
    const projectRequest=tx.objectStore('projects').get(object.project_id);
    projectRequest.onsuccess=()=>{
     const project=projectRequest.result as Project|undefined;
     if(!project||project.scope!=='SYNTHETIC'||(object.kind==='Run'&&!project.module_snapshot.run_types.some(t=>t.id===object.run_type))){fail(Error('合成项目或模块记录类型无效'));return;}
     const identityRequest=tx.objectStore('meta').get('identity');
     identityRequest.onsuccess=()=>{
      const identity=identityRequest.result as Identity|undefined;if(!identity||identity.scope!=='SYNTHETIC_QA'){fail(Error('请先初始化合成工作区'));return;}
      result={...object,local_edit_version:object.local_edit_version+1};
      const event=!current?'create':object.kind==='Run'&&current.kind==='Run'&&(object.is_highlighted!==current.is_highlighted||object.highlight_note!==current.highlight_note||object.highlight_type!==current.highlight_type)?'highlight':'update';
      const source={workspace_id:identity.workspace_id,device_id:identity.device_id};
      const operation:LocalOperation={id:operationId,project_id:object.project_id,object_id:object.id,object_type:object.kind,operation_type:event,payload:result,known_base_revision:null,local_format_version:1,source,state:'pending',wire_adapter:'NEEDS_WIRE_ADAPTER',created_at:time};
      const audit:LocalAudit={id:auditId,operation_id:operationId,object_id:object.id,project_id:object.project_id,event,local_edit_version:result.local_edit_version,source,created_at:time,local_format_version:1};
      tx.objectStore('objects').put(result);tx.objectStore('operations').add(operation);const last=tx.objectStore('audit').add(audit);
      last.onsuccess=()=>{if(quota){fail(new DOMException('TEST ONLY：模拟配额不足；真实事务回滚，本次修改尚未保存','QuotaExceededError'));}else if(abort){fail(Error('TEST ONLY：写请求后真实事务中止，本次修改尚未保存'));}else tx.commit();};
     };
    };
   };
  });
 }
}
export const localCommands=new LocalCommandService();
