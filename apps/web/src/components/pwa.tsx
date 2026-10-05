'use client';
import {useEffect,useState} from 'react';
type InstallEvent=Event&{prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>};
export function PwaControls(){
 const [prompt,setPrompt]=useState<InstallEvent|null>(null),[secure,setSecure]=useState(true),[message,setMessage]=useState(''),[offlineStatus,setOfflineStatus]=useState('正在准备离线提示…');
 useEffect(()=>{let active=true;setSecure(window.isSecureContext);const listener=(event:Event)=>{event.preventDefault();setPrompt(event as InstallEvent);};window.addEventListener('beforeinstallprompt',listener);if('serviceWorker'in navigator&&window.isSecureContext){navigator.serviceWorker.register('/sw.js').then(()=>navigator.serviceWorker.ready).then(()=>{if(active)setOfflineStatus('离线说明页已就绪；科研记录仍需连接服务。');}).catch(()=>{if(active)setOfflineStatus('离线说明页未就绪，请重新连接后重试。');});}else setOfflineStatus('当前浏览器或连接不支持离线说明页。');return()=>{active=false;window.removeEventListener('beforeinstallprompt',listener);};},[]);
 return <div className="pwa-controls"><p>{secure?'当前为安全上下文；支持的浏览器可安装 PWA。':'当前 HTTP 地址不是安全上下文。手机安装需要 HTTPS 或 localhost。'}</p><p role="status" className="muted">{offlineStatus}</p><button disabled={!secure} onClick={async()=>{if(prompt){await prompt.prompt();const choice=await prompt.userChoice;setMessage(choice.outcome==='accepted'?'已接受安装请求。':'安装已取消。');setPrompt(null);}else setMessage('请使用浏览器菜单中的「安装应用」或「添加到主屏幕」。浏览器是否提供安装取决于平台与当前安装状态。');}}>安装Research Hub</button>{message&&<p role="status" className="muted">{message}</p>}<small>仅静态离线页缓存；科研数据与会话页面需要联网。</small></div>;
}
