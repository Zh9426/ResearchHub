import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {emptyRecordState,applyRecord,commonBase,stageRecordPage,type RecordContext} from '../src/record-kernel-core.ts';
const fixture=JSON.parse(readFileSync(new URL('../../../fixtures/sync/v2/record_kernel_cases.json',import.meta.url),'utf8'));
for(const scenario of fixture.cases)test(`record transcript ${scenario.name}`,async()=>{
 let state=emptyRecordState(fixture.principal.project_id,fixture.module_hash);const principal=structuredClone(scenario.principal??fixture.principal);
 for(const step of scenario.steps){
  if(step.revoke)principal.active=false;if(step.context_project)principal.project_id=step.context_project;if(step.target_project)principal.project_id=step.target_project;
  const before=structuredClone(state);let result;
  try{const applied=await applyRecord(state,step.transaction,{principal,module:step.module??fixture.module,module_hash:step.module_hash??fixture.module_hash,project_id:step.target_project??fixture.principal.project_id,mode:step.mode??'online'});state=applied.snapshot;result=applied.receipt.state;}
  catch(error){result=(error as {code?:string}).code;assert.deepEqual(state,before);}
  assert.equal(result,step.expected);
 }
});
test('common BASE is unique maximal ancestor, including multiple maxima',()=>{for(const item of fixture.common_base)assert.equal(commonBase(item.graph,item.heads),item.expected);});
const context=():RecordContext=>({principal:structuredClone(fixture.principal),module:fixture.module,module_hash:fixture.module_hash,project_id:fixture.principal.project_id,mode:'online'});
test('whole page failure leaves original pure snapshot untouched (not an IDB test)',async()=>{
 const state=emptyRecordState(fixture.principal.project_id,fixture.module_hash),before=structuredClone(state);
 const valid=fixture.cases.find((c:any)=>c.name==='independent').steps[0].transaction;
 const invalid=fixture.cases.find((c:any)=>c.name==='missing-parent').steps[0].transaction;
 await assert.rejects(stageRecordPage(state,[valid,invalid],context()),{code:'DEPENDENCY_REQUIRED'});assert.deepEqual(state,before);
});
test('async hashing cannot observe later caller snapshot/context mutations',async()=>{
 const state=emptyRecordState(fixture.principal.project_id,fixture.module_hash),trusted=context(),tx=structuredClone(fixture.cases[0].steps[0].transaction);
 const pending=applyRecord(state,tx,trusted);state.sequence=900;trusted.principal.active=false;tx.changes[0].payload.title='later mutation';
 const result=await pending;assert.equal(result.receipt.sequence,1);assert.equal(result.receipt.state,'ACCEPTED');assert.notEqual(Object.values(result.snapshot.revisions)[0].document.title,'later mutation');
});
