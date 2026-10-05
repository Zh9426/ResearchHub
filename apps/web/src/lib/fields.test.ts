import {describe,it,expect} from 'vitest';
import {parseFields,resourceFields,localDateTime,f,evidenceStatuses} from './fields';
function form(values:Record<string,string>) {const el=document.createElement('form');for(const [name,value] of Object.entries(values)){const input=document.createElement('input');input.name=name;input.value=value;el.append(input);}return el;}
describe('科研表单边界',()=>{
  it('未知参数以 null 与 unknown 保存，无自动伪造值',()=>{const fields=resourceFields('parameters');expect(fields.find(x=>x.key==='source_kind')?.default).toBe('unknown');expect(parseFields(fields,form({name:'frequency',value:'null',value_type:'number',source_kind:'unknown'})).value).toBeNull();});
  it('JSON 数值与布尔类型保留',()=>{const fields=resourceFields('parameters');expect(parseFields(fields,form({name:'beta',value:'0.5',value_type:'number'})).value).toBe(0.5);expect(parseFields(fields,form({name:'enabled',value:'false',value_type:'boolean'})).value).toBe(false);});
  it('无效 JSON 与空必填字段产生具体错误',()=>{expect(()=>parseFields(resourceFields('parameters'),form({name:'frequency',value:'unquoted'}))).toThrow('有效 JSON');expect(()=>parseFields(resourceFields('notes'),form({content:'a'}))).toThrow('标题');});
  it('Claim 与 Decision 保留多条 evidence 关系',()=>{expect(resourceFields('claims').find(x=>x.key==='evidence_ids')?.kind).toBe('multi');expect(resourceFields('decisions').find(x=>x.key==='evidence_ids')?.kind).toBe('multi');});
  it('datetime-local 按用户时区转为 UTC，编辑重新显示本地组件',()=>{const raw='2026-10-05T09:30';const saved=parseFields([f('started_at','Started','datetime-local')],form({started_at:raw}));expect(saved.started_at).toBe(new Date(raw).toISOString());expect(localDateTime(saved.started_at)).toBe(raw);expect(parseFields([f('started_at','Started','datetime-local')],form({started_at:''})).started_at).toBeNull();});
  it('保留 API 支持的所有 Metric / Decision / Risk 枚举',()=>{expect(resourceFields('metrics').find(f=>f.key==='status')?.options?.map(o=>o.value)).toEqual(evidenceStatuses);expect(resourceFields('decisions').find(f=>f.key==='status')?.options?.map(o=>o.value)).toContain('rejected');expect(resourceFields('risks').find(f=>f.key==='severity')?.options?.map(o=>o.value)).toContain('critical');});
});
