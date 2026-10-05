'use client';
import {useState} from 'react';
import type {ProjectContext} from '../../../../packages/shared/types';
import {patch} from '@/lib/api';
import {resourceFields} from '@/lib/fields';
import {Panel,ResourceList,Status} from './ui';
export function Workflow({context,onChange}:{context:ProjectContext;onChange:()=>void}){
 const [error,setError]=useState('');
 return <><Panel title="Research Stages"><p className="section-copy">Stage 来自 Project Module；Gate 的判据、证据与阻塞原因独立保存。</p><div className="stage-choice-list">{context.module.research_stages.map(stage=><article key={stage.id}><div><strong>{stage.id} · {stage.name}</strong><p>{stage.description}</p></div>{context.project.current_stage===stage.id?<Status value="in_progress"/>:<button onClick={async()=>{try{await patch(`/projects/${context.project.id}`,{current_stage:stage.id});onChange();}catch(e){setError((e as Error).message);}}}>设为当前 Stage</button>}</article>)}</div>{error&&<p className="error" role="alert">{error}</p>}</Panel><ResourceList title="Stage Gates / Criteria" collection="gates" rows={context.gates} fields={resourceFields('gates',context,context.module)} createPath={`/projects/${context.project.id}/gates`} onChange={onChange}/><Panel title="Gate Criteria / Evidence"><div className="criteria-list">{context.gates.map(gate=><section key={gate.id}><h3>{String(gate.gate_id)} · {String(gate.name)}</h3>{(gate.criteria as {id:string;description:string;status:string;provenance:string;evidence_ids:string[]}[]??[]).map(c=><div key={c.id}><strong>{c.id} {c.description}</strong><Status value={c.status}/><small>Provenance: {c.provenance} · Evidence {c.evidence_ids?.length??0}</small></div>)}</section>)}</div></Panel></>;
}
