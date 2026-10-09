import {chromium,expect,type BrowserContext} from '@playwright/test';
import {spawn,type ChildProcess} from 'node:child_process';
import {once} from 'node:events';
import {resolve} from 'node:path';
export const runtime=resolve('../../storage/runtime/browser-local-qa');
export const origin='http://127.0.0.1:3313';
process.env.PLAYWRIGHT_BROWSERS_PATH=resolve(runtime,'browsers');
export async function startServer(){const server=spawn(process.execPath,['scripts/server.mjs'],{stdio:['ignore','pipe','pipe']});await new Promise<void>((ok,no)=>{const t=setTimeout(()=>no(Error('QA startup timeout')),5000);server.stdout!.on('data',d=>{if(String(d).includes('QA_READY')){clearTimeout(t);ok();}});server.once('error',no);server.once('exit',c=>{clearTimeout(t);no(Error(`QA server exited ${c}`));});});return server;}
export async function stopServer(server:ChildProcess){if(server.exitCode===null&&server.signalCode===null){const exited=once(server,'exit');server.kill();await exited;}}
export const launch=(profile:string)=>chromium.launchPersistentContext(profile,{headless:true,channel:'chromium'});
export async function closeBrowser(context:BrowserContext){const browser=context.browser()!;const cdp=await browser.newBrowserCDPSession();const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');const pids=processInfo.map(p=>p.id);expect(pids.length).toBeGreaterThan(0);await context.close();expect(browser.isConnected()).toBe(false);await expect.poll(()=>pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(e){if((e as NodeJS.ErrnoException).code==='ESRCH')return false;throw e;}})).toEqual([]);console.log(JSON.stringify({closedBrowserPids:pids,remainingBrowserProcesses:[]}));}
