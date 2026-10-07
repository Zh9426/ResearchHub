import type {RecordData} from '../../../../packages/shared/types';

export function githubRepository(value:unknown):string|null {
  if(typeof value!=='string')return null;
  const match=/^https:\/\/github\.com\/([A-Za-z0-9_-]+)\/([A-Za-z0-9_.-]+)\/?$/.exec(value);
  if(!match||['.','..'].includes(match[2]))return null;
  return `https://github.com/${match[1]}/${match[2].replace(/\.git$/,'')}`;
}

export function codeLinks(run:RecordData,fallback?:unknown):{label:string;url:string}[] {
  const repository=githubRepository(run.repository??fallback);
  if(!repository)return [];
  const links=[{label:'代码仓库',url:repository}];
  if(typeof run.branch==='string'&&run.branch.trim())links.push({label:'分支',url:`${repository}/tree/${encodeURIComponent(run.branch)}`});
  if(typeof run.commit_sha==='string'&&/^[a-f0-9]{7,40}$/i.test(run.commit_sha))links.push({label:'关联提交',url:`${repository}/commit/${run.commit_sha}`});
  for(const [key,label,path] of [['issue_url','关联 Issue','issues'],['pull_request_url','关联 Pull Request','pull']] as const){
    const value=run[key];
    if(typeof value==='string'&&value.toLowerCase().startsWith(`${repository}/${path}/`.toLowerCase())&&/^[1-9]\d*$/.test(value.slice(`${repository}/${path}/`.length)))links.push({label,url:value});
  }
  return links;
}
