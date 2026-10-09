import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as reporter from './network-evidence-reporter.ts';
test('diagnostics export only six fixed enums and never private error fragments',()=>{
 assert.equal(typeof reporter.safeDiagnostics,'function');
 const secret='PRIVATE_SECRET_SENTINEL';
 assert.deepEqual(reporter.safeDiagnostics(secret+' arbitrary unknown failure'),[]);
 const output=reporter.safeDiagnostics(secret+" EACCES EPERM Executable doesn't exist MODULE_NOT_FOUND No usable sandbox error while loading shared libraries");
 assert.deepEqual(output,['ACCESS_DENIED','OPERATION_NOT_PERMITTED','MISSING_BROWSER','MISSING_MODULE','SANDBOX_UNAVAILABLE','MISSING_SHARED_LIBRARY']);
 assert.equal(JSON.stringify(output).includes(secret),false);
 assert.deepEqual(reporter.safeDiagnostics(secret+' Permission denied Permission denied'),['ACCESS_DENIED']);
});

test('error summaries retain category and full error hash without private text',()=>{
 assert.equal(typeof reporter.summarizeError,'function');
 const raw={message:'PRIVATE_SECRET_SENTINEL launchPersistentContext: Timeout 30000ms exceeded.',stack:'PRIVATE_STACK',name:'TimeoutError'};
 const summary=reporter.summarizeError(raw);
 assert.equal(summary.errorType,'TimeoutError');assert.match(summary.sha256,/^[a-f0-9]{64}$/);
 assert.equal(JSON.stringify(summary).includes('PRIVATE'),false);
 assert.deepEqual(summary.diagnostics,['BROWSER_LAUNCH_TIMEOUT']);
 assert.notEqual(reporter.summarizeError({...raw,stack:'different'}).sha256,summary.sha256);
 assert.equal(reporter.summarizeError({name:'PRIVATE_TYPE',message:'arbitrary private error'}).errorType,'UNKNOWN');
 assert.deepEqual(reporter.summarizeError({message:'arbitrary private error'}).diagnostics,[]);
});

test('launch diagnostics expose bounded exit status and fixed codes, never stderr argv paths or PID',()=>{
 const message='Target page, context or browser has been closed\n<launching> /PRIVATE/PATH --token=PRIVATE_SECRET\n<launched> pid=987654\n[pid=987654][err] chrome_crashpad_handler: --database is required\n[pid=987654] <process did exit: exitCode=null, signal=SIGTRAP>\n[pid=987654] <process did exit: exitCode=null, signal=SIGTRAP>';
 const summary=reporter.summarizeError({message});
 assert.deepEqual(summary.processExits,[{exitCode:null,signal:'SIGTRAP'}]);
 assert.equal(summary.diagnostics.includes('CRASHPAD_DATABASE_REQUIRED'),true);
 assert.equal(JSON.stringify(summary).includes('PRIVATE'),false);assert.equal(JSON.stringify(summary).includes('987654'),false);
 assert.deepEqual(reporter.summarizeError({message:'<process did exit: exitCode=127, signal=null>'}).processExits,[{exitCode:127,signal:null}]);
 assert.deepEqual(reporter.summarizeError({message:'<process did exit: exitCode=null, signal=SECRET_SIGNAL>'}).processExits,[{exitCode:null,signal:'OTHER'}]);
 assert.deepEqual(reporter.summarizeError({message:'private unrecognized stderr'}).processExits,[]);
 assert.deepEqual(reporter.summarizeError({message:'<process did exit: exitCode=999999, signal=null>'}).processExits,[]);
});
