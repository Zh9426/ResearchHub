import {useEffect,useState} from 'react';
import {previewBinding,type BindingPreview} from './binding';
import type {BindingRecord} from './wire';
import {openLocalDatabase} from '../local/db';
export function BindingPanel({refreshToken}:{refreshToken?:unknown}={}){
 const [text,setText]=useState(''),[preview,setPreview]=useState<BindingPreview|null>(null),[status,setStatus]=useState<'READING'|'VERIFIED'|'UNVERIFIED'|'ERROR'>('READING');
 useEffect(()=>{
  let active=true;
  void (async()=>{const db=await openLocalDatabase('researchhub-browser-sync-qa-business-v1');try{
   const rows=await new Promise<BindingRecord[]>((resolve,reject)=>{const tx=db.transaction('meta','readonly'),request=tx.objectStore('meta').getAll();tx.oncomplete=()=>resolve(request.result);tx.onabort=()=>reject(tx.error);});
   if(active)setStatus(rows.some(r=>r.state==='VERIFIED'&&r.id===`binding:${r.binding?.semantic_project_id}`)?'VERIFIED':'UNVERIFIED');
  }finally{db.close();}})().catch(()=>{if(active)setStatus('ERROR');});
  return()=>{active=false;};
 },[refreshToken]);
 return <section className="qa-content"><h2>项目加入</h2><p>{status==='VERIFIED'?'已存在 VERIFIED 项目绑定；下方独立预览不会更改已有授权。':status==='UNVERIFIED'?'尚未加入受信项目。尚未验证项目所有者和设备授权，暂不能转换或发送。':status==='ERROR'?'持久绑定状态读取失败；请重新加载。':'正在读取持久绑定状态…'}</p><label>公共项目绑定（待验证预览）<textarea value={text} onChange={e=>setText(e.target.value)}/></label><button onClick={async()=>{try{setPreview(await previewBinding(JSON.parse(text)));}catch{setPreview({state:'BLOCKED',reasons:['JSON: invalid input']});}}}>预览公共绑定</button>{preview&&<div role="status"><p>{preview.state==='UNVERIFIED'?'内容校验通过；此预览未验证信任，也不建立或改变项目授权。':'绑定预览受阻'}</p>{preview.binding&&<p>项目 UUID：{preview.binding.semantic_project_id} · 模块 {preview.binding.module_snapshot.id}</p>}<ul>{preview.reasons.map((r,i)=><li key={i}>{r}</li>)}</ul></div>}<details><summary>诊断</summary><p>{status==='VERIFIED'?'项目授权：VERIFIED；记录应用状态请查看“当前记录同步状态”。':'项目授权尚未验证，不能转换或发送。'}</p><p>3A 救援导入：NOT IMPLEMENTED。不会克隆设备身份或 nonce。</p></details></section>;
}
