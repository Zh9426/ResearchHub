import {withNativeUiCleanup,privateFailure,NATIVE_UI_FAILURE} from '../scripts/native-ui-cleanup.ts';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {withCleanup} from './cleanup.ts';
for(const failed of ['summary','close'])test(`${failed} failure still attempts every owned cleanup and retains primary`,async()=>{
 const calls:string[]=[],primary=Error('primary'),failure=Error(failed);
 await assert.rejects(withCleanup(async()=>{throw primary;},['summary','close','stopPc'].map(name=>async()=>{calls.push(name);if(name===failed)throw failure;})),error=>{
  assert.ok(error instanceof AggregateError);assert.deepEqual(error.errors,[primary,failure]);return true;
 });
 assert.deepEqual(calls,['summary','close','stopPc']);
});
test('all cleanup failures are retained even when work succeeds',async()=>{
 const failures=[Error('summary'),Error('close'),Error('stopPc')];
 await assert.rejects(withCleanup(async()=>{},failures.map(error=>async()=>{throw error;})),error=>{assert.ok(error instanceof AggregateError);assert.deepEqual(error.errors,failures);return true;});
});
test('clean success resolves',async()=>{await withCleanup(async()=>{},[()=>{},async()=>{}]);});


for(const failures of ['both','primary','cleanup','none'])test(`native UI ${failures} preserves private causes and fixed public diagnostic`,async()=>{
 const primary=Error('PRIVATE_PRIMARY'),cleanup=Error('PRIVATE_CLEANUP');let cleaned=false;
 const promise=withNativeUiCleanup(async()=>{if(['both','primary'].includes(failures))throw primary;},async()=>{cleaned=true;if(['both','cleanup'].includes(failures))throw cleanup;});
 if(failures==='none')await promise;
 else await assert.rejects(promise,error=>{
  assert.ok(error instanceof AggregateError);
  const expected=failures==='both'?[primary,cleanup]:failures==='primary'?[primary]:[cleanup];assert.deepEqual(error.errors,expected);
  const saved=privateFailure(error);assert.deepEqual(saved.errors!.map((row:any)=>row.message),expected.map(e=>e.message));
  assert.ok(saved.errors!.every((row:any)=>typeof row.stack==='string'&&row.stack.includes(row.message)));
  assert.equal(NATIVE_UI_FAILURE,'NATIVE_UI_LABEL_ASSERTION_FAILED');assert.equal(NATIVE_UI_FAILURE.includes('PRIVATE'),false);return true;
 });
 assert.equal(cleaned,true);
});


test('private aggregate serialization retains nested causes and bounds cycles',()=>{
 const cause=Error('PRIVATE_CAUSE'),nested=new AggregateError([Error('PRIVATE_NESTED')],'PRIVATE_GROUP',{cause});
 const saved=privateFailure(new AggregateError([nested],'outer'));
 assert.equal(saved.errors![0].errors![0].message,'PRIVATE_NESTED');assert.equal(saved.errors![0].cause!.message,'PRIVATE_CAUSE');
 const cyclic=Error('PRIVATE_CYCLE');(cyclic as any).cause=cyclic;assert.equal(privateFailure(cyclic).cause!.message,'DETAIL_LIMIT');
});
