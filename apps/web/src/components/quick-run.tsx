'use client';
import {useEffect,useRef,useState} from 'react';
import {useRouter} from 'next/navigation';
import {X} from 'lucide-react';
import {post} from '@/lib/api';
import {useData} from '@/lib/use-data';
import type {ModuleManifest,Project,QueryPage,RecordData} from '../../../../packages/shared/types';

export function QuickRun({project,module,onClose,initialType}:{project:Project;module:ModuleManifest;onClose:()=>void;initialType?:string}) {
 const dialog=useRef<HTMLDialogElement>(null),router=useRouter();
 const [parent,setParent]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const enabled=project.enabled_capabilities as string[]|undefined;
 const types=module.run_types.map(x=>typeof x==='string'?{id:x,name:x,capability:undefined}:x).filter(x=>!x.capability||enabled?.includes(x.capability));
 const parents=useData<QueryPage<RecordData>>(`/projects/${project.id}/runs/query?limit=20&q=${encodeURIComponent(parent)}`);
 useEffect(()=>{dialog.current?.showModal();const node=dialog.current;return()=>node?.close();},[]);
 return <dialog ref={dialog} className="editor quick-run" onCancel={onClose}>
  <div className="editor-heading"><h2>新建研究记录</h2><button type="button" className="icon-button" aria-label="关闭编辑器" onClick={onClose}><X/></button></div>
  <form onSubmit={async e=>{e.preventDefault();setError('');const data=new FormData(e.currentTarget);setSaving(true);try{
   const body={run_type:data.get('run_type'),title:String(data.get('title')).trim(),objective:String(data.get('objective')??'').trim(),parent_run_id:parent.trim()||null};
   if(!body.title)throw new Error('请填写标题');
   const run=await post<RecordData>(`/projects/${project.id}/runs`,body);onClose();router.push(`/runs/${run.id}`);
  }catch(err){setError((err as Error).message);}finally{setSaving(false);}}}>
   <p className="muted">先开始记录，创建后再填写参数、观察和结果。</p>
   {!types.length&&<p role="status">尚未启用可用的研究能力，请先在项目的数据管理中启用。</p>}
   <div className="form-grid">
    <label className="field"><span>研究记录类型 *</span><select name="run_type" required defaultValue={initialType??types[0]?.id}>{types.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
    <label className="field"><span>标题 *</span><input name="title" required maxLength={200} autoFocus/></label>
    <label className="field field-wide"><span>研究目标</span><textarea name="objective" rows={3}/></label>
    <label className="field field-wide"><span>父记录（可选）</span><input name="parent_run_id" value={parent} onChange={e=>setParent(e.target.value)} list="parent-run-options" placeholder="搜索标题后选择；或输入记录 ID"/><datalist id="parent-run-options">{parents.data?.items.map(x=><option key={x.id} value={x.id}>{String(x.title)}</option>)}</datalist><small>关联父记录会自动显示参数差异；需要继承参数时使用父记录的“克隆”。</small></label>
   </div>{error&&<p role="alert" className="error">{error}</p>}
   <div className="editor-actions"><button type="button" onClick={onClose}>取消</button><button className="primary" disabled={saving||!types.length}>{saving?'正在创建…':'创建并继续'}</button></div>
  </form>
 </dialog>;
}
