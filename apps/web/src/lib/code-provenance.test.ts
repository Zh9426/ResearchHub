import {describe,it,expect} from 'vitest';
import {codeLinks,githubRepository} from './code-provenance';

describe('代码来源链接',()=>{
  it('拒绝外部主机与凭据，保留合法 GitHub 仓库',()=>{
    expect(githubRepository('https://github.com/Zh9426/ResearchHub.git')).toBe('https://github.com/Zh9426/ResearchHub');
    for(const value of ['javascript:alert(1)','https://github.com.evil.invalid/a/b','https://token@github.com/a/b','https://github.com/a/b?secret=x'])expect(githubRepository(value)).toBeNull();
  });
  it('仅链接所属仓库的 Issue/PR，分支按路径编码',()=>{
    const links=codeLinks({id:'run',branch:'codex/v02',commit_sha:'cb12577',issue_url:'https://github.com/other/repo/issues/1',pull_request_url:'https://github.com/Zh9426/ResearchHub/pull/2'},'https://github.com/Zh9426/ResearchHub');
    expect(links.map(x=>x.label)).toEqual(['代码仓库','分支','关联提交','关联 Pull Request']);
    expect(links[1].url).toContain('codex%2Fv02');
    expect(codeLinks({id:'run',repository:'https://evil.invalid/a/b'},'https://github.com/Zh9426/ResearchHub')).toEqual([]);
  });
  it('同仓库大小写差异不会隐藏合法 Issue',()=>{
    const issue='https://github.com/zh9426/researchhub/issues/1';
    expect(codeLinks({id:'run',issue_url:issue},'https://github.com/Zh9426/ResearchHub')).toContainEqual({label:'关联 Issue',url:issue});
  });
});
