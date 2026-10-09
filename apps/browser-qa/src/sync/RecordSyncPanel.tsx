import {useEffect,useState} from 'react';
import type {LocalObject} from '../local/model';
import type {RecordSyncStatus} from './status';
export function RecordSyncPanel({draft,dirty,read,refreshToken,pc}:{draft:LocalObject;dirty:boolean;read:(object:LocalObject)=>Promise<RecordSyncStatus>;refreshToken:unknown;pc?:boolean}){
 const [status,setStatus]=useState<RecordSyncStatus|null>(null),[error,setError]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;setStatus(null);setError(false);void read(draft).then(value=>{if(active)setStatus(value);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[draft.id,draft.local_edit_version,read,refreshToken,retry]);
 const conversion:Record<string,string>={NOT_CONVERTED:'等待转换',PREPARED:'已准备，尚未封装',CONVERTED:'已转换，尚未封装',SEALED:'已封装',BLOCKED:'受阻，需检查授权或诊断',NOT_APPLICABLE:'没有本地发送操作'};
 return <section aria-label="当前记录同步状态" data-testid="record-sync-status"><h3>当前记录同步状态</h3>{dirty&&<p>当前输入尚未保存；下列状态仅属于最近一次已保存的本地修改。</p>}{error?<p role="alert">状态读取失败。<button onClick={()=>setRetry(v=>v+1)}>刷新记录状态</button></p>:!status?<p>读取持久状态…</p>:<>
 <p data-testid="record-sync-local">本机：{status.local==='SAVED'?`已保存本地修改 v${status.local_version}`:'没有本地发送操作；可信记录可继续编辑'}</p>
 <p data-testid="record-sync-conversion">转换与封装：{conversion[status.conversion]??'状态待核对'}</p>
 <p data-testid="record-sync-relay">Relay 传输：{status.transport==='RELAY_STORED'?'已存储这次修改':status.transport==='NOT_SENT'?'这次修改尚未确认存储':status.transport==='BLOCKED'?'发送受阻':'没有本地发送操作'}</p>
 <p data-testid="record-sync-peer">对端应用：{status.target_device_id?`${pc?'浏览器设备':'PC 设备'} ${status.target_device_id.slice(0,8)} · `:''}{status.peer==='VERIFIED'?'已验证该设备应用了这次修改':'这次修改尚未确认对端应用'}</p>
 <p data-testid="record-sync-review">科研审核：尚未请求科研批准。{status.current_record==='CONFLICTED'?'当前记录存在冲突，需比较候选。':status.current_record==='CANDIDATE'?'当前记录为候选，尚未接纳。':status.current_record==='ACCEPTED'?'当前为内核接纳的普通记录。':''}应用回执仅记录历史提交事实。</p>
 <details><summary>当前记录同步诊断</summary><pre>{JSON.stringify(status,null,2)}</pre></details>
 </>}</section>;
}
