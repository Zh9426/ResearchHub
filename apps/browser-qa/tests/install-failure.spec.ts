import {test,expect,chromium,type BrowserContext} from '@playwright/test';
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {once} from 'node:events';
const runtime=resolve('../../storage/runtime/browser-local-qa');
process.env.PLAYWRIGHT_BROWSERS_PATH=resolve(runtime,'browsers');
test('首次SW静态资源503明确失败并恢复按钮，修复资源后可重试',async()=>{
 let failAsset=false, failures=0;
 const server=createServer((req,res)=>{const path=req.url==='/'?'index.html':req.url!.slice(1);if(failAsset&&path==='icon.svg'){failures++;res.writeHead(503);res.end('TEST ONLY injected shell asset failure');return;}const types:Record<string,string>={'index.html':'text/html','app.js':'text/javascript','sw.js':'text/javascript','app.css':'text/css','icon.svg':'image/svg+xml'};if(!types[path]){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',types[path]);res.setHeader('Cache-Control','no-store');res.end(readFileSync(resolve(runtime,'dist',path)));});
 let context:BrowserContext|undefined;
 try{
 server.listen(3313,'127.0.0.1');await once(server,'listening');
 context=await chromium.launchPersistentContext(resolve(runtime,'profiles',`asset-failure-${Date.now()}`),{headless:true,channel:'chromium'});
 const page=await context.newPage();await page.goto('http://127.0.0.1:3313');failAsset=true;
 await page.getByRole('button',{name:'初始化离线资源'}).click();
 await expect(page.getByRole('alert')).toContainText('离线资源初始化失败');
 await expect(page.getByRole('button',{name:'初始化离线资源'})).toBeEnabled();
 await expect(page.getByTestId('offline-status')).not.toHaveText('离线资源已就绪');
 expect(failures).toBeGreaterThan(0);console.log(JSON.stringify({injected503:failures,result:'failure visible; retry enabled'}));
 failAsset=false;await page.getByRole('button',{name:'初始化离线资源'}).click();
 await expect(page.getByTestId('offline-status')).toHaveText('离线资源已就绪');
 console.log('asset restored: retry initialized real service worker');
 }finally{try{await context?.close();}finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));}}
});
