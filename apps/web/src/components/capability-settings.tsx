'use client';
import {useEffect,useState} from 'react';
import {useData} from '@/lib/use-data';
import {patch} from '@/lib/api';
import type {Capability,Project} from '../../../../packages/shared/types';
import {Panel,Feedback} from './ui';
export function CapabilitySettings({project,onChange}:{project:Project;onChange:()=>void}) {
 const result=useData<Capability[]>('/capabilities'),[selected,setSelected]=useState<string[]>(project.enabled_capabilities as string[]??[]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>setSelected(project.enabled_capabilities as string[]??[]),[project.enabled_capabilities]);
 return <Panel title="工作区能力"><div className="transfer-content"><p>能力决定录入方式，项目模块决定科研字段和证据边界。停用能力会隐藏对应创建入口，已有记录继续保留。</p><Feedback loading={result.loading} error={result.error||error}/><div className="capability-list">{result.data?.map(c=><label key={c.id} className="checkbox-field"><input type="checkbox" checked={selected.includes(c.id)} onChange={e=>setSelected(e.target.checked?[...selected,c.id]:selected.filter(x=>x!==c.id))}/><span><strong>{c.name}</strong><small>{c.description}</small></span></label>)}</div><button className="primary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await patch(`/projects/${project.id}`,{enabled_capabilities:selected});onChange();}catch(err){setError((err as Error).message);}finally{setBusy(false);}}}>{busy?'正在保存…':'保存启用能力'}</button></div></Panel>;
}
