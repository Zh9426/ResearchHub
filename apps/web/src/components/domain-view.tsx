'use client';
import {useState} from 'react';
import Link from 'next/link';
import type {ProjectContext,ViewDefinition,QueryPage,RecordData} from '../../../../packages/shared/types';
import {viewQuery} from '@/lib/module-ui';
import {useData} from '@/lib/use-data';
import {Panel,Status,Empty,Feedback} from './ui';
import {RunList} from './run-list';
import {PageControls} from './query-browser';
import {MetricsView} from './best-metrics';
import {Lineage} from './lineage';
export function ViewRecords({view,projectId,kind,title}:{view:ViewDefinition;projectId:string;kind:'runs'|'evidence'|'artifacts';title:string}){
 const [offset,setOffset]=useState(0),query=viewQuery(view,kind,offset),result=useData<QueryPage<RecordData>>(`/projects/${projectId}/${kind}/query?${query}`);
 return <Panel title={title}><Feedback loading={result.loading} error={result.error}/>{result.data&&(kind==='runs'?<RunList rows={result.data.items}/>:result.data.items.length?<div className="compact-list">{result.data.items.map(row=><Link key={row.id} href={kind==='artifacts'?`/api/artifacts/${row.id}/download`:`/projects/${projectId}/trace?kind=evidence&id=${row.id}`}><div><strong>{String(row.title??row.filename)}</strong><small>{String(row.limitations??row.category??'')}</small></div><Status value={row.status}/></Link>)}</div>:<Empty>尚无符合模块筛选条件的记录。</Empty>)}<PageControls page={result.data} offset={offset} setOffset={setOffset} loading={result.loading}/></Panel>;
}
export function DomainView({id,context}:{id:string;context:ProjectContext}){
 const raw=context.module.custom_views.find(v=>(typeof v==='string'?v:v.id)===id),view:ViewDefinition=typeof raw==='object'?raw:{id,name:raw??id};
 const projectId=context.project.id,layout=view.layout_type??'research';
 const registry={runs:()=> <ViewRecords view={view} projectId={projectId} kind="runs" title="研究记录"/>,metrics:()=> <MetricsView module={context.module} projectId={projectId} view={view}/>,evidence:()=> <ViewRecords view={view} projectId={projectId} kind="evidence" title="证据与边界"/>,artifacts:()=> <ViewRecords view={view} projectId={projectId} kind="artifacts" title="研究文件"/>,lineage:()=> <Lineage projectId={projectId}/>,research:()=> <><ViewRecords view={view} projectId={projectId} kind="runs" title="研究记录"/><div className="overview-grid"><ViewRecords view={view} projectId={projectId} kind="evidence" title="关联证据"/><ViewRecords view={view} projectId={projectId} kind="artifacts" title="关联文件"/></div>{Boolean(view.metric_ids?.length)&&<MetricsView module={context.module} projectId={projectId} view={view}/>}</>};
 return <><Panel title={view.name??view.id}><p className="section-copy">{view.description||'此项目使用冻结的模块定义；可在数据管理预览并主动升级模块。'}</p>{!view.layout_type&&<p className="muted">旧版定义未声明筛选条件，以下使用通用研究视图。</p>}</Panel>{(registry[layout==='hardware'||layout==='lab'?'research':layout])()}</>;
}
