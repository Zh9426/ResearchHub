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

test('manual sync phases retain only reviewed labels, never arbitrary private content',()=>{
 const safePhase=(reporter as any).safePhase;
 assert.equal(typeof safePhase,'function');
 for(const phase of ['C_PC_BASELINE_UI','C_B_NATIVE_EDIT_UI','C_PC_READ_AND_EDIT_UI','C_CLEAN_EDITOR_REFRESH','C_PC_DIRTY_BASELINE_CAS','C_DIRTY_EDITOR_PRESERVED','C_DURABLE_NATIVE_PEER_RECEIPTS'])assert.equal(safePhase(phase),phase);
 assert.equal(safePhase('PRIVATE_SECRET_SENTINEL'),'START');assert.equal(safePhase('BAD_PROOF'),'BAD_PROOF');
});


test('manual diagnostic locations and codes are fixed and bounded',()=>{
 const summarize=reporter.summarizeError({message:'PRIVATE_SECRET',stack:'Error: PRIVATE_SECRET\n at manualRoundTrip (/PRIVATE/ROOT/tests-network/manual-roundtrip.ts:17:9)\n at /PRIVATE/ROOT/tests-network/network.spec.ts:57:3\n at /PRIVATE/other.ts:99:1'});
 assert.deepEqual((summarize as any).locations,[{file:'manual-roundtrip.ts',line:17,column:9},{file:'network.spec.ts',line:57,column:3}]);
 assert.equal(JSON.stringify(summarize).includes('PRIVATE'),false);
 assert.deepEqual((reporter.summarizeError({stack:'at /x/manual-roundtrip.ts:99999999:9'}) as any).locations,[]);
 const safe=(reporter as any).safeManualDiagnostic;assert.equal(typeof safe,'function');
 assert.equal(safe('Error: MAPPING_NOT_CONVERTED'),'MAPPING_NOT_CONVERTED');
 for(const code of ['RELAY_REJECTED','RESPONSE_MISSING','RESPONSE_TOO_LARGE','NONCANONICAL_RESPONSE']){assert.equal(safe('Error: '+code),code);assert.equal(safe('Error: '+code+' PRIVATE_SECRET'),'MANUAL_FAILURE_UNCLASSIFIED');assert.equal(safe('prefix '+code),'MANUAL_FAILURE_UNCLASSIFIED');}
 for(const raw of ['Error: PRIVATE_SECRET','Error: MAPPING_NOT_CONVERTED PRIVATE_SECRET','prefix MAPPING_NOT_CONVERTED','TypeError: Failed to fetch PRIVATE_SECRET'])assert.equal(safe(raw),'MANUAL_FAILURE_UNCLASSIFIED');
 for(const phase of ['C_B_READ_BASELINE_RUN','C_B_SAVE_RUN','C_B_STAR_RUN','C_B_SELECT_NOTE','C_B_SAVE_NOTE_FIRST','C_B_SAVE_NOTE_SECOND','C_B_UNCONFIRMED_BEFORE_SEND','C_B_SEND_PENDING','C_B_RELAY_ONLY_ASSERT','C_PC_APPLY_B_PENDING','C_B_COLLECT_PEER_RECEIPTS','C_B_PEER_ASSERT','C_B_CONFIRMATION_COUNT'])assert.equal(reporter.safePhase(phase),phase);
});
