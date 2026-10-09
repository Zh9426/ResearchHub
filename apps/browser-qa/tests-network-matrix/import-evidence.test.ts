import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as evidence from './import-evidence.ts';

for(const failWrite of [false,true])test(`import preserves primary, all cleanup failures and evidence write failure=${failWrite}`,async()=>{
 const run=(evidence as any).withImportCleanup;assert.equal(typeof run,'function');
 const primary=Error('PRIVATE_PRIMARY'),first=Error('PRIVATE_CLOSE'),second=Error('PRIVATE_EXIT'),write=Error('PRIVATE_WRITE');let saved:any;const calls:string[]=[];
 await assert.rejects(run(async()=>{throw primary;},[async()=>{calls.push('close');throw first;},async()=>{calls.push('exit');throw second;}],(summary:any)=>{calls.push('write');saved=summary;if(failWrite)throw write;}),(error:any)=>{
  assert.ok(error instanceof AggregateError);assert.deepEqual(error.errors,failWrite?[primary,first,second,write]:[primary,first,second]);return true;
 });
 assert.deepEqual(calls,['close','exit','write']);assert.equal(saved.state,'FAILED');assert.match(saved.primaryError.sha256,/^[a-f0-9]{64}$/);assert.equal(saved.errors.length,2);assert.equal(JSON.stringify(saved).includes('PRIVATE'),false);
});

test('import cleanup failure with successful work still fails',async()=>{
 const run=(evidence as any).withImportCleanup;assert.equal(typeof run,'function');const failure=Error('PRIVATE_FAILURE');let saved:any;
 await assert.rejects(run(async()=>{},[async()=>{throw failure;}],(s:any)=>{saved=s;}),(e:any)=>e instanceof AggregateError&&e.errors[0]===failure);
 assert.equal(saved.primaryError,null);assert.equal(saved.state,'FAILED');assert.equal(saved.errors.length,1);
});

test('import Fetch counter admits only actual message URL methods and accepted response statuses',()=>{
 const create=(evidence as any).createImportFetchCounter;assert.equal(typeof create,'function');const counter=create();
 counter.request('secret-id','https://private.invalid/v1/messages','POST');counter.response('secret-id',200);
 counter.request('bad','https://127.0.0.1:38001/v1/messages?secret=x','POST');counter.response('bad',200);
 counter.request('denied','https://127.0.0.1:38001/v1/messages','POST');counter.response('denied',403);
 counter.request('options','https://127.0.0.1:38001/v1/messages','OPTIONS');counter.response('options',204);
 counter.request('post','https://127.0.0.1:38001/v1/messages','POST');counter.response('post',200);counter.response('post',200);
 assert.deepEqual(counter.counts(),{preflights:1,signedPosts:1});
});
