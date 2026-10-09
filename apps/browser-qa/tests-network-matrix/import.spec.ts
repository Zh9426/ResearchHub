import {test,expect,chromium,type Page,type BrowserContext} from '@playwright/test';
import {withImportCleanup,createImportFetchCounter} from './import-evidence';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const root=process.env.RH_B2_RESULTS!,source=process.env.RH_IMPORT_SOURCE_DIR!,module=process.env.RH_IMPORT_MODULE!;
const rawPath=resolve(source,'source-rescue.json'),descriptorPath=resolve(source,'source-project.json');
let phase='START',version='';const fetchCounter=createImportFetchCounter();
const mark=(next:string)=>{phase=next;writeFileSync(resolve(root,'phase.json'),JSON.stringify({phase,chromium:version,...fetchCounter.counts()}),{mode:0o600});};
const save=async(p:Page)=>{await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');};
const sync=async(p:Page)=>{await p.getByRole('button',{name:'立即同步',exact:true}).click();await expect(p.getByTestId('manual-sync-status')).toContainText('本轮发送',{timeout:60000});};
async function snapshot(p:Page){return p.evaluate(async()=>await (window as any).__LOCAL_QA__.snapshot());}
async function pair(b:Page,pc:Page){
 await b.getByRole('button',{name:'生成本设备加入公钥'}).click();await expect(b.getByLabel('本设备公开身份')).not.toHaveValue('');
 await pc.getByLabel('B 设备公开身份',{exact:true}).fill(await b.getByLabel('本设备公开身份').inputValue());await pc.getByRole('button',{name:'开始设备配对'}).click();await expect(pc.getByTestId('pc-sas')).toBeVisible({timeout:30000});
 const start=JSON.parse(await pc.getByLabel('PC 配对公开输出').inputValue());await b.getByLabel('PC challenge 与 bootstrap').fill(JSON.stringify(start));await b.getByRole('button',{name:'查看待核对指纹'}).click();
 await expect(b.getByTestId('join-fingerprint')).toContainText(start.challenge.recipient.fingerprint);await expect(pc.getByTestId('pc-fingerprint')).toContainText(start.challenge.recipient.fingerprint);
 for(const [label,id,prefix] of [['从可信 PC 独立核对的 Owner root','pc-owner-root','Owner root '],['从可信 PC 独立核对的 Recovery root','pc-recovery-root','Recovery root '],['从可信 PC 独立核对的 SAS','pc-sas','SAS ']])await b.getByLabel(label).fill((await pc.getByTestId(id).innerText()).replace(prefix,''));
 await b.getByRole('checkbox',{name:'我已独立核对 PC 信任根、SAS 与本设备指纹'}).check();await b.getByRole('button',{name:'确认核对并生成配对证明'}).click();await expect(b.getByLabel('交给 PC 的配对证明')).not.toHaveValue('');
 await pc.getByLabel('B 配对证明',{exact:true}).fill(await b.getByLabel('交给 PC 的配对证明').inputValue());await pc.getByRole('button',{name:'确认 B 配对证明'}).click();await expect(pc.getByLabel('PC 配对公开输出')).toHaveValue(/"stage":"COMPLETE"/,{timeout:30000});
 await b.getByLabel('PC 完成回执与签名绑定').fill(await pc.getByLabel('PC 配对公开输出').inputValue());await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).toHaveText('加入完成 · VERIFIED · Relay hello 已确认',{timeout:30000});
}
test('O explicit 3A source archive and same-identity native replay',async()=>{
 let ownedContext:BrowserContext|undefined,pids:number[]=[];
 await withImportCleanup(async()=>{
  mark('BROWSER_LAUNCH');const context=await chromium.launchPersistentContext(resolve(root,'profile'),{headless:true,channel:'chromium',viewport:{width:1440,height:1000}});ownedContext=context;
  version=context.browser()!.version();mark('BROWSER_VERSION');
  const b=await context.newPage();await b.goto('http://127.0.0.1:3314');expect((await snapshot(b)).projects).toHaveLength(0);
  if(process.env.RH_IMPORT_PHASE==='apply'){
   const cdp=await context.newCDPSession(b);await cdp.send('Network.enable');
   cdp.on('Network.requestWillBeSent',event=>fetchCounter.request(event.requestId,event.request.url,event.request.method));
   cdp.on('Network.responseReceived',event=>fetchCounter.response(event.requestId,event.response.status));
  }
  if(process.env.RH_IMPORT_PHASE==='prepare'){
   mark('IMPORT_SOURCE_UI');const a=await context.newPage();await a.goto('http://127.0.0.1:3313');await a.getByRole('button',{name:'初始化合成工作区',exact:true}).click();await expect(a.getByLabel('项目选择')).toBeVisible();
   for(const alias of ['hdsp','ice']){
    await a.getByLabel('项目选择').selectOption(alias);await a.getByRole('button',{name:'新建 Run',exact:true}).click();await a.getByLabel('标题',{exact:true}).fill('SYNTHETIC '+alias+' 导入 Run');await save(a);
    await a.getByLabel('观察',{exact:true}).fill(' 中文观察第二版 ');await save(a);
    await a.getByLabel('标题',{exact:true}).fill('SYNTHETIC '+alias+' 混合正文星标');await a.getByLabel('观察',{exact:true}).fill(' 中文正文与星标同时修改 ');await a.getByRole('button',{name:'设为星标',exact:true}).click();await a.getByLabel('星标说明（可选）',{exact:true}).fill('混合步骤');await save(a);
    await a.getByLabel('星标说明（可选）',{exact:true}).fill('纯星标步骤');await save(a);
    await a.getByRole('button',{name:'新建 Note',exact:true}).click();await a.getByLabel('标题',{exact:true}).fill('SYNTHETIC '+alias+' 导入 Note');await a.getByLabel('笔记正文',{exact:true}).fill(' 初始笔记\n');await save(a);await a.getByLabel('笔记正文',{exact:true}).fill(' 中文最终笔记\n');await save(a);
   }
   await a.getByLabel('笔记正文',{exact:true}).fill('未保存草稿仅归档，不发送');await a.getByText('诊断与合成草稿救援',{exact:true}).click();const download=a.waitForEvent('download');await a.getByRole('button',{name:'导出合成救援包',exact:true}).click();await (await download).saveAs(rawPath);
   const pack=JSON.parse(readFileSync(rawPath,'utf8')),project=pack.content.projects.find((p:any)=>p.module_id===module);expect(pack.content.drafts).toHaveLength(1);
   await b.getByLabel('3A 完整合成救援包').setInputFiles(rawPath);await b.getByLabel('选择重放项目').selectOption(project.id);
   const descriptor=b.waitForEvent('download');await b.getByRole('button',{name:'下载新 PC 初始化来源描述',exact:true}).click();await (await descriptor).saveAs(descriptorPath);
   expect(JSON.parse(readFileSync(descriptorPath,'utf8')).project).toEqual(project);expect((await snapshot(b)).objects).toHaveLength(0);
   mark('IMPORT_SOURCE_PREPARED');return;
  }
  const pack=JSON.parse(readFileSync(rawPath,'utf8')),descriptor=JSON.parse(readFileSync(descriptorPath,'utf8')),project=descriptor.project,selected=pack.content.objects.filter((o:any)=>o.project_id===project.id);
  expect(project.module_id).toBe(module);mark('IMPORT_NORMAL_PAIRING');const pc=await context.newPage();await pc.goto('http://127.0.0.1:3315');await pair(b,pc);
  const before=await snapshot(b);expect(before.projects[0].id).toBe(project.id);expect(before.projects[0].module_snapshot).toEqual(project.module_snapshot);expect(before.projects[0].module_hash).toBe(project.module_hash);
  mark('IMPORT_PREVIEW');await b.getByLabel('3A 完整合成救援包').setInputFiles(rawPath);await b.getByLabel('选择重放项目').selectOption(project.id);await b.getByRole('button',{name:'只读预览导入',exact:true}).click();await expect(b.getByText(/字段验证通过/)).toBeVisible();expect(await snapshot(b)).toEqual(before);
  mark('IMPORT_CONFIRM');await b.getByRole('button',{name:'确认归档并重放已保存历史',exact:true}).click();await expect(b.getByTestId('import-status')).toContainText('尚未发送至 PC');const imported=await snapshot(b);
  expect(imported.objects.sort((a:any,b:any)=>a.id.localeCompare(b.id))).toEqual(selected.sort((a:any,b:any)=>a.id.localeCompare(b.id)));expect(imported.operations).toHaveLength(pack.content.operations.filter((o:any)=>o.project_id===project.id).length);
  await b.getByRole('button',{name:'确认归档并重放已保存历史',exact:true}).click();await expect(b.getByTestId('import-status')).toContainText('尚未发送至 PC');expect(await snapshot(b)).toEqual(imported);
  mark('IMPORT_NATIVE_SEND');await sync(b);await sync(pc);await sync(b);
  for(const object of selected){await pc.locator('button.qa-record').filter({hasText:object.title}).click();expect(new URL(pc.url()).pathname.split('/').at(-1)).toBe(object.id);if(object.kind==='Run'){await expect(pc.getByLabel('观察',{exact:true})).toHaveValue(object.observation);await expect(pc.getByLabel('星标说明（可选）',{exact:true})).toHaveValue(object.highlight_note);}else await expect(pc.getByLabel('笔记正文',{exact:true})).toHaveValue(object.body);}
  const pcSnapshot=await pc.evaluate(async()=>await(await fetch('/api/snapshot')).json());expect(pcSnapshot.records).toHaveLength(selected.length);
  mark('IMPORT_PC_RETURN');const note=selected.find((o:any)=>o.kind==='Note');await pc.locator('button.qa-record').filter({hasText:note.title}).click();await pc.getByLabel('笔记正文',{exact:true}).fill('PC 回传中文修改');await save(pc);await sync(pc);await sync(b);await b.locator('button.qa-record').filter({hasText:note.title}).click();await expect(b.getByLabel('笔记正文',{exact:true})).toHaveValue('PC 回传中文修改');
  const mapping=b.waitForEvent('download');await b.getByRole('button',{name:'下载旧操作至新操作映射',exact:true}).click();await(await mapping).saveAs(resolve(root,'import-mapping.json'));
  const mapped=JSON.parse(readFileSync(resolve(root,'import-mapping.json'),'utf8'));expect(mapped.wireMap.every((m:any)=>m.wire?.conversion==='CONVERTED')).toBe(true);
  expect(fetchCounter.counts().preflights).toBeGreaterThan(0);expect(fetchCounter.counts().signedPosts).toBeGreaterThan(0);
  await b.getByRole('region',{name:'显式导入 3A 救援包'}).screenshot({path:resolve(root,'import-desktop.png')});await b.setViewportSize({width:390,height:844});await b.getByRole('region',{name:'显式导入 3A 救援包'}).screenshot({path:resolve(root,'import-mobile.png')});mark('IMPORT_COMPLETE');
 },[
  ()=>mark(phase),
  async()=>{if(!ownedContext)return;const browser=ownedContext.browser();if(!browser)throw Error('BROWSER_HANDLE_MISSING');const cdp=await browser.newBrowserCDPSession();pids=(await cdp.send('SystemInfo.getProcessInfo')).processInfo.map(p=>p.id);expect(pids.length).toBeGreaterThan(0);},
  async()=>{if(!ownedContext)return;const browser=ownedContext.browser();await ownedContext.close();if(browser)expect(browser.isConnected()).toBe(false);},
  async()=>{await expect.poll(()=>pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(error){if((error as NodeJS.ErrnoException).code==='ESRCH')return false;throw error;}})).toEqual([]);},
 ],summary=>writeFileSync(resolve(root,'cleanup.json'),JSON.stringify(summary),{mode:0o600}));
});
