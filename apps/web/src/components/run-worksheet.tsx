'use client';
import {useId,useState} from 'react';
import {patch,post} from '@/lib/api';
import type {ModuleManifest,RecordData,RunContext,Schema} from '../../../../packages/shared/types';
import {Panel} from './ui';

function valueText(value:unknown,type:string){return value==null?'':typeof value==='object'?JSON.stringify(value,null,2):String(value);}
export function parseScientificValue(raw:string,type:string):unknown {
 if(!raw.trim())return null;
 if(type==='number'||type==='integer') {const n=Number(raw);if(!Number.isFinite(n)||type==='integer'&&!Number.isInteger(n))throw new Error('请填写有效数值；未知值留空');return n;}
 if(type==='boolean'){if(raw==='true')return true;if(raw==='false')return false;throw new Error('请选择真或假');}
 if(type==='object'||type==='array'){const parsed=JSON.parse(raw);if(parsed===null)return null;if(type==='array'?!Array.isArray(parsed):typeof parsed!=='object'||Array.isArray(parsed))throw new Error('结构值的类型不正确');return parsed;}
 return raw;
}
function ValueField({schema,value,unit}:{schema:Schema;value:unknown;unit?:string|null}){
 const id=useId(),type=schema.value_type,label=`${schema.name}${unit?` (${unit})`:''}${schema.required?' *':''}`;
 const accessible={'aria-labelledby':`${id}-label`,'aria-describedby':`${id}-help`};
 return <label className="field"><span id={`${id}-label`}>{label}</span>{type==='object'||type==='array'?<textarea {...accessible} name={schema.id} required={schema.required} rows={3} defaultValue={valueText(value,type)}/>:type==='boolean'?<select {...accessible} name={schema.id} defaultValue={valueText(value,type)}><option value="">未知</option><option value="true">真</option><option value="false">假</option></select>:<input {...accessible} name={schema.id} type={type==='string'?'text':'number'} step={type==='integer'?'1':'any'} required={schema.required} defaultValue={valueText(value,type)}/>}<small id={`${id}-help`}>{schema.help_text||schema.description||'未知值留空，不代表零。'}</small></label>;
}
function WorksheetSection({title,kind,fields,context,onChange}:{title:string;kind:'context'|'parameters'|'metrics';fields:Schema[];context:RunContext;onChange:()=>void}) {
 const [saving,setSaving]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const entries=kind==='parameters'?context.worksheet_parameters??context.parameters:kind==='metrics'?context.worksheet_metrics??context.metrics:[];
 const incomplete=kind==='parameters'?context.worksheet_parameters_incomplete:kind==='metrics'?context.worksheet_metrics_incomplete:false;
 const values=context.run.context_data as Record<string,unknown>??{};
 return <Panel title={title} className="worksheet-section"><form onSubmit={async e=>{e.preventDefault();setSaving(true);setError('');setMessage('');try{
  if(incomplete)throw new Error('表单数据未完整加载，禁止批量保存；请逐项编辑或联系维护者。');
  const data=new FormData(e.currentTarget),updated=Object.fromEntries(fields.map(s=>[s.id,parseScientificValue(String(data.get(s.id)??''),s.value_type)]));
  if(kind==='context')await patch(`/runs/${context.run.id}`,{context_data:{...values,...updated}});
  else {
   const payload=fields.map(s=>{const existing=entries.find(x=>x.name===s.id);const unchanged=JSON.stringify(existing?.value??null)===JSON.stringify(updated[s.id]),provenance={source_kind:existing?.source_kind??'unknown',source_id:existing?.source_id??null,source_location:existing?.source_location??null,uncertainty:existing?.uncertainty??null,valid_conditions:existing?.valid_conditions??null};return kind==='parameters'?{name:s.id,value:updated[s.id],value_type:s.value_type,unit:existing?existing.unit:s.unit,...provenance,is_confirmed:false}:{name:s.id,value:updated[s.id],unit:existing?existing.unit:s.unit,...provenance,derivation:existing?.derivation??null,artifact_ids:existing?.artifact_ids??[],metric_schema_id:s.id,status:unchanged?existing?.status??'unknown':'unknown'};});
   await post(`/runs/${context.run.id}/${kind}/batch`,{[kind]:payload});
  }
  setMessage('已保存');onChange();
 }catch(err){setError((err as Error).message);}finally{setSaving(false);}}}>
  <div className="form-grid">{fields.map(s=>{const existing=entries.find(x=>x.name===s.id);return <ValueField key={`${s.id}-${context.run.updated_at}`} schema={s} value={kind==='context'?values[s.id]:existing?existing.value:s.default} unit={String((existing?existing.unit:s.unit)??'')}/>;})}</div>
  {kind==='parameters'&&<p className="muted">按当前单位保存，保留已填来源；本表单保存为未确认参数。人工确认请进入“逐项编辑参数与来源”。</p>}
  {kind==='metrics'&&<p className="muted">修改数值后恢复为未知验证状态；需要验证或复现标记时请逐项编辑。</p>}
  {incomplete&&<p className="error" role="alert">表单字段超过加载上限，已禁止批量保存以保留原数据。</p>}{error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}<div className="heading-actions"><button className="primary" disabled={saving||incomplete}>{saving?'正在保存…':'保存此组'}</button></div>
 </form></Panel>;
}
export function RunWorksheet({context,module,onChange,kinds=['context','parameters','metrics']}:{context:RunContext;module:ModuleManifest;onChange:()=>void;kinds?:('context'|'parameters'|'metrics')[]}) {
 const form=module.run_forms?.find(f=>f.run_type===context.run.run_type);
 const groups=form?.groups??[{id:'parameters',name:'输入参数与来源',fields:module.parameter_schemas.map(s=>s.id)},{id:'metrics',name:'输出指标',fields:module.metric_schemas.map(s=>s.id)}];
 return <div className="run-worksheet">{groups.map(group=>{
  const sections=([{kind:'context',schemas:module.context_fields??[]},{kind:'parameters',schemas:module.parameter_schemas},{kind:'metrics',schemas:module.metric_schemas}] as const).filter(({kind})=>kinds.includes(kind)).map(({kind,schemas})=>({kind,fields:schemas.filter(s=>group.fields.includes(s.id)).sort((a,b)=>(a.order??0)-(b.order??0))})).filter(x=>x.fields.length);
  if(!sections.length)return null;
  const body=sections.map(({kind,fields})=><WorksheetSection key={kind} title={sections.length===1?group.name:`${group.name} · ${kind==='context'?'条件':kind==='parameters'?'参数':'指标'}`} kind={kind} fields={fields} context={context} onChange={onChange}/>);
  return group.visibility==='advanced'?<details key={group.id} className="more-details"><summary>{group.name}</summary>{body}</details>:<div key={group.id}>{body}</div>;
 })}</div>;
}
