'use client';
import {useState,useDeferredValue} from 'react';
import Link from 'next/link';
import type {ProjectContext,RunContext,QueryPage,RecordData} from '../../../../packages/shared/types';
import {useData} from '@/lib/use-data';
import {Panel,Status,Feedback} from './ui';
import {RunDiff} from './scientific-values';
import {PageControls} from './query-browser';
function RunPicker({projectId,label,value,onChange}:{projectId:string;label:string;value:string;onChange:(id:string)=>void}){
 const [q,setQ]=useState(''),[offset,setOffset]=useState(0),deferred=useDeferredValue(q),result=useData<QueryPage<RecordData>>(`/projects/${projectId}/runs/query?limit=25&offset=${offset}&q=${encodeURIComponent(deferred)}`);
 return <div><label className="field"><span>{label} · 搜索</span><input value={q} type="search" onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label><label className="field"><span>{label}</span><select value={value} onChange={e=>onChange(e.target.value)}><option value="">选择研究记录</option>{value&&!result.data?.items.some(row=>row.id===value)&&<option value={value}>已选择 #{value.slice(0,8)}</option>}{result.data?.items.map(row=><option key={row.id} value={row.id}>{String(row.title)}</option>)}</select></label><Feedback loading={result.loading} error={result.error}/><PageControls page={result.data} offset={offset} setOffset={setOffset} loading={result.loading}/></div>;
}
export function Compare({context}:{context:ProjectContext}){
 const [a,setA]=useState(''),[b,setB]=useState(''),left=useData<RunContext>(a?`/runs/${a}/context`:null),right=useData<RunContext>(b?`/runs/${b}/context`:null);
 return <><Panel title="研究记录比较"><div className="comparison-selector"><RunPicker projectId={context.project.id} label="参考记录" value={a} onChange={setA}/><RunPicker projectId={context.project.id} label="当前记录" value={b} onChange={setB}/></div>{a===b&&a&&<p className="boundary">请选择两个不同的研究记录。</p>}</Panel><Feedback loading={left.loading||right.loading} error={left.error||right.error}/>{a&&b&&a!==b&&left.data&&right.data&&<><Panel title="状态与结论"><div className="comparison-heads">{[left.data,right.data].map((x,i)=><div key={i}><h3><Link href={`/runs/${x.run.id}`}>{String(x.run.title)}</Link></h3><Status value={x.run.status}/><p>科研结果：<Status value={x.run.scientific_outcome}/></p><p><strong>人工结论</strong><br/>{String(x.run.human_conclusion||'尚未填写')}</p></div>)}</div></Panel><RunDiff key={`p-${a}-${b}`} runId={b} otherRunId={a} kind="parameters"/><RunDiff key={`m-${a}-${b}`} runId={b} otherRunId={a} kind="metrics"/></>}</>;
}
