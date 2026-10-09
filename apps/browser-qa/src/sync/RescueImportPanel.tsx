import {useEffect,useState} from 'react';
import {previewRescue,type RescuePackage} from '../local/rescue';
import {RescueImporter,previewImport,sourceProjectDescriptor,type ImportPreview} from './rescue-import';
import {openLocalDatabase} from '../local/db';
const importer=new RescueImporter(()=>openLocalDatabase('researchhub-browser-sync-qa-business-v1'));
function download(name:string,raw:string){const url=URL.createObjectURL(new Blob([raw],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function RescueImportPanel({refresh}:{refresh:()=>Promise<void>}){
 const [raw,setRaw]=useState(''),[pack,setPack]=useState<RescuePackage|null>(null),[selected,setSelected]=useState(''),[preview,setPreview]=useState<ImportPreview|null>(null),[status,setStatus]=useState(''),[busy,setBusy]=useState(false),[archives,setArchives]=useState<any[]>([]);
 const reload=async()=>setArchives(await importer.archives());useEffect(()=>{void reload();},[]);
 async function run(work:()=>Promise<void>){setBusy(true);setStatus('');try{await work();}catch(e){setStatus(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 return <section className="qa-content" aria-label="显式导入 3A 救援包"><h2>显式导入 3A 合成记录</h2><p>先选择来源项目并下载描述，用新 PC 节点保留相同项目 UUID 和模块快照。正常配对加入该空项目后，才能预览并确认重放。原 3A 工作区保持独立。</p>
 <fieldset disabled={busy}><label>3A 完整合成救援包<input type="file" accept="application/json,.json" onChange={e=>{const file=e.target.files?.[0];setPreview(null);setPack(null);if(file)void run(async()=>{const text=await file.text(),value=await previewRescue(text);setRaw(text);setPack(value);setSelected(value.content.projects[0].id);});}}/></label>
 {pack&&<><label>选择重放项目<select value={selected} onChange={e=>{setSelected(e.target.value);setPreview(null);}}>{pack.content.projects.map(p=><option key={p.id} value={p.id}>{p.title} · {p.module_id}</option>)}</select></label><p>来源项目 UUID：{selected}</p><p>其他项目与 {pack.content.drafts.length} 份未保存草稿仅归档，不保存为记录，也不发送。</p>
 <button onClick={()=>void run(async()=>download('3a-source-project.json',JSON.stringify(await sourceProjectDescriptor(raw,selected),null,2)))}>下载新 PC 初始化来源描述</button>
 <button onClick={()=>void run(async()=>{setPreview(null);const b=await importer.binding(selected);if(!b)throw Error('请先正常配对加入相同 UUID 的新 PC 空项目');setPreview(await previewImport(raw,selected,b));})}>只读预览导入</button></>}
 {preview&&<div><p>目标同源项目：{preview.selectedProjectId} · {preview.project.module_id} {preview.project.module_version}</p><p>可检查记录 {preview.counts.objects} 条，保存操作 {preview.counts.operations} 步；其他 {preview.counts.archiveProjects} 个项目仅归档。</p><p>来源摘要：{preview.sourceDigest}</p>{preview.blockers.length>0?<ul>{preview.blockers.map((reason,i)=><li key={i}>{reason}</li>)}</ul>:<p>字段验证通过。确认后由当前已授权设备生成新的同步事务；旧设备与旧时间仅保留为来源证据。</p>}
 <button disabled={preview.blockers.length>0} onClick={()=>void run(async()=>{const result=await importer.confirmImport(raw,selected,preview.bindingFingerprint,preview.planDigest);await refresh();await reload();setStatus(`已导入 ${result.operationMap.length} 步；尚未发送至 PC。请使用手动同步。`);})}>确认归档并重放已保存历史</button></div>}
 </fieldset><p role="status" data-testid="import-status">{status}</p>
 {archives.length>0&&<div><h3>只读导入来源</h3><p>下载内容是原始 3A 合成明文来源与转换清单，不是当前已接受状态的可信备份。</p>{archives.map(({journal,archive})=><div key={journal.id}><p>项目 {journal.selectedProjectId} · 原包摘要 {journal.sourceDigest}</p><button onClick={()=>download('3a-original-rescue.json',archive.raw)}>下载原始来源包</button><button onClick={()=>void run(async()=>{const current=(await importer.archives()).find(a=>a.journal.id===journal.id);download('3a-import-mapping.json',JSON.stringify({journal:current?.journal,wireMap:current?.wireMap},null,2));})}>下载旧操作至新操作映射</button></div>)}</div>}
 </section>;
}
