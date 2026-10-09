import {test, expect, chromium, type Page, type BrowserContext} from '@playwright/test';
import {readFileSync, writeFileSync, existsSync, renameSync, chmodSync} from 'node:fs';
import {resolve} from 'node:path';
import {withCleanup} from '../tests-owner/cleanup';
import {rethrowPrivateFailure} from './failure-private-evidence';
import {summarizeError,safeManualDiagnostic} from '../scripts/network-evidence-reporter';
const root = process.env.RH_B2_RESULTS!, scenario = process.env.RH_FAILURE_CASE!, control = process.env.RH_FAILURE_CONTROL!;
let version = '', phase = 'START', step = 0, operation = 'NONE', diagnostic:string|null=null;
const checks:Record<string,boolean>={};
const snapshots:{stage:string;digest:string;objects:number;operations:number;audit:number;mappings:number;transactions:number;pending:number}[]=[];
function evidenceSnapshot(stage:string,s:any){snapshots.push({stage,digest:s.snapshot_digest,objects:s.objects.length,operations:s.operations.length,audit:s.audit.length,mappings:s.mappings.length,transactions:s.kernel.reduce((sum:number,k:any)=>sum+Object.keys(k.state.transactions).length,0),pending:s.pending.length});persist();}
const progress=(value:string)=>{operation=value;persist();};
function persist(){writeFileSync(resolve(root,'phase.json'),JSON.stringify({phase,operation,diagnostic,checks,snapshots,chromium:version}),{mode:0o600});}
function mark(next:string) { phase=next;operation='NONE';persist(); }
async function action(action:string) {
 progress(action);
 const current=++step, prefix=String(current).padStart(3,'0');
 const temporary=resolve(control,prefix+'.request.tmp');
 writeFileSync(temporary,JSON.stringify({version:1,case:scenario,step:current,action}),{flag:'wx',mode:0o644});
 chmodSync(temporary,0o644);renameSync(temporary,resolve(control,prefix+'.request.json'));
 const response=resolve(control,prefix+'.response.json');
 await expect.poll(()=>existsSync(response),{timeout:90000}).toBe(true);
 expect(JSON.parse(readFileSync(response,'utf8'))).toEqual({version:1,case:scenario,step:current,status:'PASS'});
}
async function launch(name:string) { return chromium.launchPersistentContext(resolve(root,name),{headless:true,channel:'chromium',args:['--host-resolver-rules=MAP localhost 127.0.0.1'],viewport:{width:1440,height:1000}}); }
async function close(context:BrowserContext) {
 const browser=context.browser(); let pids:number[]=[];
 await withCleanup(async()=>{if(!browser)throw Error('BROWSER_HANDLE_MISSING');const cdp=await browser.newBrowserCDPSession();pids=(await cdp.send('SystemInfo.getProcessInfo')).processInfo.map(p=>p.id);expect(pids.length).toBeGreaterThan(0);},[
  ()=>context.close(),
  async()=>{if(browser)expect(browser.isConnected()).toBe(false);if(pids.length)await expect.poll(()=>pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(e){if((e as NodeJS.ErrnoException).code==='ESRCH')return false;throw e;}})).toEqual([]);},
 ]);
}
async function save(p:Page) { progress(p.url().startsWith('http://127.0.0.1:3315')?'PC_SAVE':'B_SAVE');await p.getByRole('button',{name:'保存到本机',exact:true}).click(); await expect(p.getByTestId('local-save')).toHaveText('已保存到本机'); }
async function sync(p:Page) { progress(p.url().startsWith('http://127.0.0.1:3315')?'PC_SYNC':'B_SYNC');try{await p.getByRole('button',{name:'立即同步',exact:true}).click();await expect(p.getByTestId('manual-sync-status')).toContainText('本轮发送',{timeout:60000});}catch(error){try{diagnostic=safeManualDiagnostic(await p.getByTestId('manual-sync-diagnostic').textContent({timeout:1000}));persist();}catch{}throw error;} }
async function choose(p:Page,title:string) { await p.locator('button.qa-record').filter({hasText:title}).click(); await expect(p.getByLabel('标题',{exact:true})).toHaveValue(title); }
async function durable(p:Page) {
 return p.evaluate(async()=>{
  const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-browser-sync-qa-business-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});
  try{const value=await new Promise<any>((ok,no)=>{
   const tx=db.transaction(['projects','objects','operations','audit','meta'],'readonly'),result:any={};
   for(const name of ['projects','objects','operations','audit','meta']) { const r=tx.objectStore(name).getAll(); r.onsuccess=()=>{result[name]=r.result;}; }
   tx.oncomplete=()=>{
    const all=result.meta; delete result.meta;
    result.mappings=all.filter((r:any)=>r.id.startsWith('mapping:')).map((r:any)=>({...r,envelope:r.envelope?Array.from(r.envelope):undefined}));
    result.kernel=all.filter((r:any)=>r.id.startsWith('record-kernel:'));
    result.pending=all.filter((r:any)=>r.id.startsWith('pending-operation:'));
    result.cursor=all.filter((r:any)=>r.id.startsWith('relay-cursor:'));
    result.relay=all.filter((r:any)=>r.id.startsWith('relay-stored:'));
    ok(result);
   };tx.onabort=()=>no(tx.error??Error('SNAPSHOT_ABORTED'));
  });const hashed=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));return {...value,snapshot_digest:Array.from(new Uint8Array(hashed),b=>b.toString(16).padStart(2,'0')).join('')};}finally{db.close();}
 });
}
const RUN='SYNTHETIC_MATRIX_RUN_7c91', NOTE='SYNTHETIC_MATRIX_NOTE_a05d', OBS='SYNTHETIC_MATRIX_OBSERVATION_9ea2', STAR='SYNTHETIC_MATRIX_STAR_39ef';
async function records(p:Page) {
 mark('LOCAL_RUN_CREATE');await p.getByRole('button',{name:'新建 Run',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill(RUN);await save(p);
 mark('LOCAL_RUN_UPDATE');await p.getByLabel('观察',{exact:true}).fill(OBS+' 中文\n ');await save(p);
 mark('LOCAL_RUN_STAR');await p.getByRole('button',{name:'设为星标',exact:true}).click();await expect(p.getByRole('button',{name:'取消星标',exact:true})).toBeVisible();
 mark('LOCAL_RUN_STAR_NOTE');await p.getByLabel('星标说明（可选）',{exact:true}).fill(STAR);await save(p);
 mark('LOCAL_NOTE_CREATE');await p.getByRole('button',{name:'新建 Note',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill(NOTE);await p.getByLabel('笔记正文',{exact:true}).fill(NOTE+' 中文\n ');await save(p);
}
async function verifyRecords(p:Page) {
 await choose(p,RUN);await expect(p.getByLabel('观察',{exact:true})).toHaveValue(OBS+' 中文\n ');await expect(p.getByRole('button',{name:'取消星标',exact:true})).toBeVisible();await expect(p.getByLabel('星标说明（可选）',{exact:true})).toHaveValue(STAR);const runId=new URL(p.url()).pathname.split('/').at(-1);
 await choose(p,NOTE);await expect(p.getByLabel('笔记正文',{exact:true})).toHaveValue(NOTE+' 中文\n ');return {runId,noteId:new URL(p.url()).pathname.split('/').at(-1)};
}

async function pair(b:Page,pc:Page) {
  await b.getByRole('button',{name:'生成本设备加入公钥'}).click();
  await expect(b.getByLabel('本设备公开身份')).not.toHaveValue('');
  await pc.getByLabel('B 设备公开身份',{exact:true}).fill(await b.getByLabel('本设备公开身份').inputValue());
  mark('OWNER_START');await pc.getByRole('button',{name:'开始设备配对'}).click();await expect(pc.getByTestId('pc-sas')).toBeVisible({timeout:30000});
  const start=JSON.parse(await pc.getByLabel('PC 配对公开输出').inputValue());
  await b.getByLabel('PC challenge 与 bootstrap').fill(JSON.stringify(start));await b.getByRole('button',{name:'查看待核对指纹'}).click();
  await expect(b.getByTestId('join-fingerprint')).toContainText(start.challenge.recipient.fingerprint);
  await expect(pc.getByTestId('pc-fingerprint')).toContainText(start.challenge.recipient.fingerprint);
  await b.getByLabel('从可信 PC 独立核对的 Owner root').fill((await pc.getByTestId('pc-owner-root').innerText()).replace('Owner root ',''));
  await b.getByLabel('从可信 PC 独立核对的 Recovery root').fill((await pc.getByTestId('pc-recovery-root').innerText()).replace('Recovery root ',''));
  await b.getByLabel('从可信 PC 独立核对的 SAS').fill((await pc.getByTestId('pc-sas').innerText()).replace('SAS ',''));
  await b.getByRole('checkbox',{name:'我已独立核对 PC 信任根、SAS 与本设备指纹'}).check();
  mark('B_NATIVE_PROOF');await b.getByRole('button',{name:'确认核对并生成配对证明'}).click();await expect(b.getByLabel('交给 PC 的配对证明')).not.toHaveValue('');
  await pc.getByLabel('B 配对证明',{exact:true}).fill(await b.getByLabel('交给 PC 的配对证明').inputValue());
  mark('OWNER_CONFIRM');await pc.getByRole('button',{name:'确认 B 配对证明'}).click();await expect(pc.getByLabel('PC 配对公开输出')).toHaveValue(/"stage":"COMPLETE"/,{timeout:30000});
  const result=await pc.getByLabel('PC 配对公开输出').inputValue();
 return result;
}

test('failure matrix uses native UI and owned real services',async()=>{
 let bContext:BrowserContext|undefined, pcContext:BrowserContext|undefined;
 const cleanupErrors:unknown[]=[];
 try{await withCleanup(async()=>{
  mark('BROWSER_LAUNCH');bContext=await launch('profile');pcContext=await launch('pc-profile');version=bContext.browser()!.version();
  let b=await bContext.newPage();const pc=await pcContext.newPage();
  await b.goto('http://127.0.0.1:3314');await pc.goto('http://127.0.0.1:3315');mark('PAIR');
  expect((await durable(b)).projects).toHaveLength(0);const receipt=await pair(b,pc);
  if(scenario==='historical-bootstrap') {
   mark('BOOTSTRAP_HISTORY');await pc.getByRole('button',{name:'新建 Note',exact:true}).click();await pc.getByLabel('标题',{exact:true}).fill('SYNTHETIC before first B install');await pc.getByLabel('笔记正文',{exact:true}).fill('SYNTHETIC history requires bootstrap');await save(pc);await sync(pc);
   await action('VERIFY_DURABLE_COUNTS');await b.getByLabel('PC 完成回执与签名绑定').fill(receipt);await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).toContainText('BOOTSTRAP_REQUIRED',{timeout:30000});
   const state=await durable(b);for(const field of ['projects','objects','operations','audit','kernel','cursor'])expect(state[field]).toEqual([]);checks.bootstrap_no_business_or_cursor=true;
   await action('VERIFY_DURABLE_COUNTS');await action('CASE_FINISH');mark('COMPLETE');return;
  }
  await b.getByLabel('PC 完成回执与签名绑定').fill(receipt);await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).toHaveText('加入完成 · VERIFIED · Relay hello 已确认',{timeout:30000});await expect(b.getByRole('button',{name:'新建 Run',exact:true})).toBeVisible();
  if(scenario==='reopen') {await b.getByRole('button',{name:'初始化离线资源',exact:true}).click();await expect(b.getByTestId('offline-status')).toHaveText('离线资源已就绪');}
  mark('LOCAL_UI');
  if(['reopen','independent-echo'].includes(scenario))await bContext.setOffline(true);
  await records(b);
  const local=await durable(b);evidenceSnapshot('LOCAL_SAVED',local);expect(local.objects).toHaveLength(2);expect(local.operations).toHaveLength(5);expect(local.audit).toHaveLength(5);expect(local.pending).toHaveLength(2);
  if(scenario==='reopen') {
   mark('NORMAL_ALL_PID_REOPEN');await close(bContext);bContext=undefined;
   bContext=await launch('profile');await bContext.setOffline(true);b=await bContext.newPage();await b.goto('http://127.0.0.1:3314');await expect(b.getByTestId('offline-status')).toHaveText('离线资源已就绪');
   expect(await durable(b)).toEqual(local);await verifyRecords(b);checks.offline_cold_start=true;checks.same_profile_reopened=true;checks.all_b_pids_exited_before_reopen=true;await bContext.setOffline(false);
  }
  if(scenario==='independent-echo') {
   mark('INDEPENDENT_OBJECT');await pc.getByRole('button',{name:'新建 Note',exact:true}).click();await pc.getByLabel('标题',{exact:true}).fill('SYNTHETIC independent PC Note');await pc.getByLabel('笔记正文',{exact:true}).fill('SYNTHETIC PC unsent independent body');await save(pc);await bContext.setOffline(false);
  }
  if(scenario==='revoked-write') {
   mark('OWNER_REVOKE');await action('OWNER_REVOKE');await action('VERIFY_DURABLE_COUNTS');
   let denied=0;b.on('response',r=>{if(r.url().startsWith('https://127.0.0.1:38001/v1/messages')&&r.status()===401)denied++;});
   await b.getByRole('button',{name:'立即同步',exact:true}).click();await expect(b.getByTestId('manual-sync-status')).toContainText('同步未完成',{timeout:30000});expect(denied).toBe(1);expect(await durable(b)).toEqual(local);checks.owner_revoked_old_sync_rejected=true;checks.local_operations_preserved=true;checks.local_audit_preserved=true;await verifyRecords(b);await expect(b.getByTestId('record-sync-peer')).toContainText('尚未确认');
   await action('VERIFY_DURABLE_COUNTS');await action('CASE_FINISH');mark('COMPLETE');return;
  }
  if(scenario==='pc-offline') {mark('PC_LOGICAL_OFFLINE');await action('PC_STOP');}
  if(scenario==='ack-loss') {
   mark('ACKLOSS');const sent:string[]=[];
   const capture=(p:Page)=>p.on('request',r=>{if(r.url()==='https://127.0.0.1:38001/v1/messages'&&r.method()==='POST')sent.push(r.postData()!);});capture(b);
   await action('ACKLOSS_ARM');await b.getByRole('button',{name:'立即同步',exact:true}).click();await action('ACKLOSS_WAIT_COMMIT_AND_KILL');
   await expect(b.getByTestId('manual-sync-status')).toContainText('同步未完成',{timeout:30000});expect(sent).toHaveLength(1);
   const failed=await durable(b);evidenceSnapshot('ACK_UNKNOWN',failed);expect(failed.operations).toEqual(local.operations);expect(failed.audit).toEqual(local.audit);expect(failed.pending).toEqual(local.pending);expect(failed.relay).toEqual([]);expect(failed.mappings).toHaveLength(1);expect(failed.mappings[0].envelope.length).toBeGreaterThan(0);
   mark('ACKLOSS_ALL_PID_REOPEN');await close(bContext);bContext=undefined;bContext=await launch('profile');b=await bContext.newPage();capture(b);await b.goto('http://127.0.0.1:3314');expect(await durable(b)).toEqual(failed);checks.same_profile_reopened=true;checks.all_b_pids_exited_before_reopen=true;
   await action('RELAY_START');await sync(b);expect(sent.length).toBe(6);expect(sent[1]).toBe(sent[0]);checks.exact_request_body_repeated=true;
   const resent=await durable(b);expect(resent.mappings.find((m:any)=>m.id===failed.mappings[0].id).envelope).toEqual(failed.mappings[0].envelope);checks.cached_envelope_unchanged=true;
  } else {mark('SEND');await sync(b);}
  if(scenario==='pc-offline') {
   await expect(b.getByTestId('record-sync-relay')).toContainText('已存储这次修改');await expect(b.getByTestId('record-sync-peer')).toContainText('尚未确认');await action('PC_START');await pc.reload();
  }
  mark('PEER_APPLY');await sync(pc);await sync(b);await sync(pc);await sync(b);
  expect(await verifyRecords(pc)).toEqual(await verifyRecords(b));checks.remote_ids_match=true;await expect(b.getByTestId('record-sync-peer')).toContainText('已验证该设备应用了这次修改');
  const settled=await durable(b);evidenceSnapshot('PEER_CONFIRMED',settled);expect(settled.objects).toHaveLength(scenario==='independent-echo'?3:2);expect(settled.operations).toEqual(local.operations);expect(settled.audit).toEqual(local.audit);expect(settled.pending).toEqual([]);checks.local_operations_preserved=true;checks.local_audit_preserved=true;
  if(scenario==='independent-echo') {await choose(b,'SYNTHETIC independent PC Note');await expect(b.getByLabel('笔记正文',{exact:true})).toHaveValue('SYNTHETIC PC unsent independent body');}
  if(scenario==='privacy') {mark('PRIVACY');await action('PRIVACY_AUDIT');}
  else {
   mark('IDEMPOTENT_ECHO');await action('VERIFY_DURABLE_COUNTS');await sync(b);await sync(pc);await sync(b);const repeated=await durable(b);expect(repeated).toEqual(settled);evidenceSnapshot('ECHO_NO_CHANGE',repeated);checks.no_extra_echo_mutations=true;await action('VERIFY_DURABLE_COUNTS');
  }
  await action('CASE_FINISH');mark('COMPLETE');
 },[
  async()=>{if(bContext)try{await close(bContext);}catch(e){cleanupErrors.push(e);throw e;}},
  async()=>{if(pcContext)try{await close(pcContext);}catch(e){cleanupErrors.push(e);throw e;}},
  ()=>writeFileSync(resolve(root,'cleanup.json'),JSON.stringify({state:cleanupErrors.length?'FAILED':'PASS',errors:cleanupErrors.map(e=>summarizeError(e as Error))}),{mode:0o600}),
 ]);}catch(error){rethrowPrivateFailure(error,resolve(root,'failure-details.private.json'));}
});
