// @vitest-environment jsdom
import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {DataManagement} from './data-management';

const mocks=vi.hoisted(()=>({patch:vi.fn(),post:vi.fn(),api:vi.fn(),refresh:vi.fn(),rows:[] as object[]}));
vi.mock('@/lib/api',()=>({patch:mocks.patch,post:mocks.post,api:mocks.api}));
vi.mock('@/lib/use-data',()=>({useData:()=>({data:mocks.rows,loading:false,error:'',refresh:mocks.refresh})}));
afterEach(cleanup);
beforeEach(()=>{vi.clearAllMocks();mocks.rows=[];mocks.patch.mockResolvedValue({});mocks.post.mockResolvedValue({});});
describe('科研数据管理',()=>{
 it('所有可归档对象都能从数据管理选择并恢复',()=>{
  render(<DataManagement onChange={vi.fn()}/>);
  for(const name of ['参数','指标','主张','来源','决策','假设','研究问题','里程碑','风险','标签','关卡'])expect(screen.getByRole('option',{name})).toBeTruthy();
 });
 it('恢复归档通过生命周期接口，不删除原始记录',async()=>{
  mocks.rows=[{id:'run-1',title:'阴性结果',archived_at:'2026-10-06T00:00:00Z'}];
  const change=vi.fn();render(<DataManagement onChange={change}/>);
  fireEvent.change(screen.getByLabelText('记录类型'),{target:{value:'runs'}});
  fireEvent.click(screen.getByRole('button',{name:'恢复'}));
  await waitFor(()=>expect(mocks.patch).toHaveBeenCalledWith('/lifecycle/runs/run-1',{action:'restore'}));
  expect(change).toHaveBeenCalled();
  expect(mocks.post).not.toHaveBeenCalled();
 });
 it('人工确认升级携带预览摘要，阻止静默升级',async()=>{
  mocks.api.mockResolvedValue({current_version:'0.1.0',target_version:'0.2.0',target_digest:'digest',diff:{run_types:{added:['实验']}}});
  vi.spyOn(window,'confirm').mockReturnValue(true);
  render(<DataManagement project={{id:'project-1',name:'测试项目',description:'',module_id:'hdsp',module_version:'0.1.0',current_stage:null}} onChange={vi.fn()}/>);
  expect(mocks.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'检查模块升级'}));
  fireEvent.click(await screen.findByRole('button',{name:'确认升级模块'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledWith('/projects/project-1/module-upgrade',{
   confirm:true,expected_version:'0.1.0',expected_target_digest:'digest',
  }));
  vi.restoreAllMocks();
 });
});
