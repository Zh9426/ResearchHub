'use client';
import {useState} from 'react';
import {patch} from '@/lib/api';
import type {RecordData} from '../../../../packages/shared/types';
import {Panel} from './ui';
export function RunProgress({run,capability,onChange}:{run:RecordData;capability?:string|null;onChange:()=>void}) {
 const [busy,setBusy]=useState(false),[error,setError]=useState('');const code=capability==='code_simulation'||capability==='data_analysis';
 const fields=code?[['environment','运行环境'],['software_version','软件版本'],['code_revision','代码版本'],['observation','观察记录'],['human_conclusion','人工结论（由你确认）'],['next_step','下一步']]:[['protocol','研究方案 / 实验步骤'],['observation','观察记录'],['human_conclusion','人工结论（由你确认）'],['next_step','下一步']];
 return <Panel title={code?'运行与观察':'过程、观察与人工结论'} className="worksheet-section"><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const data=new FormData(e.currentTarget);await patch(`/runs/${run.id}`,Object.fromEntries([...fields.map(([key])=>[key,String(data.get(key)??'')]),['status',data.get('status')],['scientific_outcome',data.get('scientific_outcome')]]));onChange();}catch(err){setError((err as Error).message);}finally{setBusy(false);}}}>
  <div className="form-grid">{fields.map(([key,label])=><label key={`${key}-${run.updated_at}`} className={`field ${key==='observation'?'field-wide':''}`}><span>{label}</span><textarea name={key} rows={key==='observation'?4:2} defaultValue={String(run[key]??'')}/></label>)}<label className="field"><span>运行状态</span><select name="status" defaultValue={String(run.status)}>{[['planned','计划中'],['running','进行中'],['completed','已完成'],['failed','运行失败'],['cancelled','已取消'],['blocked','受阻']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label><label className="field"><span>科研结果</span><select name="scientific_outcome" defaultValue={String(run.scientific_outcome??'unknown')}>{[['unknown','未知'],['positive_result','正结果'],['negative_result','负结果'],['inconclusive','暂不确定'],['candidate_rejected','候选否决']].map(([v,label])=><option value={v} key={v}>{label}</option>)}</select><small>负结果可标记“已完成”；不等同于运行失败。</small></label></div>{error&&<p role="alert" className="error">{error}</p>}<button className="primary" disabled={busy}>{busy?'正在保存…':'保存过程记录'}</button>
 </form></Panel>;
}
