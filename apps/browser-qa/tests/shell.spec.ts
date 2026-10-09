import {test,expect,chromium,type BrowserContext} from '@playwright/test';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {existsSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import os from 'node:os';
const running=(pid:number)=>{try{process.kill(pid,0);return true;}catch(error){if((error as NodeJS.ErrnoException).code==='ESRCH')return false;throw error;}};
const runtime=resolve('../../storage/runtime/browser-local-qa');
process.env.PLAYWRIGHT_BROWSERS_PATH=resolve(runtime,'browsers');
const origin='http://127.0.0.1:3313';
test('壳初始化后停止服务器、关闭浏览器进程、同profile离线直访详情',async()=>{
 mkdirSync(runtime,{recursive:true});
 // Before implementation, a deliberately empty static fixture lets Chromium prove the missing UI.
 let fixture:ReturnType<typeof createServer>|undefined;
 let server:ReturnType<typeof spawn>|undefined;
 let context:BrowserContext|undefined;
 try {
 if(!existsSync('scripts/server.mjs')){fixture=createServer((_q,r)=>r.end('<!doctype html><title>RED empty shell</title>'));fixture.listen(3313,'127.0.0.1');await once(fixture,'listening');}
 else {server=spawn(process.execPath,['scripts/server.mjs'],{stdio:['ignore','pipe','pipe']});await new Promise<void>((ok,no)=>{const timer=setTimeout(()=>no(new Error('QA server startup timeout')),5000);server!.stdout!.on('data',d=>{if(String(d).includes('QA_READY')){clearTimeout(timer);ok();}});server!.once('error',error=>{clearTimeout(timer);no(error);});server!.once('exit',c=>{clearTimeout(timer);no(new Error(`server exit ${c}`));});});}
 const profile=resolve(runtime,'profiles',`shell-${Date.now()}`);
 context=await chromium.launchPersistentContext(profile,{headless:true,channel:'chromium'});
 console.log(JSON.stringify({browser:context.browser()?.version(),os:`${os.platform()} ${os.release()} ${os.arch()}`,origin,profile}));
 const page=await context.newPage();await page.goto(origin);
 await expect(page.getByText('浏览器离线实验版 · 仅合成数据 · 未接入跨端同步')).toBeVisible();
 await page.getByRole('button',{name:'初始化离线资源'}).click();
 await expect(page.getByTestId('offline-status')).toHaveText('离线资源已就绪');
 const shellKeys=await page.evaluate(async()=>{const names=await caches.keys();const cache=await caches.open(names.find(n=>n.startsWith('researchhub-browser-qa-shell-'))!);return (await cache.keys()).map(r=>new URL(r.url).pathname).sort();});
 expect(shellKeys).toEqual(['/app.css','/app.js','/icon.svg','/index.html']);
 const collision=spawn(process.execPath,['scripts/server.mjs'],{stdio:'pipe'});expect((await once(collision,'exit'))[0]).toBe(1);expect((await fetch(origin)).ok).toBe(true);
 expect((await fetch(origin+'/api/projects')).status).toBe(404);
 await page.evaluate(()=>caches.open('unknown-cache').then(c=>c.put('/unknown',new Response('preserve'))));
 if(server){server.kill();await once(server,'exit');server=undefined;}
 await expect(async()=>{await expect(fetch(origin)).rejects.toThrow();}).toPass();
 const browser=context.browser()!;const cdp=await browser.newBrowserCDPSession();const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');const pids=processInfo.map(p=>p.id);expect(pids.length).toBeGreaterThan(0);await context.close();expect(browser.isConnected()).toBe(false);await expect.poll(()=>pids.filter(running)).toEqual([]);console.log(JSON.stringify({closedBrowserPids:pids,remainingBrowserProcesses:[]}));
 context=await chromium.launchPersistentContext(profile,{headless:true,channel:'chromium'});
 const reopened=await context.newPage();await reopened.goto(`${origin}/projects/hdsp/runs/synthetic-detail`);
 await expect(reopened.getByText('浏览器离线实验版 · 仅合成数据 · 未接入跨端同步')).toBeVisible();
 await expect(reopened.getByRole('heading',{name:'研究记录'})).toBeVisible();
 expect(await reopened.evaluate(()=>caches.has('unknown-cache'))).toBe(true);
 await reopened.reload();await expect(reopened.getByTestId('offline-status')).toHaveText('离线资源已就绪');
 await reopened.screenshot({path:resolve(runtime,'shell-desktop.png'),fullPage:true});
 await reopened.setViewportSize({width:390,height:844});await reopened.screenshot({path:resolve(runtime,'shell-mobile.png'),fullPage:true});
 }finally{try{await context?.close();}finally{if(server?.pid&&server.exitCode===null&&server.signalCode===null){const exited=once(server,'exit');server.kill();await exited;}if(fixture){fixture.closeAllConnections();await new Promise<void>(r=>fixture!.close(()=>r()));}}}
});
