import {chromium} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
export async function openOwnedKernelBrowser(profile){
 const context=await chromium.launchPersistentContext(profile,{headless:true,channel:'chromium',timeout:30000,args:['--remote-debugging-port=0','--remote-debugging-address=127.0.0.1']});
 try{
  const cdp=await context.browser().newBrowserCDPSession();const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');const pids=processInfo.map(p=>p.id);
  if(!pids.length)throw Error('BROWSER_PID_MISSING');
  const [port,path]=readFileSync(join(profile,'DevToolsActivePort'),'utf8').trim().split(/\r?\n/);
  if(!/^\d{1,5}$/.test(port)||!path.startsWith('/devtools/browser/'))throw Error('OWNED_CDP_ENDPOINT_INVALID');
  return {context,pids,endpoint:`ws://127.0.0.1:${port}${path}`};
 }catch(error){try{await context.close();}catch(cleanup){throw new AggregateError([error,cleanup],'BROWSER_START_AND_CLEANUP_FAILED');}throw error;}
}
export async function closeOwnedKernelBrowser(owned){
 const errors=[];
 try{const cdp=await owned.context.browser().newBrowserCDPSession();const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');owned.pids=[...new Set([...owned.pids,...processInfo.map(p=>p.id)])];}catch(error){errors.push(error);}
 try{await owned.context.close();}catch(error){errors.push(error);}
 if(errors.length)throw new AggregateError(errors,'OWNED_BROWSER_CLEANUP_FAILED');
 const deadline=Date.now()+10000;
 while(true){
  const alive=owned.pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(error){if(error.code==='ESRCH')return false;throw error;}});
  if(!alive.length)return;if(Date.now()>=deadline)throw Error('OWNED_BROWSER_EXIT_DEADLINE');
  await new Promise(done=>setTimeout(done,50));
 }
}
