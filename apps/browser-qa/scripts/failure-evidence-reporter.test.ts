import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import Reporter,{safeFailureCase,safeFailurePhase,safeFailureOperation,safeFailureChecks,safeFailureSnapshots,failureLocations} from './failure-evidence-reporter.ts';
import {withCleanup} from '../tests-owner/cleanup.ts';
import {rethrowPrivateFailure} from '../tests-network-matrix/failure-private-evidence.ts';

test('pre-serialization evidence retains work and cleanup failures and rethrows identical aggregate',async()=>{
 const runtime=resolve('../../storage/runtime/browser-sync-qa/failure-reporter-tests');mkdirSync(runtime,{recursive:true});
 const dir=mkdtempSync(resolve(runtime,'aggregate-')),path=resolve(dir,'failure-details.private.json');
 const primary=Error('Expected: PRIVATE_EXPECTED\nReceived: PRIVATE_ACTUAL'),cleanup=Error('PRIVATE_CLOSE_FAILURE');
 primary.stack+='\n at /private/tests-network-matrix/failure.spec.ts:123:7';
 let original:unknown;
 await assert.rejects((async()=>{
  try{await withCleanup(async()=>{throw primary;},[()=>{throw cleanup;}]);}
  catch(error){original=error;rethrowPrivateFailure(error,path);}
 })(),error=>{assert.equal(error,original);return true;});
 const saved=JSON.parse(readFileSync(path,'utf8'));
 assert.deepEqual(saved.errors.map((row:any)=>row.message),[primary.message,cleanup.message]);
 assert.equal(saved.errors[0].stack,primary.stack);assert.equal(saved.errors[1].stack,cleanup.stack);
 // Model Playwright's message/stack/cause-only boundary: the private file must predate it.
 const serialized={message:(original as Error).message,stack:(original as Error).stack};
 assert(!JSON.stringify(serialized).includes('PRIVATE_EXPECTED'));
 assert(saved.errors[0].stack.includes('failure.spec.ts:123:7'));
});

test('private evidence write failure retains original aggregate and filesystem failure',()=>{
 const original=new AggregateError([Error('PRIVATE_WORK'),Error('PRIVATE_CLEANUP')],'outer');
 const runtime=resolve('../../storage/runtime/browser-sync-qa/failure-reporter-tests');mkdirSync(runtime,{recursive:true});
 const directory=mkdtempSync(resolve(runtime,'write-failure-'));
 assert.throws(()=>rethrowPrivateFailure(original,directory),error=>{
  assert(error instanceof AggregateError);assert.equal(error.errors[0],original);
  assert(error.errors[1] instanceof Error);assert.equal(error.errors.length,2);return true;
 });
});

test('only reviewed names and strict scalar evidence escape',()=>{
 for(const value of ['PRIVATE_PROOF',{},null,1])for(const fn of [safeFailureCase,safeFailurePhase,safeFailureOperation])assert.equal(fn(value),'UNKNOWN');
 assert.equal(safeFailureCase('ack-loss'),'ack-loss');assert.equal(safeFailurePhase('LOCAL_RUN_STAR_NOTE'),'LOCAL_RUN_STAR_NOTE');assert.equal(safeFailureOperation('VERIFY_DURABLE_COUNTS'),'VERIFY_DURABLE_COUNTS');
 const checked=safeFailureChecks({cached_envelope_unchanged:true,local_operations_preserved:'PRIVATE_PROOF',PRIVATE_PROOF:true});
 assert.equal(checked.cached_envelope_unchanged,true);assert.equal(checked.local_operations_preserved,false);assert(!JSON.stringify(checked).includes('PRIVATE_PROOF'));
 const good={stage:'ACK_UNKNOWN',digest:'a'.repeat(64),objects:2,operations:5,audit:5,mappings:1,transactions:0,pending:2};
 assert.deepEqual(safeFailureSnapshots([{...good,PRIVATE_PROOF:'secret'}, {...good,digest:'PRIVATE_PROOF'}, {...good,operations:-1}, {...good,operations:true}]),[good]);
});
test('error sources have exact filename and bounded positions',()=>{
 assert.deepEqual(failureLocations('at /secret/tests-network-matrix/failure.spec.ts:122:9\n at C:\\secret\\tests-network-matrix\\failure.spec.ts:43:1)'),[{file:'failure.spec.ts',line:122,column:9},{file:'failure.spec.ts',line:43,column:1}]);
 assert.deepEqual(failureLocations('/private/other.spec.ts:12:1 /x/tests-network-matrix/failure.spec.ts:123456:1 /x/tests-network-matrix/failure.spec.ts:12:0'),[]);
});
test('public failure report excludes private errors and extra fields',()=>{
 const runtime=resolve('../../storage/runtime/browser-sync-qa/failure-reporter-tests');mkdirSync(runtime,{recursive:true});
 const dir=mkdtempSync(resolve(runtime,'attempt-')),before={results:process.env.RH_B2_RESULTS,scenario:process.env.RH_FAILURE_CASE};
 try{
  process.env.RH_B2_RESULTS=dir;process.env.RH_FAILURE_CASE='ack-loss';
  writeFileSync(resolve(dir,'phase.json'),JSON.stringify({phase:'ACKLOSS',operation:'B_SYNC',diagnostic:'RELAY_REJECTED',chromium:'156.0.8078.4',proof:'PRIVATE_PROOF',checks:{exact_request_body_repeated:true}}));
  const reporter=new Reporter();reporter.onError({message:'PRIVATE_PROOF and PRIVATE_KEY',stack:'at /private/tests-network-matrix/failure.spec.ts:132:7'});reporter.onEnd({status:'failed'} as any);
  const text=readFileSync(resolve(dir,'summary.json'),'utf8');assert(!text.includes('PRIVATE_'));assert(!text.includes('/private/'));
  const report=JSON.parse(text);assert.equal(report.phase,'ACKLOSS');assert.equal(report.operation,'B_SYNC');assert.equal(report.diagnostic,'RELAY_REJECTED');assert.equal(report.retries,0);assert.deepEqual(report.errors[0].failureLocations,[{file:'failure.spec.ts',line:132,column:7}]);
 }finally{for(const [key,value] of [['RH_B2_RESULTS',before.results],['RH_FAILURE_CASE',before.scenario]])if(value===undefined)delete process.env[key!];else process.env[key!]=value;}
});
