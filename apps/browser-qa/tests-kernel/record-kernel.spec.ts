import {test,expect,chromium,type BrowserContext,type Browser} from '@playwright/test';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {withCleanup} from '../tests-owner/cleanup';
const root=process.env.RH_C1_RESULTS!;
const fixture=JSON.parse(readFileSync(resolve(root,'fixture.json'),'utf8'));
const oracle=JSON.parse(readFileSync(resolve(root,'oracle.json'),'utf8'));
const pgBases=JSON.parse(readFileSync(resolve(root,'common-base.json'),'utf8'));
function normalize(value:any):any{
 if(Array.isArray(value))return value.map(normalize);
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,['audits','conflicts'].includes(k)?value[k].map(normalize).sort((a:any,b:any)=>JSON.stringify(a).localeCompare(JSON.stringify(b))):normalize(value[k])]));
 return value;
}
test('actual Chromium record kernel matches independent PostgreSQL snapshots',async()=>{
 let context:BrowserContext|undefined,connection:Browser|undefined,passed=0,version:string|undefined,cleanup='NOT_STARTED';
 await withCleanup(async()=>{
  const endpoint=process.env.RH_C1_CDP;if(!endpoint||!/^ws:\/\/127\.0\.0\.1:\d+\/devtools\/browser\//.test(endpoint))throw Error('OWNED_CDP_REQUIRED');
  connection=await chromium.connectOverCDP(endpoint);context=connection.contexts()[0];version=connection.version();
  const page=await context.newPage();await page.goto('http://127.0.0.1:3314');
  for(let index=0;index<fixture.cases.length;index++){
   const scenario=fixture.cases[index];
   const result=await page.evaluate(async({scenario,fixture})=>{
    const kernel=(window as any).recordKernel;let state=kernel.emptyRecordState(fixture.principal.project_id,fixture.module_hash);const principal=structuredClone(scenario.principal??fixture.principal),steps=[];
    for(const step of scenario.steps){
     if(step.revoke)principal.active=false;if(step.context_project)principal.project_id=step.context_project;if(step.target_project)principal.project_id=step.target_project;
     const before=JSON.stringify(state);let output;
     try{const applied=await kernel.applyRecord(state,step.transaction,{principal,module:step.module??fixture.module,module_hash:step.module_hash??fixture.module_hash,project_id:step.target_project??fixture.principal.project_id,mode:step.mode??'online'});state=applied.snapshot;output={result:applied.receipt.state,receipt:applied.receipt};}
     catch(error){if(JSON.stringify(state)!==before)throw Error('FAILED_STEP_MUTATED_STATE');output={result:(error as any).code};}
     steps.push({...output,snapshot:structuredClone(state)});
    }
    return {name:scenario.name,steps};
   },{scenario,fixture});
   expect(normalize(result),scenario.name).toEqual(normalize(oracle[index]));passed++;
  }
  const graphResults=await page.evaluate(items=>items.map((i:any)=>(window as any).recordKernel.commonBase(i.graph,i.heads)),fixture.common_base);
  expect(graphResults).toEqual(fixture.common_base.map((i:any)=>i.expected));
  expect(graphResults).toEqual(pgBases);
  const atomic=await page.evaluate(async fixture=>{
   const k=(window as any).recordKernel,state=k.emptyRecordState(fixture.principal.project_id,fixture.module_hash),before=JSON.stringify(state),context={principal:fixture.principal,module:fixture.module,module_hash:fixture.module_hash,project_id:fixture.principal.project_id,mode:'online'};
   const first=fixture.cases.find((c:any)=>c.name==='independent').steps[0].transaction,bad=fixture.cases.find((c:any)=>c.name==='missing-parent').steps[0].transaction;
   try{await k.stageRecordPage(state,[first,bad],context);return false;}catch(error){return (error as any).code==='DEPENDENCY_REQUIRED'&&JSON.stringify(state)===before;}
  },fixture);
  expect(atomic).toBe(true);
 },[
  async()=>{
   if(!connection)return;cleanup='FAILED';await connection.close();cleanup='DISCONNECTED_OWNED_RUNNER_CLOSES';
  },
  ()=>{writeFileSync(resolve(root,'browser-summary.json'),JSON.stringify({scope:'SYNTHETIC real Chromium versus PostgreSQL; pure staged page only; no IDB or transport claim',casesPassed:passed,chromium:version,retries:0,cleanup}));},
 ]);
});
