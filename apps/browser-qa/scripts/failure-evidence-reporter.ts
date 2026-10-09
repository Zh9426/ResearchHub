import type {Reporter, TestResult, TestCase, FullResult, TestError} from '@playwright/test/reporter';
import {readFileSync,writeFileSync,existsSync,appendFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {summarizeError,safeCleanup,safeManualDiagnostic} from './network-evidence-reporter.ts';
const phases=new Set('START BROWSER_LAUNCH PAIR OWNER_START B_NATIVE_PROOF OWNER_CONFIRM BOOTSTRAP_HISTORY LOCAL_UI LOCAL_RUN_CREATE LOCAL_RUN_UPDATE LOCAL_RUN_STAR LOCAL_RUN_STAR_NOTE LOCAL_NOTE_CREATE NORMAL_ALL_PID_REOPEN INDEPENDENT_OBJECT OWNER_REVOKE PC_LOGICAL_OFFLINE ACKLOSS ACKLOSS_ALL_PID_REOPEN SEND PEER_APPLY PRIVACY IDEMPOTENT_ECHO COMPLETE'.split(' '));
const operations=new Set('NONE PC_SAVE B_SAVE PC_SYNC B_SYNC PC_STOP PC_START ACKLOSS_ARM ACKLOSS_WAIT_COMMIT_AND_KILL RELAY_START VERIFY_DURABLE_COUNTS OWNER_REVOKE PRIVACY_AUDIT CASE_FINISH'.split(' '));
const checkNames='bootstrap_no_business_or_cursor offline_cold_start same_profile_reopened all_b_pids_exited_before_reopen owner_revoked_old_sync_rejected local_operations_preserved local_audit_preserved exact_request_body_repeated cached_envelope_unchanged remote_ids_match no_extra_echo_mutations'.split(' ');
export function safeFailureChecks(value:any){return Object.fromEntries(checkNames.map(key=>[key,value?.[key]===true]));}
export function safeFailureOperation(value:unknown){return typeof value==='string'&&operations.has(value)?value:'UNKNOWN';}
export function failureLocations(stack:string){return [...stack.matchAll(/[\\/]tests-network-matrix[\\/]failure\.spec\.ts:([1-9][0-9]{0,4}):([1-9][0-9]{0,3})(?=[)\s]|$)/g)].slice(0,8).map(m=>({file:'failure.spec.ts',line:Number(m[1]),column:Number(m[2])}));}
export function safeFailureSnapshots(value:unknown){if(!Array.isArray(value))return [];return value.slice(0,8).filter(v=>v&&['LOCAL_SAVED','ACK_UNKNOWN','PEER_CONFIRMED','ECHO_NO_CHANGE'].includes(v.stage)&&/^[a-f0-9]{64}$/.test(v.digest)&&['objects','operations','audit','mappings','transactions','pending'].every(k=>Number.isSafeInteger(v[k])&&v[k]>=0)).map(v=>({stage:v.stage,digest:v.digest,objects:v.objects,operations:v.operations,audit:v.audit,mappings:v.mappings,transactions:v.transactions,pending:v.pending}));}
const cases=new Set('reopen pc-offline independent-echo ack-loss revoked-write historical-bootstrap privacy'.split(' '));
export function safeFailurePhase(value:unknown){return typeof value==='string'&&phases.has(value)?value:'UNKNOWN';}
export function safeFailureCase(value:unknown){return typeof value==='string'&&cases.has(value)?value:'UNKNOWN';}
export default class FailureReporter implements Reporter {
 private errors:(ReturnType<typeof summarizeError>&{failureLocations:ReturnType<typeof failureLocations>})[]=[];
 private tests:{status:string;retry:number}[]=[];
 onError(e:TestError){
  appendFileSync(resolve(process.env.RH_B2_RESULTS!,'errors.private.jsonl'),JSON.stringify({message:e.message,stack:e.stack})+'\n',{mode:0o600});
  this.errors.push({...summarizeError(e),failureLocations:failureLocations(e.stack??'')});
 }
 onTestEnd(_:TestCase,result:TestResult){for(const e of result.errors)this.onError(e);this.tests.push({status:result.status,retry:result.retry});}
 onEnd(result:FullResult){
  const root=process.env.RH_B2_RESULTS!,read=(name:string)=>existsSync(resolve(root,name))?JSON.parse(readFileSync(resolve(root,name),'utf8')):{};
  const p=read('phase.json');
  writeFileSync(resolve(root,'summary.json'),JSON.stringify({scope:'SYNTHETIC isolated Linux native browser real failures',status:result.status,case:safeFailureCase(process.env.RH_FAILURE_CASE),phase:safeFailurePhase(p.phase),operation:safeFailureOperation(p.operation),diagnostic:p.diagnostic?safeManualDiagnostic('Error: '+p.diagnostic):null,checks:safeFailureChecks(p.checks),snapshots:safeFailureSnapshots(p.snapshots),chromium:typeof p.chromium==='string'&&/^\d+(\.\d+){1,3}$/.test(p.chromium)?p.chromium:null,node:process.version,sourceCommit:/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA??'')?process.env.GITHUB_SHA:null,buildHash:/^[a-f0-9]{64}$/.test(process.env.RH_B2_BUILD_HASH??'')?process.env.RH_B2_BUILD_HASH:null,cleanup:safeCleanup(read('cleanup.json')),tests:this.tests,errors:this.errors,retries:0,TLS_001:'OPEN',PRODUCTION_READY:false},null,2),{mode:0o600});
 }
}
