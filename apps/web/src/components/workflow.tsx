'use client';
import {provenanceLabel} from '@/lib/zh';
import {useState} from 'react';
import type {ProjectContext} from '../../../../packages/shared/types';
import {patch} from '@/lib/api';
import {resourceFields} from '@/lib/fields';
import {Panel,ResourceList,Status,human} from './ui';
export function Workflow({context,onChange}:{context:ProjectContext;onChange:()=>void}){
 const [error,setError]=useState('');
 return <><Panel title="研究阶段"><p className="section-copy">研究阶段来自项目模块；关卡的判据、证据与阻塞原因独立保存。</p><div className="stage-choice-list">{context.module.research_stages.map(stage=><article key={stage.id}><div><strong>{stage.id} · {stage.name}</strong><p>{stage.description}</p></div>{context.project.current_stage===stage.id?<Status value="in_progress"/>:<button onClick={async()=>{try{await patch(`/projects/${context.project.id}`,{current_stage:stage.id});onChange();}catch(e){setError((e as Error).message);}}}>设为当前研究阶段</button>}</article>)}</div>{error&&<p className="error" role="alert">{error}</p>}</Panel><ResourceList title="阶段关卡与判据" collection="gates" rows={context.gates} fields={resourceFields('gates',context,context.module)} createPath={`/projects/${context.project.id}/gates`} onChange={onChange}/><Panel title="关卡判据与证据"><div className="criteria-list">{context.gates.map(gate=><section key={gate.id}><h3>{String(gate.gate_id)} · {human(gate.name)}</h3>{(gate.criteria as {id:string;description:string;status:string;provenance:string;evidence_ids:string[]}[]??[]).map(c=><div key={c.id}><strong>{c.id} {c.description}</strong><Status value={c.status}/><small>来源依据: {provenanceLabel(c.provenance)} · 证据 {c.evidence_ids?.length??0}</small></div>)}</section>)}</div></Panel></>;
}
