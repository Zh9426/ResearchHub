import React from 'react';
import {describe,it,expect,vi,beforeAll} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {Editor,Status} from './ui';
import {resourceFields} from '@/lib/fields';
import {CriteriaEditor} from './criteria-editor';
beforeAll(()=>{HTMLDialogElement.prototype.showModal=function(){this.open=true;};HTMLDialogElement.prototype.close=function(){this.open=false;};});
describe('科研编辑器',()=>{
 it('新增参数真实提交 unknown/null，保持人工确认关闭',async()=>{const save=vi.fn().mockResolvedValue(undefined),close=vi.fn();render(<Editor title="Parameters" fields={resourceFields('parameters')} onSave={save} onClose={close}/>);fireEvent.change(screen.getByLabelText('参数名称 *'),{target:{value:'material_threshold'}});fireEvent.click(screen.getByText('保存'));await waitFor(()=>expect(save).toHaveBeenCalled());expect(save.mock.calls[0][0]).toMatchObject({name:'material_threshold',value:null,source_kind:'unknown',is_confirmed:false});expect(close).toHaveBeenCalled();cleanup();});
 it('保存失败保留输入并展示服务端错误',async()=>{render(<Editor title="Note" fields={resourceFields('notes')} onSave={async()=>{throw new Error('API 不可用');}} onClose={()=>{}}/>);fireEvent.change(screen.getByLabelText('标题 *'),{target:{value:'负结果记录'}});fireEvent.change(screen.getByLabelText('记录内容 *'),{target:{value:'未检出差异'}});fireEvent.click(screen.getByText('保存'));await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('API 不可用'));expect((screen.getByLabelText('标题 *') as HTMLInputElement).value).toBe('负结果记录');cleanup();});
 it('负科研结果与软件失败显示不同状态文本',()=>{render(<><Status value="negative_result"/><Status value="failed"/></>);expect(screen.getByText('negative result')).toBeDefined();expect(screen.getByText('failed')).toBeDefined();cleanup();});
 it('更新 Gate Criterion 状态保留定义与 provenance',()=>{const {container}=render(<CriteriaEditor name="criteria" value={[{id:'G1-1',description:'数值细化',provenance:'proposed roadmap',status:'not_started',evidence_ids:[]}]}/>);fireEvent.change(screen.getByLabelText('Criterion Status'),{target:{value:'blocked'}});const input=container.querySelector('input[name="criteria"]') as HTMLInputElement;expect(JSON.parse(input.value)[0]).toMatchObject({id:'G1-1',description:'数值细化',provenance:'proposed roadmap',status:'blocked',evidence_ids:[]});cleanup();});
});
