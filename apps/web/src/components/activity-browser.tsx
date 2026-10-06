'use client';
import {useDeferredValue,useState} from 'react';
import {useData} from '@/lib/use-data';
import {post} from '@/lib/api';
import type {QueryPage,RecordData} from '../../../../packages/shared/types';
import {Panel,Feedback} from './ui';
import {ActivityList} from './activity';
import {PageControls} from './query-browser';
export function ActivityBrowser({projectId}:{projectId?:string}) {
 const [view,setView]=useState('activity'),[range,setRange]=useState('30'),[actor,setActor]=useState(''),[resource,setResource]=useState(''),[action,setAction]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const query=useDeferredValue(q),params=new URLSearchParams({format:'page',limit:'25',offset:String(offset),range,q:query});
 if(projectId)params.set('project_id',projectId);
 for(const [key,value] of Object.entries({actor_type:actor,resource_type:resource,action}))if(value)params.set(key,value);
 const result=useData<QueryPage<RecordData>>(`/${view}?${params}`),filter=(fn:()=>void)=>{fn();setOffset(0);};
 return <Panel title={view==='audit'?'审计历史':'最近活动'} action={view==='activity'?<button disabled={busy} onClick={async()=>{if(!confirm('隐藏当前项目或全局已有的活动展示？审计历史始终保留且可以导出。'))return;setBusy(true);setError('');try{await post('/activity/clear',{project_id:projectId??null,confirm:true});result.refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>清除展示历史</button>:<a className="button" href={`/api/audit/export?${new URLSearchParams({...(projectId?{project_id:projectId}:{}),format:'jsonl'})}`}>导出审计</a>}>
  <p className="section-copy">活动便于查看最近操作；审计保留完整科研来源、操作方和修改前后记录。</p>
  <div className="query-toolbar"><label className="field"><span>查看</span><select value={view} onChange={e=>filter(()=>setView(e.target.value))}><option value="activity">活动展示</option><option value="audit">审计历史（始终保留）</option></select></label><label className="field"><span>搜索</span><input type="search" value={q} onChange={e=>filter(()=>setQ(e.target.value))}/></label><label className="field"><span>时间范围</span><select value={range} onChange={e=>filter(()=>setRange(e.target.value))}>{[['7','最近 7 天'],['30','最近 30 天'],['90','最近 90 天'],['all','全部时间']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label><label className="field"><span>操作方</span><select value={actor} onChange={e=>filter(()=>setActor(e.target.value))}>{[['','全部操作方'],['human','人工'],['codex','Codex'],['chatgpt','ChatGPT'],['system','系统']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label><label className="field"><span>资源</span><select value={resource} onChange={e=>filter(()=>setResource(e.target.value))}>{[['','全部资源'],['research_runs','研究记录'],['evidence','证据'],['artifacts','文件'],['parameters','参数'],['metrics','指标'],['tasks','任务'],['stage_gates','关卡'],['projects','项目']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label><label className="field"><span>操作</span><select value={action} onChange={e=>filter(()=>setAction(e.target.value))}>{[['','全部操作'],['create_runs','创建研究记录'],['update_runs','修改研究记录'],['set_run_highlight','设置星标'],['create_evidence','新增证据'],['update_evidence','更新证据'],['trash_runs','记录移入回收站'],['restore_runs','恢复记录'],['upload_artifact','上传文件']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label></div>
  <Feedback loading={result.loading} error={result.error||error}/>{result.data&&<ActivityList rows={result.data.items}/>}<PageControls page={result.data} offset={offset} setOffset={setOffset} loading={result.loading}/>
 </Panel>;
}
