import {useEffect,useState} from 'react';
import {BrowserJoin,parsePublic} from './join';
import {openLocalDatabase} from '../local/db';
const join=new BrowserJoin(()=>openLocalDatabase('researchhub-browser-sync-qa-business-v1'));
export function JoinPanel({refresh}:{refresh:()=>Promise<void>}){
 const [recipient,setRecipient]=useState(''),[challenge,setChallenge]=useState(''),[receipt,setReceipt]=useState(''),[proof,setProof]=useState('');
 const [owner,setOwner]=useState(''),[recovery,setRecovery]=useState(''),[sas,setSas]=useState(''),[checked,setChecked]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState(''),[display,setDisplay]=useState<any>(null);
 useEffect(()=>{void join.state().then(s=>{if(s){setProof(JSON.stringify({session_id:s.start.session_id,proof:s.proof}));setStatus(s.stage==='COMPLETE'?'加入完成 · VERIFIED · Relay hello 已确认':'已保留配对证明；可粘贴同一会话回执继续');}});},[]);
 async function run(work:()=>Promise<void>){setBusy(true);setStatus('');try{await work();}catch(e){setStatus(e instanceof Error?e.message:'JOIN_FAILED');}finally{setBusy(false);}}
 return <section className="qa-content" aria-label="设备安全加入"><h2>加入可信 PC 项目</h2><p>仅支持空工作区加入空的当前 epoch 项目；旧记录需要 BOOTSTRAP_REQUIRED 恢复流程。私钥保留在本浏览器 vault。</p><fieldset disabled={busy}>
 <button onClick={()=>void run(async()=>{setRecipient(JSON.stringify(await join.recipient()));})}>生成本设备加入公钥</button>
 {recipient&&<label>本设备公开身份<textarea readOnly value={recipient}/></label>}
 <label>PC challenge 与 bootstrap<textarea value={challenge} onChange={e=>{setChallenge(e.target.value);setDisplay(null);setChecked(false);}}/></label>
 <button onClick={()=>void run(async()=>{const p=parsePublic(challenge);setDisplay({fingerprint:p.challenge?.recipient?.fingerprint,sas:p.challenge?.sas,owner:p.bootstrap?.owner_root,recovery:p.bootstrap?.recovery_root});})}>查看待核对指纹</button>
 {display&&<div><p>请在可信 PC 屏幕独立核对以下内容；粘贴内容本身不建立信任。</p><p data-testid="join-fingerprint">设备指纹 {display.fingerprint}</p><p>SAS {display.sas}</p><p>Owner root {display.owner}</p><p>Recovery root {display.recovery}</p></div>}
 <label>从可信 PC 独立核对的 Owner root<input value={owner} onChange={e=>setOwner(e.target.value)}/></label>
 <label>从可信 PC 独立核对的 Recovery root<input value={recovery} onChange={e=>setRecovery(e.target.value)}/></label>
 <label>从可信 PC 独立核对的 SAS<input value={sas} onChange={e=>setSas(e.target.value)}/></label>
 <label><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/>我已独立核对 PC 信任根、SAS 与本设备指纹</label>
 <button disabled={!checked||!display} onClick={()=>void run(async()=>{setProof(JSON.stringify(await join.answer(parsePublic(challenge),owner,recovery,sas)));setStatus('配对证明已保存，请交给可信 PC 确认');})}>确认核对并生成配对证明</button>
 {proof&&<label>交给 PC 的配对证明<textarea readOnly value={proof}/></label>}
 <label>PC 完成回执与签名绑定<textarea value={receipt} onChange={e=>setReceipt(e.target.value)}/></label>
 <button onClick={()=>void run(async()=>{await join.complete(parsePublic(receipt));await refresh();setStatus('加入完成 · VERIFIED · Relay hello 已确认');setRecipient('');setChallenge('');setReceipt('');setProof('');setDisplay(null);})}>验证回执并加入</button>
 </fieldset><p role="status" data-testid="join-status">{status}</p></section>;
}
