'use client';
import {useState} from 'react';
import {Archive,Tags,Trash2} from 'lucide-react';
import {api,patch} from '@/lib/api';
import {f} from '@/lib/fields';
import type {RecordData} from '../../../../packages/shared/types';
import {Editor} from './ui';
export function ArtifactControls({artifact,tags,onChange}:{artifact:RecordData;tags:RecordData[];onChange:()=>void}) {
 const [editing,setEditing]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const act=async(action:string)=>{setBusy(true);setError('');try{if(action==='trash')await api(`/artifacts/${artifact.id}`,{method:'DELETE'});else await patch(`/lifecycle/artifacts/${artifact.id}`,{action});onChange();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <><div className="row-actions"><button className="icon-button" disabled={busy} aria-label={`归档 ${artifact.filename}`} onClick={()=>void act('archive')}><Archive size={16}/></button><button className="icon-button" aria-label={`标签 ${artifact.filename}`} onClick={()=>setEditing(true)}><Tags size={16}/></button><button className="icon-button danger" disabled={busy} aria-label={`移入回收站 ${artifact.filename}`} onClick={()=>{if(confirm('将文件移入回收站？字节和关联暂保留，可从数据管理恢复。'))void act('trash');}}><Trash2 size={16}/></button></div>{error&&<p role="alert" className="error">{error}</p>}{editing&&<Editor title="编辑文件标签" fields={[f('tag_ids','标签','multi',{options:tags.map(x=>({value:x.id,label:String(x.name)}))})]} item={artifact} onClose={()=>setEditing(false)} onSave={async body=>{await patch(`/artifacts/${artifact.id}`,body);onChange();}}/>}</>;
}
