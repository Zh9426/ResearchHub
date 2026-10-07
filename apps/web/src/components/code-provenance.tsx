'use client';
import {useState} from 'react';
import {patch} from '@/lib/api';
import {f} from '@/lib/fields';
import {codeLinks,githubRepository} from '@/lib/code-provenance';
import type {RecordData,Project} from '../../../../packages/shared/types';
import {Editor,Panel,date} from './ui';

export function ProjectRepository({project,onChange}:{project:Project;onChange:()=>void}){
  const [editing,setEditing]=useState(false),repository=githubRepository(project.repository);
  return <Panel title="GitHub 代码来源" action={<button onClick={()=>setEditing(true)}>关联仓库</button>}>
    <p className="section-copy">保存课题的代码仓库。科研记录、证据与判断保存在 Research Hub。</p>
    {repository?<a href={repository} target="_blank" rel="noopener noreferrer">{repository}</a>:<p>尚未关联仓库。</p>}
    {editing&&<Editor title="关联代码仓库" fields={[f('repository','GitHub 仓库 URL','text',{hint:'例如 https://github.com/Zh9426/ResearchHub。留空解除关联。'})]} item={project} onClose={()=>setEditing(false)} onSave={async body=>{await patch(`/projects/${project.id}`,{repository:body.repository||null});onChange();}}/>}
  </Panel>;
}

export function CodeProvenance({run,project,onChange}:{run:RecordData;project:Project;onChange:()=>void}){
  const [editing,setEditing]=useState(false),links=codeLinks(run,project.repository);
  const fields=[f('repository','GitHub 仓库 URL','text',{hint:'留空时显示项目仓库；需要可复现来源时保存记录自己的仓库。'}),f('branch','分支'),f('commit_sha','提交 SHA','text',{hint:'完整的 40 位十六进制提交 SHA。'}),f('issue_url','Issue URL','text'),f('pull_request_url','Pull Request URL','text')];
  return <Panel title="代码来源与运行环境" action={<button onClick={()=>setEditing(true)}>编辑代码来源</button>}>
    <p className="section-copy">链接打开 GitHub；这里只展示已保存的来源，未自动验证提交存在或读取仓库内容。</p>
    <div className="capture-home-links">{links.map(link=><a className="button" href={link.url} target="_blank" rel="noopener noreferrer" key={link.label}>{link.label} ↗</a>)}</div>
    <dl className="record-dl"><dt>仓库</dt><dd>{String(run.repository??project.repository??'未知')}{!run.repository&&project.repository?'（项目默认）':''}</dd><dt>分支</dt><dd><code>{String(run.branch??'未知')}</code></dd><dt>提交 SHA</dt><dd><code>{String(run.commit_sha??'未知')}</code></dd><dt>历史代码版本</dt><dd>{String(run.code_revision||'未知')}</dd><dt>运行环境</dt><dd>{String(run.environment||'未知')}</dd><dt>软件版本</dt><dd>{String(run.software_version||'未知')}</dd><dt>开始 / 完成</dt><dd>{date(run.started_at)} / {date(run.completed_at)}</dd></dl>
    {editing&&<Editor title="编辑代码来源" fields={fields} item={run} onClose={()=>setEditing(false)} onSave={async body=>{await patch(`/runs/${run.id}`,Object.fromEntries(fields.map(field=>[field.key,body[field.key]||null])));onChange();}}/>}
  </Panel>;
}
