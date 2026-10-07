'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useData} from '@/lib/use-data';
import {viewQuery} from '@/lib/module-ui';
import type {ModuleManifest,RecordData,QueryPage,ViewDefinition} from '../../../../packages/shared/types';
import {Empty,Feedback,Panel,Status,human} from './ui';
import {PageControls} from './query-browser';
import {MetricTrend} from './metric-trend';
const directionNames={maximize:'越高越好',minimize:'越低越好',target_range:'目标区间',informational:'仅供描述'};
export function MetricsView({projectId,module,view={},title='代表性指标'}:{projectId:string;module:ModuleManifest;view?:Partial<ViewDefinition>;title?:string}){
 const [offset,setOffset]=useState(0),[trend,setTrend]=useState(false),params=viewQuery({id:'metrics',...view},'metrics',offset);
 const result=useData<QueryPage<RecordData>>(`/projects/${projectId}/metrics/query?${params}`);
 return <><Panel title={title} action={<button aria-pressed={trend} onClick={()=>setTrend(!trend)}>{trend?'收起时间序列':'查看时间序列'}</button>}><p className="section-copy">仅展示已保存的值及来源。优化方向由模块声明；验证状态、单位或适用条件不同的记录不能直接认定总体最佳。</p><Feedback loading={result.loading} error={result.error}/>{result.data&&(!result.data.items.length?<Empty>尚未保存符合条件的指标。</Empty>:<div className="table-scroll"><table><thead><tr><th>研究记录</th><th>指标</th><th>数值 / 单位</th><th>优化方向</th><th>来源与状态</th></tr></thead><tbody>{result.data.items.map(metric=>{const run=metric.run as RecordData,schema=module.metric_schemas.find(s=>s.id===(metric.metric_schema_id??metric.name)),direction=schema?.optimization_direction??'informational';return <tr key={metric.id}><td><Link href={`/runs/${run.id}`}>{String(run.title)}</Link></td><td>{schema?.name??human(metric.name)}</td><td className="mono">{metric.value==null?'未知':JSON.stringify(metric.value)} {metric.unit==null?'（单位未知）':String(metric.unit)}</td><td>{directionNames[direction]}{direction==='target_range'&&schema?.target_range&&<small> {schema.target_range.join('–')}</small>}</td><td><Status value={metric.status}/><small>{human(metric.source_kind)} · {String(metric.source_location??'来源位置未知')}</small><Link href={`/projects/${projectId}/trace?kind=metrics&id=${metric.id}`}>追踪来源 →</Link></td></tr>;})}</tbody></table></div>)}<PageControls page={result.data} offset={offset} setOffset={setOffset} loading={result.loading}/></Panel>{trend&&<MetricTrend key={JSON.stringify([projectId,module.version,view.metric_ids,view.run_types])} projectId={projectId} module={module} view={view}/>}</>;
}
