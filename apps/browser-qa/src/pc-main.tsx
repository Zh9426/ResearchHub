import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {QaShell} from './QaShell';
import {Workbench} from './Workbench';
import {Panel} from '../../web/src/components/presentational';
import {pcAdapter,request,snapshot,type PcSnapshot} from './pc/adapter';
import {previewBinding,type PublicProjectBinding} from './sync/binding';
function PcStatus(){
 const [state,setState]=useState<PcSnapshot|null>(null),[binding,setBinding]=useState<unknown>(null),[error,setError]=useState(''),[preview,setPreview]=useState('');
 async function refresh(){try{setState(await snapshot());const value=await request<{binding:PublicProjectBinding}>('/api/binding');setBinding(value);const checked=await previewBinding(value.binding);setPreview(checked.state==='UNVERIFIED'?'结构校验通过，仍须独立信任确认':checked.reasons.join('；'));}catch(e){setError(String(e));}}
 useEffect(()=>{void refresh();},[]);
 return <Panel title="PC 可信读取与公共绑定"><div className="qa-content"><p>PC 合成节点 · 受控实验。设备文件为 UNPROTECTED QA ONLY，项目密钥仅在 PC 内存中解封。</p><p>配对与网络尚未接入，G4 未完成；保存不表示对端已收到或科研批准。</p><button onClick={()=>void refresh()}>刷新可信状态</button>{error&&<p role="alert">{error}</p>}{state&&<><p>PC 待处理事务 {state.outbox_count} 条</p>{state.records.map(r=><div key={r.object_id}><strong>{r.work?.document.title as string||r.object_id}</strong><p>{r.trusted.status==='conflicted'?'存在冲突，保留双方候选':r.trusted.status==='accepted'?'内核普通记录已接纳；未请求科研批准':'候选记录，尚未接纳'} · {r.work?.pending?'本地修改待发送':'无本地待发送修改'}</p><details><summary>工作副本、可信基线、候选与历史</summary><pre>{JSON.stringify(r,null,2)}</pre></details></div>)}</>}
 <p data-testid="binding-preview">{preview}</p><details><summary>公共绑定（仅公开身份；浏览器仍需独立确认信任根）</summary><textarea aria-label="公共绑定 payload" readOnly rows={12} value={binding?JSON.stringify(binding,null,2):''}/><p>签名包装 domain：ResearchHub/PcProjectBinding/v1。复制该公开内容不等于完成配对。</p></details></div></Panel>;
}
if(location.origin!=='http://127.0.0.1:3315')document.body.textContent='拒绝启动：固定 PC QA 地址 http://127.0.0.1:3315';
else createRoot(document.getElementById('root')!).render(<QaShell sync pc><Workbench adapter={pcAdapter} extension={()=><PcStatus/>}/></QaShell>);
