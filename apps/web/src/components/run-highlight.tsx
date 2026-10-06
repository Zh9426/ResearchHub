'use client';
import {useState} from 'react';
import {Star} from 'lucide-react';
import {patch} from '@/lib/api';
import type {RecordData} from '../../../../packages/shared/types';
import {Editor} from './ui';
import {f} from '@/lib/fields';

export function RunHighlight({run,onChange,compact=false}:{run:RecordData;onChange:()=>void;compact?:boolean}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[editing,setEditing]=useState(false);const marked=Boolean(run.is_highlighted);
 return <span className="highlight-control"><button className={compact?'icon-button':'button'} aria-label={`${marked?'取消星标':'星标'} ${run.title}`} aria-pressed={marked} disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await patch(`/runs/${run.id}/highlight`,{is_highlighted:!marked});onChange();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
  <Star size={17} fill={marked?'currentColor':'none'} aria-hidden/>{!compact&&(marked?'已星标':'星标')}
 </button>{marked&&!compact&&<button onClick={()=>setEditing(true)}>星标说明</button>}{error&&<span className="error" role="alert">{error}</span>}{editing&&<Editor title="星标说明" item={{id:run.id,type:run.highlight_type,note:run.highlight_note}} fields={[f('type','星标类型','text',{hint:'可选，例如关键基线、负结果或待复查。'}),f('note','星标原因','textarea')]} onClose={()=>setEditing(false)} onSave={async body=>{await patch(`/runs/${run.id}/highlight`,{is_highlighted:true,...body});onChange();}}/>}</span>;
}
