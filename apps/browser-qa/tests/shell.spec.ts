import {test,expect,type BrowserContext} from '@playwright/test';
import {runtime,origin,startServer,stopServer,launch,closeBrowser} from './lifecycle';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import os from 'node:os';
test('壳初始化后停止服务器、关闭浏览器进程、同profile离线直访详情',async()=>{
 mkdirSync(runtime,{recursive:true});
 let server:ReturnType<typeof spawn>|undefined;
 let context:BrowserContext|undefined;
 try {
 server=await startServer();
 const profile=resolve(runtime,'profiles',`shell-${Date.now()}`);
 context=await launch(profile);
 console.log(JSON.stringify({browser:context.browser()?.version(),os:`${os.platform()} ${os.release()} ${os.arch()}`,origin}));
 const page=await context.newPage();await page.goto(origin);
 await expect(page.getByText('浏览器离线实验版 · 仅合成数据 · 未接入跨端同步')).toBeVisible();
 await page.getByRole('button',{name:'初始化离线资源'}).click();
 await expect(page.getByTestId('offline-status')).toHaveText('离线资源已就绪');
 const shellKeys=await page.evaluate(async()=>{const names=await caches.keys();const cache=await caches.open(names.find(n=>n.startsWith('researchhub-browser-qa-shell-'))!);return (await cache.keys()).map(r=>new URL(r.url).pathname).sort();});
 expect(shellKeys).toEqual(['/app.css','/app.js','/icon.svg','/index.html']);
 const collision=spawn(process.execPath,['scripts/server.mjs'],{stdio:'pipe'});expect((await once(collision,'exit'))[0]).toBe(1);expect((await fetch(origin)).ok).toBe(true);
 expect((await fetch(origin+'/api/projects')).status).toBe(404);
 await page.evaluate(()=>caches.open('unknown-cache').then(c=>c.put('/unknown',new Response('preserve'))));
 if(server){await stopServer(server);server=undefined;}
 await expect(async()=>{await expect(fetch(origin)).rejects.toThrow();}).toPass();
 await closeBrowser(context);
 context=await launch(profile);
 const reopened=await context.newPage();await reopened.goto(`${origin}/projects/hdsp/runs/synthetic-detail`);
 await expect(reopened.getByText('浏览器离线实验版 · 仅合成数据 · 未接入跨端同步')).toBeVisible();
 await expect(reopened.getByRole('heading',{name:'研究记录'})).toBeVisible();
 expect(await reopened.evaluate(()=>caches.has('unknown-cache'))).toBe(true);
 await reopened.reload();await expect(reopened.getByTestId('offline-status')).toHaveText('离线资源已就绪');
 await reopened.screenshot({path:resolve(runtime,'shell-desktop.png'),fullPage:true});
 await reopened.setViewportSize({width:390,height:844});await reopened.screenshot({path:resolve(runtime,'shell-mobile.png'),fullPage:true});
 }finally{try{await context?.close();}finally{if(server)await stopServer(server);}}
});
