import type { ProjectContext, RecordData, ModuleManifest } from '../../../../packages/shared/types';
import {zh} from './zh';
export type FieldKind = 'text'|'textarea'|'select'|'multi'|'json'|'boolean'|'date'|'datetime-local'|'number'|'criteria';
export interface Field {key:string;label:string;kind?:FieldKind;required?:boolean;options?:{value:string;label:string}[];default?:unknown;hint?:string;}
export const options = (values:string[]) => values.map(value=>({value,label:zh(value)}));
export const evidenceStatuses = ['unknown','hypothesis','assumed','synthetic','simulated','measured','calibrated','validated','reproduced','rejected'];
export const sourceKinds = ['unknown','synthetic','assumed','literature','manufacturer','measured','calibrated','derived'];
export const f = (key:string,label:string,kind:FieldKind='text',extra:Partial<Field>={}):Field=>({key,label,kind,...extra});
export function localDateTime(value:unknown):string {if(!value)return '';const date=new Date(String(value));if(Number.isNaN(date.getTime()))return '';return new Date(date.getTime()-date.getTimezoneOffset()*60_000).toISOString().slice(0,16);}
const status = (values:string[],value?:string) => f('status','状态','select',{options:options(values),default:value??values[0]});
const title = f('title','标题','text',{required:true});
const description = f('description','描述','textarea');
export function linkOptions(rows:RecordData[]) {return rows.map(x=>({value:x.id,label:String(x.title??x.name??x.id)}));}
export function resourceFields(collection:string,ctx?:ProjectContext,manifest?:ModuleManifest):Field[] {
  const link=(key:string,label:string,rows:RecordData[]|undefined,multiple=false)=>f(key,label,multiple?'multi':'select',{options:linkOptions(rows??[])});
  switch(collection) {
    case 'projects': return [f('name','项目名称','text',{required:true}),description,f('module_id','项目类型','select',{required:true}),status(['active','paused','completed','archived','blocked']),f('current_stage',"当前研究阶段"),f('current_objective','当前目标','textarea')];
    case 'runs': return [title,f('run_type',"研究记录类型",'select',{required:true,options:(manifest?.run_types??[]).map(x=>typeof x==='string'?{value:x,label:zh(x)}:{value:x.id,label:zh(x.name)})}),link('parent_run_id',"基于父记录",ctx?.runs),f('objective',"研究目标",'textarea'),f('hypothesis',"研究假设",'textarea'),status(['planned','running','completed','failed','cancelled','blocked']),f('scientific_outcome',"科研结果",'select',{options:options(['unknown','positive_result','negative_result','inconclusive','candidate_rejected']),default:'unknown',hint:'负结果或候选否决是科研结果，独立于软件运行状态。'}),f('changes_from_parent',"相对父记录的变化",'textarea'),f('protocol',"研究方案",'textarea'),f('observation',"观察记录",'textarea'),f('ai_analysis',"AI 分析",'textarea',{hint:'AI 分析与人工结论分别保存。'}),f('human_conclusion',"人工结论",'textarea'),f('next_step',"下一步",'textarea'),f('environment',"运行环境",'textarea'),f('software_version',"软件版本"),f('code_revision',"代码版本"),f('started_at','开始时间','datetime-local'),f('completed_at','完成时间','datetime-local')];
    case 'questions':return [title,description,status(['open','investigating','answered','closed'])];
    case 'hypotheses':return [f('statement',"假设陈述",'textarea',{required:true}),link('research_question_id',"研究问题",ctx?.questions),status(['proposed','testing','supported','rejected','inconclusive']),f('evidence_status',"证据状态",'select',{options:options(evidenceStatuses),default:'unknown'})];
    case 'tasks':return [title,description,status(['todo','doing','blocked','done']),f('priority','优先级','select',{options:options(['low','medium','high','critical']),default:'medium'}),link('milestone_id',"里程碑",ctx?.milestones),f('due_date','截止日期','date')];
    case 'milestones':return [title,description,status(['not_started','in_progress','completed','blocked']),f('target_date','目标日期','date'),f('completed_at','完成时间','datetime-local')];
    case 'sources':return [title,description,f('source_kind',"来源类别",'select',{options:options(sourceKinds),default:'unknown'}),f('url','URL'),f('doi','DOI'),f('source_location','来源位置'),f('citation',"文献引用",'textarea')];
    case 'evidence':return [title,description,f('evidence_type',"证据类型",'select',{options:options(['simulation','measurement','literature','artifact','observation','other']),default:'observation'}),status(evidenceStatuses),link('linked_run_id',"关联研究记录",ctx?.runs),link('linked_artifact_id',"关联文件",ctx?.artifacts),link('linked_source_id',"关联来源",ctx?.sources),f('limitations',"限制与证据边界",'textarea')];
    case 'claims':return [f('title',"论断标题"),f('statement',"科研论断",'textarea',{required:true}),status(['draft','supported','rejected','inconclusive']),link('evidence_ids',"证据",ctx?.evidence,true),link('run_ids',"研究记录",ctx?.runs,true),link('artifact_ids',"研究文件",ctx?.artifacts,true),link('source_ids',"来源",ctx?.sources,true),f('limitations',"适用限制",'textarea')];
    case 'notes':return [title,link('run_id',"关联研究记录",ctx?.runs),f('content','记录内容','textarea',{required:true})];
    case 'decisions':return [title,f('context',"决策背景",'textarea'),f('decision',"决策内容",'textarea',{required:true}),f('reason',"理由",'textarea'),f('alternatives',"备选方案",'textarea'),status(['proposed','accepted','superseded','rejected']),link('run_id',"关联研究记录",ctx?.runs),link('evidence_ids',"关联证据",ctx?.evidence,true)];
    case 'risks':return [title,description,status(['open','mitigated','closed']),f('severity','严重程度','select',{options:options(['low','medium','high','critical']),default:'medium'}),f('mitigation',"缓解措施",'textarea')];
    case 'gates':return [f('gate_id',"关卡编号",'text',{required:true}),f('name',"关卡名称",'text',{required:true}),f('stage_id',"研究阶段",'select',{options:(manifest?.research_stages??[]).map(s=>({value:s.id,label:s.name}))}),description,status(['not_started','in_progress','passed','failed','blocked']),f('criteria',"判据与来源",'criteria',{default:[],options:linkOptions(ctx?.evidence??[]),hint:'逐条更新判据状态和证据；保留来源边界。'}),link('evidence_ids',"关联证据",ctx?.evidence,true),f('blocking_reason',"阻塞原因",'textarea')];
    case 'parameters':return [f('name','参数名称','text',{required:true}),f('value_type','类型','select',{options:options(['number','integer','string','boolean','object','array']),default:'number'}),f('value','值','json',{default:null,hint:'支持 null 表示未知；数值输入 JSON 数字，字符串使用双引号。'}),f('unit','单位'),f('source_kind','来源类别','select',{options:options(sourceKinds),default:'unknown'}),link('source_id','来源记录',ctx?.sources),f('source_location','来源位置'),f('uncertainty',"不确定度"),f('valid_conditions',"适用条件",'textarea'),f('is_confirmed','已确认','boolean',{default:false})];
    case 'metrics':return [f('name','指标名称','text',{required:true}),f('value','值','json',{default:null}),f('unit','单位'),f('metric_schema_id',"指标模板",'select',{options:(manifest?.metric_schemas??[]).map(x=>({value:x.id,label:zh(x.name)}))}),status(evidenceStatuses)];
    default:return [];
  }
}
export function parseFields(fields:Field[],form:HTMLFormElement):Record<string,unknown> {
  const data=new FormData(form),result:Record<string,unknown>={};
  for(const field of fields) {
    if(field.kind==='multi') {result[field.key]=data.getAll(field.key).filter(Boolean);continue;}
    if(field.kind==='boolean') {result[field.key]=data.has(field.key);continue;}
    const raw=String(data.get(field.key)??'').trim();
    if(field.required&&!raw) throw new Error(`${field.label} 为必填项`);
    if(field.kind==='json'||field.kind==='criteria') {try {result[field.key]=raw?JSON.parse(raw):null;}catch {throw new Error(`${field.label} 需要有效 JSON`);}continue;}
    if(field.kind==='number') {result[field.key]=raw?Number(raw):null;continue;}
    if(field.kind==='datetime-local') {result[field.key]=raw?new Date(raw).toISOString():null;continue;}
    const nullable=field.key.endsWith('_id')||['unit','source_location','uncertainty','valid_conditions','url','doi','current_stage','started_at','completed_at','target_date','due_date'].includes(field.key);
    result[field.key]=raw||(nullable?null:'');
  }
  return result;
}
