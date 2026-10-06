import {afterEach,beforeAll,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import type {ModuleManifest,Project,RunContext} from '../../../../packages/shared/types';
import {QuickRun} from './quick-run';
import {RunHighlight} from './run-highlight';
import {CloneRun} from './clone-run';
import {RunWorksheet,parseScientificValue} from './run-worksheet';

const mocks=vi.hoisted(()=>({post:vi.fn(),patch:vi.fn(),push:vi.fn(),refresh:vi.fn()}));
vi.mock('@/lib/api',()=>({post:mocks.post,patch:mocks.patch}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:mocks.push})}));
vi.mock('@/lib/use-data',()=>({useData:()=>({data:{items:[],total:0,limit:20,offset:0},loading:false,error:'',refresh:mocks.refresh})}));
const module={id:'generic',name:'通用科研',version:'0.2.0',description:'',run_types:[{id:'simulation',name:'仿真',capability:'code_simulation'},{id:'measurement',name:'测量',capability:'measurement_imaging'}],parameter_schemas:[{id:'pressure',name:'压力',value_type:'number',unit:'Pa',default:null},{id:'threshold',name:'阈值',value_type:'number',unit:'',default:null}],metric_schemas:[{id:'error',name:'误差',value_type:'number',unit:'Pa',default:null}],context_fields:[],research_stages:[],stage_gates:[],artifact_categories:['data'],navigation:[],custom_views:[],dashboard_widgets:[]} as ModuleManifest;
const project={id:'project-1',name:'测试',description:'',module_id:'generic',current_stage:null,enabled_capabilities:['code_simulation']} as Project;
const context={run:{id:'run-1',title:'负结果',status:'completed',scientific_outcome:'negative_result',run_type:'simulation'},parameters:[{id:'p1',name:'pressure',value:0,unit:'MPa',source_kind:'literature',source_id:'source-1',source_location:'表2',is_confirmed:true}],metrics:[{id:'m1',name:'error',value:1,unit:'Pa',status:'validated'}],artifacts:[],evidence:[],parent:null,children:[],changes_from_parent:{}} as RunContext;
beforeAll(()=>{HTMLDialogElement.prototype.showModal=function(){this.open=true;};HTMLDialogElement.prototype.close=function(){this.open=false;};});
beforeEach(()=>{vi.clearAllMocks();mocks.post.mockResolvedValue({id:'new-run'});mocks.patch.mockResolvedValue({});});
afterEach(cleanup);
describe('人优先研究工作流',()=>{
 it('快捷创建只显示四个首层字段，提交精简数据并跳转',async()=>{
  const close=vi.fn();const {container}=render(<QuickRun project={project} module={module} onClose={close}/>);
  expect(container.querySelectorAll('input[name],select[name],textarea[name]')).toHaveLength(4);
  expect(screen.queryByRole('option',{name:'测量'})).toBeNull();
  fireEvent.change(screen.getByLabelText('标题 *'),{target:{value:'  阈值未知的仿真  '}});
  fireEvent.change(screen.getByLabelText('研究目标'),{target:{value:'  检查负结果  '}});
  fireEvent.click(screen.getByRole('button',{name:'创建并继续'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledWith('/projects/project-1/runs',{run_type:'simulation',title:'阈值未知的仿真',objective:'检查负结果',parent_run_id:null}));
  expect(mocks.push).toHaveBeenCalledWith('/runs/new-run');expect(close).toHaveBeenCalled();
 });
 it('未启用任何能力时禁止创建并给出操作说明',()=>{
  render(<QuickRun project={{...project,enabled_capabilities:[]}} module={module} onClose={vi.fn()}/>);
  expect((screen.getByRole('button',{name:'创建并继续'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('status').textContent).toContain('启用');
 });
 it('星标负结果不会改运行状态、科研结果或结论',async()=>{
  render(<RunHighlight run={context.run} onChange={mocks.refresh}/>);
  fireEvent.click(screen.getByRole('button',{name:'星标 负结果'}));
  await waitFor(()=>expect(mocks.patch).toHaveBeenCalledWith('/runs/run-1/highlight',{is_highlighted:true}));
  expect(context.run.status).toBe('completed');expect(context.run.scientific_outcome).toBe('negative_result');
 });
 it('克隆只提交选择的继承选项及文件引用',async()=>{
  render(<CloneRun run={context.run} artifacts={[{id:'a1',filename:'原始.csv'}]}/>);
  fireEvent.click(screen.getByRole('button',{name:'克隆'}));
  fireEvent.click(screen.getByLabelText('继承代码版本'));
  fireEvent.change(screen.getByRole('listbox'),{target:{value:'a1'}});
  fireEvent.click(screen.getByRole('button',{name:'保存'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalled());
  const body=mocks.post.mock.calls[0][1];expect(body).toMatchObject({inherit_parameters:true,inherit_code:false,artifact_ids:['a1']});
  expect(body).not.toHaveProperty('human_conclusion');expect(body).not.toHaveProperty('scientific_outcome');expect(body).not.toHaveProperty('status');
 });
 it('分组保存保留零、实际单位和来源，未知值为 null，取消自动确认',async()=>{
  render(<RunWorksheet context={context} module={module} onChange={mocks.refresh}/>);
  expect((screen.getByRole('spinbutton',{name:'压力 (MPa)'}) as HTMLInputElement).value).toBe('0');
  fireEvent.click(screen.getAllByRole('button',{name:'保存此组'})[0]);
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledWith('/runs/run-1/parameters/batch',{parameters:[expect.objectContaining({name:'pressure',value:0,unit:'MPa',source_kind:'literature',source_id:'source-1',source_location:'表2',is_confirmed:false}),expect.objectContaining({name:'threshold',value:null})]}));
 });
 it('改过的指标数值不会继承 validated',async()=>{
  render(<RunWorksheet context={context} module={module} onChange={mocks.refresh}/>);
  fireEvent.change(screen.getByRole('spinbutton',{name:'误差 (Pa)'}),{target:{value:'2'}});
  fireEvent.click(screen.getAllByRole('button',{name:'保存此组'})[1]);
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledWith('/runs/run-1/metrics/batch',{metrics:[expect.objectContaining({name:'error',value:2,status:'unknown'})]}));
 });
 it('按模块字段独立读取已有参数，保留未知单位，不用缺页替换已有值',async()=>{
  render(<RunWorksheet context={{...context,parameters:[],worksheet_parameters:[{id:'late',name:'pressure',value:1.4,unit:null,source_kind:'literature',source_location:'Table2'}]}} module={module} onChange={mocks.refresh}/>);
  fireEvent.click(screen.getAllByRole('button',{name:'保存此组'})[0]);
  await waitFor(()=>expect(mocks.post.mock.calls[0][1].parameters[0]).toMatchObject({name:'pressure',value:1.4,unit:null,source_kind:'literature',source_location:'Table2'}));
 });
 it('模块表单尚未完整加载时阻止整组保存',()=>{
  render(<RunWorksheet context={{...context,worksheet_parameters_incomplete:true}} module={module} onChange={mocks.refresh}/>);
  expect((screen.getAllByRole('button',{name:'保存此组'})[0] as HTMLButtonElement).disabled).toBe(true);
 });
 it('结构值检查类型，空白与零不会混淆',()=>{
  expect(parseScientificValue('','number')).toBeNull();expect(parseScientificValue('0','number')).toBe(0);
  expect(()=>parseScientificValue('{}','array')).toThrow();expect(()=>parseScientificValue('1.2','integer')).toThrow();
 });
});
