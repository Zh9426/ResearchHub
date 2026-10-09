import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {emptyRecordState,applyRecord} from '../src/record-kernel-core.ts';
const f=JSON.parse(readFileSync(new URL('../../../fixtures/sync/v2/conflict_proposal_cases.json',import.meta.url),'utf8'));
const results:any[]=[];
for(const scenario of f.cases)test(scenario.name,async()=>{
 let state=emptyRecordState(f.principal.project_id,f.module_hash),principal=structuredClone(f.principal);
 for(const step of scenario.steps){if(step.revoke)principal.active=false;const before=structuredClone(state);let result;
  try{const applied=await applyRecord(state,step.transaction,{principal,module:f.module,module_hash:f.module_hash,project_id:f.principal.project_id,mode:step.mode??'online'});state=applied.snapshot;result=applied.receipt.state;}catch(e){result=(e as any).code;assert.deepEqual(state,before);}assert.equal(result,step.expected);
 }
 if(scenario.name.startsWith('third-')){assert.deepEqual(Object.values(state.heads)[0].map(h=>state.revisions[h].document.content).sort(),['reviewed','third']);results.push(state.heads);if(results.length===2)assert.deepEqual(results[0],results[1]);}
});
