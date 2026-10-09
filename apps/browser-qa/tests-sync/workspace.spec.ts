import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {launch,closeBrowser,stopServer} from '../tests/lifecycle';
test('3B独立工作台：星标专门命令保留脏正文并拒绝跨tab旧版本',async()=>{
 const server=spawn(process.execPath,['scripts/server.mjs'],{env:{...process.env,RH_QA_PROFILE:'sync'},stdio:'pipe'});
 await new Promise<void>((ok,no)=>{server.stdout!.on('data',d=>{if(String(d).includes('QA_READY'))ok();});server.on('exit',c=>no(Error(`server ${c}`)));});
 const context=await launch(resolve('../../storage/runtime/browser-sync-qa/a2/profiles',`test-${Date.now()}`));
 try{console.log(JSON.stringify({browser:context.browser()!.version(),scope:'SYNTHETIC / ISOLATED 3B',networkGate:'NOT VERIFIED'}));const p=await context.newPage();await p.goto('http://127.0.0.1:3314');await expect(p.getByRole('note')).toContainText('受控同步实验版 · 仅合成数据');
 await p.getByRole('button',{name:'初始化离线资源',exact:true}).click();await expect(p.getByTestId('offline-status')).toHaveText('离线资源已就绪');await context.setOffline(true);
 await p.getByRole('button',{name:'初始化合成工作区',exact:true}).click();await p.getByRole('button',{name:'新建 Run',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC 星标隔离');await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
 await p.getByRole('textbox',{name:'观察',exact:true}).fill('  未保存的中文 🧪\n');await p.getByRole('button',{name:'设为星标',exact:true}).click();await expect(p.getByRole('button',{name:'取消星标',exact:true})).toBeVisible();
 const snap=()=>p.evaluate(()=> (window as any).__LOCAL_QA__.snapshot());
 const s=await snap();expect(s.objects[0].is_highlighted).toBe(true);expect(s.objects[0].observation).toBe('');expect(s.operations).toHaveLength(2);expect(s.audit).toHaveLength(2);await expect(p.getByRole('textbox',{name:'观察',exact:true})).toHaveValue('  未保存的中文 🧪\n');
 const tab=await context.newPage();await tab.goto(p.url());await tab.getByRole('textbox',{name:'观察',exact:true}).fill('另一tab持久正文');await tab.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(tab.getByTestId('local-save')).toHaveText('已保存到本机');await p.getByRole('button',{name:'取消星标',exact:true}).click();await expect(p.getByRole('alert')).toContainText('其他标签页修改');expect((await snap()).objects[0].observation).toBe('另一tab持久正文');await expect(p.getByRole('textbox',{name:'观察',exact:true})).toHaveValue('  未保存的中文 🧪\n');
 expect((await p.evaluate(()=>indexedDB.databases())).map(x=>x.name)).toEqual(['researchhub-browser-sync-qa-business-v1']);
 await p.screenshot({path:test.info().outputPath('synthetic-desktop.png'),fullPage:true});await p.setViewportSize({width:390,height:844});await p.screenshot({path:test.info().outputPath('synthetic-mobile-viewport.png'),fullPage:true});
 }finally{await closeBrowser(context);await stopServer(server);}
});
