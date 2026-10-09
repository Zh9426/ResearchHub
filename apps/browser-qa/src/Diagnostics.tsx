import {useEffect,useRef,useState} from 'react';
import type {WorkbenchExtensionContext} from './Workbench';
import {exportRescue,previewRescue,restoreRescue,MAX_RESCUE_BYTES,type RescuePackage} from './local/rescue';
import {inspectStorage,probeDatabaseUpgrade,type StorageStatus} from './local/storage';
import {localCommands} from './local/commands';
import {testOnlyDisconnectedAdapter} from './local/testTransport';

export function Diagnostics({snapshot,draft,dirty,busy,refresh,openRescueDraft}:WorkbenchExtensionContext){
 const [storage,setStorage]=useState<StorageStatus|null>(null),[preview,setPreview]=useState<RescuePackage|null>(null),[error,setError]=useState(''),[status,setStatus]=useState(''),[working,setWorking]=useState(false),[upgrade,setUpgrade]=useState(''),[upgrading,setUpgrading]=useState(false),[transport,setTransport]=useState('');
 const selection=useRef(0);
 useEffect(()=>{void inspectStorage().then(setStorage);},[]);
 async function exportPackage(){setError('');setWorking(true);try{const content=await exportRescue(dirty?draft:null);const url=URL.createObjectURL(new Blob([content],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='researchhub-SYNTHETIC-PLAINTEXT-rescue.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('已生成明文合成救援包；请确认浏览器下载完成。当前未保存输入保持不变。');}catch(e){setError(String(e));}finally{setWorking(false);}}
 async function selectFile(file:File|undefined){const sequence=++selection.current;setPreview(null);setError('');setStatus('');if(!file)return;setWorking(true);try{if(file.size>MAX_RESCUE_BYTES)throw Error('救援文件超过 10 MiB 限制');const validated=await previewRescue(await file.text());if(sequence===selection.current)setPreview(validated);}catch(e){if(sequence===selection.current)setError(String(e));}finally{if(sequence===selection.current)setWorking(false);}}
 async function restore(){if(!preview)return;setError('');setWorking(true);let committed=false;try{const result=await restoreRescue(preview);committed=true;setStatus(result==='restored'?'恢复已提交到本机；原事件来源保留，新工作区身份未授权。未保存草稿可单独打开。':'此救援包已恢复过；未新增记录或审计。');await refresh();}catch(e){setError(`${committed?'恢复已提交，但列表刷新失败；请重试读取。':'恢复未提交。'} ${String(e)}`);}finally{setWorking(false);}}
 async function probeTransport(){try{await testOnlyDisconnectedAdapter.send();}catch(e){setTransport(`${String(e)}。实际 transport 仍为 not_configured；pending 不变，未生成任何 receipt 或科研批准。`);}}
 return <section className="panel"><details className="qa-content"><summary>诊断与合成草稿救援</summary>
 <p>明文 · 仅合成 QA。不是生产备份或加密 Recovery Kit；完整性摘要不证明来源。</p>
 <p className="muted">导出包含冻结项目、Run / Note、星标、未签名 pending 操作、审计和未保存草稿。排除设备密钥、nonce ledger、Cookie、Token、HumanGrant 和设备信任。请勿在文本中输入真实凭据或科研数据。</p>
 <h3>浏览器存储</h3><div data-testid="storage-status">{storage?<><p>{storage.testOnly?'TEST ONLY：模拟结果 · ':''}{storage.persistence}</p><p>{storage.estimate}</p><p>{storage.opfs}</p></>:<p>读取存储能力…</p>}</div>
 <button onClick={()=>void inspectStorage(true).then(setStorage)}>申请持久存储并刷新估计</button><p className="muted">获准或安装 PWA 都不保证永不丢失。清除站点数据后，只能从此前实际导出的材料恢复；不会自动清空数据库修复。</p>
 <h3>导出与恢复</h3><button disabled={!snapshot.identity||busy||working} onClick={()=>void exportPackage()}>导出合成救援包</button>{dirty&&<p>包含当前未保存输入；导出不会把它标记为已保存。</p>}
 <label>选择合成救援包<input type="file" accept="application/json,.json" disabled={working||busy} onChange={e=>void selectFile(e.target.files?.[0])}/></label>
 {preview&&<div data-testid="rescue-preview"><p>预览：{preview.content.projects.length} 个合成项目 · {preview.content.objects.length} 条记录 · {preview.content.operations.length} 条 pending 操作 · {preview.content.audit.length} 条历史 · {preview.content.drafts.length} 条未保存草稿。</p><p>仅向空 QA 工作区恢复，或对同包幂等重试；新工作区使用新的未授权身份。此预览尚未写入。</p></div>}
 <button disabled={!preview||working||busy} onClick={()=>void restore()}>确认恢复到空工作区</button>
 {snapshot.drafts.map(d=><div key={d.id}><p>救援草稿：{d.title||'未命名'}（{d.kind}）</p><button disabled={busy||working} onClick={()=>openRescueDraft(d)}>打开救援草稿为新草稿</button></div>)}
 {status&&<p data-testid="rescue-status" role="status">{status}</p>}{error&&<p data-testid="rescue-error" role="alert" className="error">{error}</p>}
 <details><summary>TEST ONLY 故障探针</summary><p>配额与持久化拒绝为模拟，不是磁盘满验收；升级阻塞由真实 IndexedDB 连接触发。探针不发送网络请求。</p>
 <button disabled={busy} onClick={()=>{localCommands.injectNextQuota();setStatus('TEST ONLY：下一次有效保存将在写请求后模拟 QuotaExceededError 并真实回滚事务。');}}>TEST ONLY：下次保存配额失败</button>
 <button onClick={()=>void inspectStorage(false,'denied').then(setStorage)}>TEST ONLY：模拟持久化拒绝</button><button onClick={()=>void inspectStorage(false,'unsupported').then(setStorage)}>TEST ONLY：模拟 API 不支持</button>
 <button disabled={upgrading||busy} onClick={()=>{setUpgrading(true);setUpgrade('TEST ONLY：请求真实数据库版本升级…');void probeDatabaseUpgrade(setUpgrade).catch(e=>setUpgrade(String(e))).finally(()=>setUpgrading(false));}}>TEST ONLY：请求真实数据库升级</button><p data-testid="upgrade-status" role="status">{upgrade}</p>
 <button onClick={()=>void probeTransport()}>TEST ONLY：模拟连接失败</button><p data-testid="transport-probe" role="status">{transport}</p>
 </details></details></section>;
}
