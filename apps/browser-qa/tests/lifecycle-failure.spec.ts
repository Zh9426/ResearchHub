import {test,expect,chromium,type BrowserContext} from '@playwright/test';
import {resolve} from 'node:path';
import {cleanup,startServer,stopServer,launch,runtime,origin} from './lifecycle';

test('close rejection still releases owned QA server',async()=>{
 const server=await startServer();
 try{
  await expect(cleanup(server,[{close:async()=>{throw Error('TEST ONLY close rejection');}} as unknown as BrowserContext])).rejects.toThrow();
  await expect.poll(()=>server.exitCode!==null||server.signalCode!==null).toBe(true);
  await expect(fetch(origin)).rejects.toThrow();
 }finally{await stopServer(server);}
});
test('real target launch failure cleans source and owned server',async()=>{
 const server=await startServer();let source:BrowserContext|undefined;let pids:number[]=[];
 await expect((async()=>{try{
  source=await launch(resolve(runtime,'profiles',`launch-source-${Date.now()}`));
  const cdp=await source.browser()!.newBrowserCDPSession();pids=(await cdp.send('SystemInfo.getProcessInfo')).processInfo.map(p=>p.id);
  await chromium.launchPersistentContext(resolve(runtime,'profiles',`launch-missing-${Date.now()}`),{executablePath:resolve(runtime,'TESTONLY-does-not-exist-browser'),headless:true});
 }finally{await cleanup(server,[source]);}})()).rejects.toThrow(/executable|exist/i);
 expect(source?.browser()?.isConnected()??false).toBe(false);
 await expect.poll(()=>pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(e){if((e as NodeJS.ErrnoException).code==='ESRCH')return false;throw e;}})).toEqual([]);
 expect(server.exitCode!==null||server.signalCode!==null).toBe(true);
 await expect(fetch(origin)).rejects.toThrow();
});
