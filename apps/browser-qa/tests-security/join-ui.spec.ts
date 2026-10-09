import {test,expect,chromium} from '@playwright/test';
import {resolve} from 'node:path';
test('fresh normal browser exposes explicit native join without demo seeds',async()=>{
 const context=await chromium.launchPersistentContext(resolve('../../storage/runtime/browser-sync-qa/b2-local/'+process.env.RH_B2_LOCAL_ATTEMPT+'/profile'),{headless:true,channel:'chromium'});
 try{const page=await context.newPage();await page.goto('http://127.0.0.1:3314');await expect(page.getByRole('button',{name:'生成本设备加入公钥'})).toBeVisible();await page.getByRole('button',{name:'生成本设备加入公钥'}).click();await expect(page.getByLabel('本设备公开身份')).not.toHaveValue('');const identity=JSON.parse(await page.getByLabel('本设备公开身份').inputValue());await page.reload();await page.getByRole('button',{name:'生成本设备加入公钥'}).click();await expect(page.getByLabel('本设备公开身份')).not.toHaveValue('');expect(JSON.parse(await page.getByLabel('本设备公开身份').inputValue()).device_id).toBe(identity.device_id);await expect(page.getByRole('button',{name:'确认核对并生成配对证明'})).toBeDisabled();expect(await page.evaluate(async()=> (await window.__LOCAL_QA__!.snapshot()).projects.length)).toBe(0);}finally{await context.close();}
});



test('persisted BindingRecord drives status; preview never changes authorization (synthetic state fixture)',async()=>{
 const context=await chromium.launchPersistentContext(resolve('../../storage/runtime/browser-sync-qa/b2-local/'+process.env.RH_B2_LOCAL_ATTEMPT+'/binding-profile'),{headless:true,channel:'chromium'});
 try{
  const page=await context.newPage();await page.goto('http://127.0.0.1:3314');
  await expect(page.getByText('尚未加入受信项目。尚未验证项目所有者和设备授权，暂不能转换或发送。')).toBeVisible();
  await page.evaluate(async()=>{const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-browser-sync-qa-business-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});try{await new Promise<void>((ok,no)=>{const t=db.transaction('meta','readwrite');t.objectStore('meta').put({id:'binding:00000000-0000-4000-8000-000000000001',state:'VERIFIED',generation:1,binding:{semantic_project_id:'00000000-0000-4000-8000-000000000001'}});t.oncomplete=()=>ok();t.onabort=()=>no(t.error);});}finally{db.close();}});
  await page.reload();
  await expect(page.getByText('已存在 VERIFIED 项目绑定；下方独立预览不会更改已有授权。')).toBeVisible();
  await expect(page.getByText('尚未加入受信项目。尚未验证项目所有者和设备授权，暂不能转换或发送。')).toHaveCount(0);
  await page.getByLabel('公共项目绑定（待验证预览）').fill('{}');await page.getByRole('button',{name:'预览公共绑定'}).click();await expect(page.getByText('绑定预览受阻')).toBeVisible();
  await expect(page.getByText('已存在 VERIFIED 项目绑定；下方独立预览不会更改已有授权。')).toBeVisible();
 }finally{await context.close();}
});
