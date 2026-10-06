'use client';
import {useState} from 'react';
import {post} from '@/lib/api';
import {useData} from '@/lib/use-data';
import type {RecordData} from '../../../../packages/shared/types';
import {Empty,Feedback,Panel} from './ui';
export function StorageCleanup(){
 const result=useData<{items:(RecordData&{object_key:string;has_live_reference:boolean})[]}>('/storage/gc-preview'),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 return <Panel title="待清理的文件字节"><div className="transfer-content"><p>仅清理永久删除或失败上传登记的孤立文件。仍有科研记录引用的字节会保留；不会扫描或清空整个存储桶。</p><Feedback loading={result.loading} error={result.error||error}/>{result.data?.items.length?<><ul>{result.data.items.map(x=><li key={x.id}><code>{x.object_key.split('/').at(-1)}</code> · {x.has_live_reference?'仍有引用，保留':x.status==='failed'?'上次失败，可重试':'等待清理'}</li>)}</ul><button disabled={busy||!result.data.items.some(x=>!x.has_live_reference)} className="danger" onClick={async()=>{if(!confirm('永久清理以上没有活动引用的文件字节？已永久删除的内容无法恢复。'))return;setBusy(true);setError('');try{const cleared=await post<{deleted:number;failed:number;skipped_live:number}>('/storage/gc',{confirm:true,object_keys:result.data!.items.filter(x=>!x.has_live_reference).map(x=>x.object_key)});setMessage(`已清理 ${cleared.deleted} 个；失败 ${cleared.failed} 个；保留引用 ${cleared.skipped_live} 个`);result.refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>确认清理孤立字节</button></>:!result.loading&&<Empty>没有待清理的文件。</Empty>}{message&&<p role="status">{message}</p>}</div></Panel>;
}
