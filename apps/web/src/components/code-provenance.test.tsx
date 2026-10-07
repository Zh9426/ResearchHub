import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react';
import {afterEach,beforeAll,beforeEach,describe,it,expect,vi} from 'vitest';
import {CodeProvenance,ProjectRepository} from './code-provenance';
const mocks=vi.hoisted(()=>({patch:vi.fn()}));
vi.mock('@/lib/api',()=>({patch:mocks.patch}));
beforeAll(()=>{HTMLDialogElement.prototype.showModal=function(){this.open=true;};HTMLDialogElement.prototype.close=function(){this.open=false;};});
afterEach(cleanup);
beforeEach(()=>{vi.clearAllMocks();mocks.patch.mockResolvedValue({});});
const project={id:'p1',name:'课题',module_id:'generic',description:'',current_stage:null,repository:'https://github.com/Zh9426/ResearchHub'};
describe('代码来源编辑',()=>{
  it('解除仓库关联发送 null，不修改科研目标',async()=>{
    render(<ProjectRepository project={project} onChange={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'关联仓库'}));
    fireEvent.change(screen.getByLabelText(/GitHub 仓库 URL/),{target:{value:''}});
    fireEvent.click(screen.getByRole('button',{name:'保存'}));
    await waitFor(()=>expect(mocks.patch).toHaveBeenCalledWith('/projects/p1',{repository:null}));
  });
  it('来源编辑仅保存代码字段，保留人工结论和旧版本描述',async()=>{
    render(<CodeProvenance project={project} run={{id:'r1',repository:project.repository,branch:'main',human_conclusion:'已复核',code_revision:'旧描述'}} onChange={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'编辑代码来源'}));
    fireEvent.change(screen.getByLabelText(/提交 SHA/),{target:{value:'cb12577fa0b05c08de8f997766e48e4156b93233'}});
    fireEvent.click(screen.getByRole('button',{name:'保存'}));
    await waitFor(()=>expect(mocks.patch).toHaveBeenCalledWith('/runs/r1',{repository:project.repository,branch:'main',commit_sha:'cb12577fa0b05c08de8f997766e48e4156b93233',issue_url:null,pull_request_url:null}));
    expect(screen.getByText('旧描述')).toBeTruthy();
  });
});
