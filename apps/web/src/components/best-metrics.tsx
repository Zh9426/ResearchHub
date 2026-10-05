'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {api} from '@/lib/api';
import type {RecordData,ProjectContext} from '../../../../packages/shared/types';
import {Empty,Feedback,Panel,Status,human} from './ui';
export function BestMetrics({context}:{context:ProjectContext}){
 const [rows,setRows]=useState<{run:RecordData;metric:RecordData}[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{let active=true;setLoading(true);setError('');Promise.all(context.runs.map(async run=>({run,metrics:await api<RecordData[]>(`/runs/${run.id}/metrics`)}))).then(data=>{if(active)setRows(data.flatMap(({run,metrics})=>metrics.map(metric=>({run,metric}))));}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[context.runs]);
 const scientific=['IoU','coverage','Energy Efficiency','over_cure','under_cure'];
 return <Panel title="关键指标与优化进度"><p className="section-copy">同时评估固化质量、过固化、欠固化与能量效率。这里只展示已保存的指标，不自动推断总体最佳方案。</p><Feedback loading={loading} error={error}/>{!loading&&!error&&(!rows.length?<Empty>暂无已保存指标。进入研究记录填写指标与证据状态。</Empty>:<div className="table-scroll"><table><thead><tr><th>研究记录</th><th>指标</th><th>数值</th><th>证据状态</th></tr></thead><tbody>{rows.filter(({metric})=>scientific.includes(String(metric.name))||scientific.includes(String(metric.metric_schema_id))).slice(0,16).map(({run,metric})=><tr key={metric.id}><td><Link href={`/runs/${run.id}`}>{String(run.title)}</Link></td><td>{human(metric.name)}</td><td className="mono">{JSON.stringify(metric.value)} {String(metric.unit??'')}</td><td><Status value={metric.status}/></td></tr>)}</tbody></table></div>)}</Panel>
}
