'use client';
import Link from 'next/link';
import type {ReactNode} from 'react';
import type {ProjectSummary,RecordData,WidgetDefinition} from '../../../../packages/shared/types';
import {widgetDefinitions} from '@/lib/module-ui';
import {useData} from '@/lib/use-data';
import {Panel,Status,Empty,Feedback} from './ui';
import {RunList} from './run-list';
import {ActivityList} from './activity';
import {MetricsView} from './best-metrics';
import {ViewRecords} from './domain-view';
function RecentActivity({projectId,title}:{projectId:string;title:string}){
 const data=useData<RecordData[]>(`/activity?project_id=${projectId}&limit=5`);return <Panel title={title} action={<Link href={`/projects/${projectId}/timeline`}>查看全部 →</Link>}><Feedback loading={data.loading} error={data.error}/>{data.data&&<ActivityList rows={data.data}/>}</Panel>;
}
function SummaryRows({rows,href}:{rows:RecordData[];href:string}){return rows.length?<div className="compact-list">{rows.map(row=><Link href={href} key={row.id}><div><strong>{String(row.title??row.name)}</strong><small>{String(row.description??row.decision??row.blocking_reason??'')}</small></div><Status value={row.status}/></Link>)}</div>:<Empty>暂无记录。</Empty>;}
function Widget({definition,summary}:{definition:WidgetDefinition;summary:ProjectSummary}){
 const {project,module}=summary,href=`/projects/${project.id}`,title=definition.name??definition.kind;
 const registry:Record<string,()=>ReactNode>={
  objective:()=> <Panel title={title}><p className="objective-copy">{String(project.current_objective||project.description||'尚未填写当前目标')}</p><div className="boundary">{project.is_demo?'DEMO / SYNTHETIC · 合成输入不能作为真实科研结果。':'科研判断以关联证据、来源与适用条件为依据。'}</div><p className="muted">{summary.counts.questions??0} 个研究问题 · {summary.counts.runs??0} 条研究记录</p></Panel>,
  stage_gates:()=>{const stage=module.research_stages.find(s=>s.id===project.current_stage);return <Panel title={title} action={<Link href={`${href}/workflow`}>工作流 →</Link>}><div className="stage-list"><article><span className="stage-dot"/><div><strong>{stage?.name??'尚未选择阶段'}</strong><p>{stage?.description??'可在项目设置选择当前阶段。'}</p></div><Status value={project.status}/></article>{summary.current_gates.map(g=><article key={g.id}><span className={`stage-dot ${g.status==='blocked'?'blocked-dot':''}`}/><div><strong>{String(g.gate_id)} · {String(g.name)}</strong>{Boolean(g.blocking_reason)&&<p className="blocking">{String(g.blocking_reason)}</p>}</div><Status value={g.status}/></article>)}</div></Panel>;},
  highlighted_runs:()=> <Panel title={title}><RunList rows={summary.highlighted_runs}/></Panel>,
  recent_runs:()=> <Panel title={title} action={<Link href={`${href}/runs`}>查看全部 →</Link>}><RunList rows={summary.recent_runs}/></Panel>,
  representative_metrics:()=> <MetricsView projectId={project.id} module={module} view={definition} title={title}/>,
  validation:()=> <ViewRecords view={definition} projectId={project.id} kind="evidence" title={title}/>,
  current_tasks:()=> <Panel title={title} action={<Link href={`${href}/tasks`}>全部任务 →</Link>}><SummaryRows rows={summary.current_tasks} href={`${href}/tasks`}/></Panel>,
  evidence_summary:()=> <Panel title={title}><div className="evidence-counts">{Object.entries(summary.evidence_summary).map(([status,count])=><div key={status}><Status value={status}/><strong>{count}</strong></div>)}</div>{!Object.keys(summary.evidence_summary).length&&<Empty>暂无证据。</Empty>}<Link href={`${href}/evidence`}>{summary.counts.evidence??0} 条证据 · 查看边界与追踪 →</Link></Panel>,
  open_risks:()=> <Panel title={title}><SummaryRows rows={summary.current_risks} href={`${href}/research`}/></Panel>,
  recent_decisions:()=> <Panel title={title}><SummaryRows rows={summary.current_decisions} href={`${href}/decisions`}/></Panel>,
  recent_activity:()=> <RecentActivity projectId={project.id} title={title}/>
 };
 return registry[definition.kind]?.()??<Panel title={title}><p className="muted">当前客户端不支持此组件：{definition.kind}。请检查模块版本。</p></Panel>;
}
export function Overview({summary}:{summary:ProjectSummary}){return <div className="dashboard-registry">{widgetDefinitions(summary.module).map(definition=><div key={definition.id} className={['recent_runs','highlighted_runs','representative_metrics','recent_activity'].includes(definition.kind)?'dashboard-wide':''}><Widget definition={definition} summary={summary}/></div>)}</div>;}
