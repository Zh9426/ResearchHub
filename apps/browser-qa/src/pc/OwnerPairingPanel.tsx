import {useEffect,useState} from 'react';
import {request} from './adapter';
import {parsePublic} from '../sync/join';
export function OwnerPairingPanel(){
 const [recipient,setRecipient]=useState(''),[proof,setProof]=useState(''),[session,setSession]=useState(''),[output,setOutput]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function call(path:string,body?:unknown){setBusy(true);setError('');try{const v=await request<any>(path,body);setOutput(v);if(v.session_id)setSession(v.session_id);}catch(e){setError(e instanceof Error?e.message:'PAIRING_FAILED');}finally{setBusy(false);}}
 useEffect(()=>{void call('/api/pairing/status');},[]);
 return <section className="qa-content" aria-label="PC 所有者配对"><h2>授权新浏览器设备</h2><p>将新浏览器公开身份粘贴在这里，独立核对设备指纹和 SAS 后确认。仅支持空项目，明确操作才向 Relay 发起配对。PC 显示 COMPLETE 后仍须等待 B 显示加入完成，再创建业务记录。</p><fieldset disabled={busy}>
 <label>B 设备公开身份<textarea value={recipient} onChange={e=>setRecipient(e.target.value)}/></label><button onClick={()=>{try{void call('/api/pairing/start',{recipient:parsePublic(recipient)});}catch{setError('INVALID_INPUT');}}}>开始设备配对</button>
 {output?.challenge&&<div><p data-testid="pc-owner-root">Owner root {output.bootstrap.owner_root}</p><p data-testid="pc-recovery-root">Recovery root {output.bootstrap.recovery_root}</p><p data-testid="pc-sas">SAS {output.challenge.sas}</p><p data-testid="pc-fingerprint">设备指纹 {output.challenge.recipient.fingerprint}</p></div>}
 <label>PC 配对公开输出<textarea readOnly value={output?JSON.stringify(output):''}/></label>
 <label>B 配对证明<textarea value={proof} onChange={e=>setProof(e.target.value)}/></label><button onClick={()=>{try{void call('/api/pairing/confirm',parsePublic(proof));}catch{setError('INVALID_INPUT');}}}>确认 B 配对证明</button>
 <label>配对会话 ID<input value={session} onChange={e=>setSession(e.target.value)}/></label><button onClick={()=>void call('/api/pairing/resume',{session_id:session})}>恢复当前配对</button></fieldset><p role="status">{output?.stage}</p>{error&&<p role="alert">{error}</p>}</section>;
}
