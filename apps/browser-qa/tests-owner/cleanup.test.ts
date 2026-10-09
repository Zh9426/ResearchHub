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
