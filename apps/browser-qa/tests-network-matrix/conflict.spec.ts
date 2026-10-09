import {conflictRoundTrip} from './conflict-roundtrip';
import {test,expect,chromium,type BrowserContext} from '@playwright/test';
import {writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {summarizeError} from '../scripts/network-evidence-reporter';
const root=process.env.RH_B2_RESULTS!;
let phase='START',preflights=0,signedPosts=0,version='',lastDiagnostic:string|null=null,baselineDiagnostic:unknown=null;
function mark(next:string,diagnostic:string|null=null,baseline?:unknown){phase=next;lastDiagnostic=diagnostic;if(baseline!==undefined)baselineDiagnostic=baseline;writeFileSync(resolve(root,'phase.json'),JSON.stringify({phase,diagnostic,baselineDiagnostic,preflights,signedPosts,chromium:version}),{mode:0o600});}
async function launch(name:string){return chromium.launchPersistentContext(resolve(root,name),{headless:true,channel:'chromium',args:['--host-resolver-rules=MAP localhost 127.0.0.1'],viewport:{width:1440,height:1000}});}
async function close(context:BrowserContext){const browser=context.browser();let pids:number[]=[];try{if(!browser)throw Error('BROWSER_HANDLE_MISSING');const cdp=await browser.newBrowserCDPSession();const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');pids=processInfo.map(p=>p.id);expect(pids.length).toBeGreaterThan(0);}finally{await context.close();}expect(browser!.isConnected()).toBe(false);await expect.poll(()=>pids.filter(pid=>{try{process.kill(pid,0);return true;}catch(e){if((e as NodeJS.ErrnoException).code==='ESRCH')return false;throw e;}})).toEqual([]);}
async function certificate(context:BrowserContext,url:string,expected:string){const p=await context.newPage();let code='NO_CERTIFICATE_FAILURE';try{await p.goto(url);}catch(e){code=String(e).includes(expected)?expected:String(e).includes('ERR_CONNECTION_REFUSED')?'ERR_CONNECTION_REFUSED':'OTHER_NETWORK_FAILURE';}finally{await p.close();}mark(phase,code);expect(code).toBe(expected);}
test('C conflict actual browser pairing and candidate convergence',async()=>{
 let context:BrowserContext|undefined,primaryFailure=false;
 try{
  mark('BROWSER_LAUNCH');context=await launch('profile');
  mark('BROWSER_VERSION');version=context.browser()!.version();
  if(process.env.RH_B2_TLS_CASE==='untrusted'){mark('UNTRUSTED_CA');await certificate(context,'https://127.0.0.1:38001/v1/hello','ERR_CERT_AUTHORITY_INVALID');return;}
  mark('HOSTNAME_NEGATIVE');await certificate(context,'https://localhost:38001/v1/hello','ERR_CERT_COMMON_NAME_INVALID');
  const b=await context.newPage(),pc=await context.newPage();
  const cdp=await context.newCDPSession(b);await cdp.send('Network.enable');
  const kinds=new Map<string,string>();
  cdp.on('Network.requestWillBeSent',(e:any)=>{if(e.request.url==='https://127.0.0.1:38001/v1/hello')kinds.set(e.requestId,e.request.method);});
  cdp.on('Network.responseReceived',(e:any)=>{const kind=kinds.get(e.requestId);if(kind==='OPTIONS'&&e.response.status===204)preflights++;if(kind==='POST'&&e.response.status===200)signedPosts++;});
  mark('FRESH_UI');await b.goto('http://127.0.0.1:3314');await pc.goto('http://127.0.0.1:3315');
  expect(await b.evaluate(async()=> (await window.__LOCAL_QA__!.snapshot()).projects.length)).toBe(0);
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
  // Reload after proof persistence: receipt must resume the exact saved session.
  await b.reload();await b.getByLabel('PC 完成回执与签名绑定').fill(result);
  mark('INJECTED_HELLO_NETWORK_LOSS');await b.route('https://127.0.0.1:38001/v1/hello',route=>route.abort('failed'));
  await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).not.toHaveText('');
  expect(await b.evaluate(async()=> (await window.__LOCAL_QA__!.snapshot()).projects.length)).toBe(0);
  await b.unroute('https://127.0.0.1:38001/v1/hello');await b.reload();await b.getByLabel('PC 完成回执与签名绑定').fill(result);
  mark('B_VERIFY_AND_FETCH');await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).toHaveText('加入完成 · VERIFIED · Relay hello 已确认',{timeout:30000});
  expect(preflights).toBeGreaterThan(0);expect(signedPosts).toBeGreaterThan(0);
  expect(await b.evaluate(async()=> (await window.__LOCAL_QA__!.snapshot()).projects.length)).toBe(1);
  const expected=JSON.parse(result).signed_binding.binding;
  const actual=await b.evaluate(async()=>{const s=await window.__LOCAL_QA__!.snapshot();return {project:s.projects[0],device:s.identity!.device_id};});
  expect(actual.project.id).toBe(expected.semantic_project_id);expect(actual.device).toBe(expected.principal.device_id);expect(actual.project.module_snapshot).toEqual(expected.module_snapshot);expect(actual.project.module_hash).toBe(expected.local_module_hash.value);
  const binding=await b.evaluate(async(id)=>{const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-browser-sync-qa-business-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});try{return await new Promise<any>((ok,no)=>{const r=db.transaction('meta').objectStore('meta').get('binding:'+id);r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});}finally{db.close();}},expected.semantic_project_id);
  expect(binding.state).toBe('VERIFIED');expect(binding.generation).toBe(1);expect(binding.binding).toEqual(expected);
  mark('RECEIPT_RESUME');await b.reload();await b.getByLabel('PC 完成回执与签名绑定').fill(result);await b.getByRole('button',{name:'验证回执并加入'}).click();await expect(b.getByTestId('join-status')).toHaveText('加入完成 · VERIFIED · Relay hello 已确认',{timeout:30000});
  await conflictRoundTrip(b,pc,mark);
  mark('BAD_PROOF');const rejected=await b.evaluate(async()=>{const r=await fetch('https://127.0.0.1:38001/v1/hello',{method:'POST',credentials:'omit',redirect:'error',headers:{'content-type':'application/json','x-rh-proof':'AAAA'},body:'{}'});return r.status;});expect(rejected).toBe(401);
  mark('UNAUTHORIZED_ORIGIN');const opaque=await context.newPage(),ocdp=await context.newCDPSession(opaque);await ocdp.send('Network.enable');let preflight403=false,nullOrigin=false;const options=new Set<string>();
  ocdp.on('Network.requestWillBeSent',(e:any)=>{if(e.request.url==='https://127.0.0.1:38001/v1/hello'&&e.request.method==='OPTIONS'){options.add(e.requestId);if(e.request.headers.Origin==='null'||e.request.headers.origin==='null')nullOrigin=true;}});
  ocdp.on('Network.responseReceived',(e:any)=>{if(options.has(e.requestId)&&e.response.status===403)preflight403=true;});
  ocdp.on('Network.responseReceivedExtraInfo',(e:any)=>{if(options.has(e.requestId)&&e.statusCode===403)preflight403=true;});
  const denied=await opaque.evaluate(async()=>{try{await fetch('https://127.0.0.1:38001/v1/hello',{method:'POST',credentials:'omit',headers:{'content-type':'application/json','x-rh-proof':'AAAA'},body:'{}'});return 'UNEXPECTED_ALLOWED';}catch(e){return e instanceof TypeError?'CORS_FETCH_TYPEERROR':'OTHER';}});expect(denied).toBe('CORS_FETCH_TYPEERROR');expect(nullOrigin).toBe(true);expect(preflight403).toBe(true);await opaque.close();
  mark('SCREENSHOTS');await b.screenshot({path:resolve(root,'desktop.png'),mask:[b.locator('textarea'),b.locator('input')]});await b.setViewportSize({width:390,height:844});await b.screenshot({path:resolve(root,'mobile.png'),mask:[b.locator('textarea'),b.locator('input')]});
  mark('COMPLETE');
 }catch(e){primaryFailure=true;try{mark(phase,lastDiagnostic??'ASSERTION_OR_OPERATION_FAILED');}catch{/* Preserve the original failure if its evidence write also fails. */}throw e;}finally{
  if(context){
   const saveCleanup=(value:unknown)=>writeFileSync(resolve(root,'cleanup.json'),JSON.stringify(value),{mode:0o600});
   let cleanupError:unknown;
   try{saveCleanup({state:'START'});}catch(error){cleanupError=error;}
   try{await close(context);}catch(error){cleanupError??=error;}
   try{saveCleanup(cleanupError?{state:'FAILED',error:summarizeError(cleanupError instanceof Error?cleanupError:{message:String(cleanupError)})}:{state:'PASS'});}catch(error){cleanupError??=error;}
   if(cleanupError&&!primaryFailure)throw cleanupError;
  }
 }
});
