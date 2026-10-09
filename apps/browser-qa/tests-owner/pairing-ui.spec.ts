import {test,expect,chromium,type BrowserContext} from '@playwright/test';
import {writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {startPc,stopPc} from '../tests-pc/lifecycle';
import {withCleanup} from './cleanup';
const root=resolve('../../storage/runtime/browser-sync-qa/b2-local',process.env.RH_B2_LOCAL_ATTEMPT!);
test('native B public identity passes actual owner start and confirm canonical API',async()=>{
 const pcServer=await startPc(['--node',process.env.RH_B2_OWNER_NODE!]);let context:BrowserContext|undefined;
 const statuses:{action:string;status:number;code:string|null}[]=[];
 await withCleanup(async()=>{
  context=await chromium.launchPersistentContext(resolve(root,'profile'),{headless:true,channel:'chromium'});
  const b=await context.newPage(),pc=await context.newPage();
  pc.on('response',async response=>{const action=response.url().match(/\/api\/pairing\/(start|confirm)$/)?.[1];if(action){let code=null;try{const body=await response.json();if(['CANONICAL_PAIRING_REQUEST_REQUIRED','PAIRING_REJECTED_CHECK_STATUS','RELAY_UNAVAILABLE_RESUME_REQUIRED'].includes(body.error))code=body.error;}catch{}statuses.push({action,status:response.status(),code});}});
  await b.goto('http://127.0.0.1:3314');await pc.goto('http://127.0.0.1:3315');
  await b.getByRole('button',{name:'生成本设备加入公钥'}).click();await expect(b.getByLabel('本设备公开身份')).not.toHaveValue('');
  await pc.getByLabel('B 设备公开身份',{exact:true}).fill(await b.getByLabel('本设备公开身份').inputValue());
  await pc.getByRole('button',{name:'开始设备配对'}).click();await expect(pc.getByTestId('pc-sas')).toBeVisible({timeout:15000});
  const started=await pc.getByLabel('PC 配对公开输出').inputValue();
  await b.getByLabel('PC challenge 与 bootstrap').fill(started);await b.getByRole('button',{name:'查看待核对指纹'}).click();
  await b.getByLabel('从可信 PC 独立核对的 Owner root').fill((await pc.getByTestId('pc-owner-root').innerText()).replace('Owner root ',''));
  await b.getByLabel('从可信 PC 独立核对的 Recovery root').fill((await pc.getByTestId('pc-recovery-root').innerText()).replace('Recovery root ',''));
  await b.getByLabel('从可信 PC 独立核对的 SAS').fill((await pc.getByTestId('pc-sas').innerText()).replace('SAS ',''));
  await b.getByRole('checkbox',{name:'我已独立核对 PC 信任根、SAS 与本设备指纹'}).check();await b.getByRole('button',{name:'确认核对并生成配对证明'}).click();await expect(b.getByLabel('交给 PC 的配对证明')).not.toHaveValue('');
  await pc.getByLabel('B 配对证明',{exact:true}).fill(await b.getByLabel('交给 PC 的配对证明').inputValue());await pc.getByRole('button',{name:'确认 B 配对证明'}).click();await expect(pc.getByLabel('PC 配对公开输出')).toHaveValue(/"stage":"COMPLETE"/,{timeout:15000});
  expect(statuses).toEqual([{action:'start',status:200,code:null},{action:'confirm',status:200,code:null}]);
 },[
  ()=>{mkdirSync(root,{recursive:true});writeFileSync(resolve(root,'owner-http-summary.json'),JSON.stringify({scope:'Actual browser B native pairing; PC Python strict TLS; browser Relay Fetch not exercised',statuses}));},
  async()=>{if(context)await context.close();},
  ()=>stopPc(pcServer),
 ]);
});
