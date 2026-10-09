import type {Reporter,TestCase,TestResult,FullResult,TestError} from '@playwright/test/reporter';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
const phases=new Set('START BROWSER_LAUNCH BROWSER_VERSION UNTRUSTED_CA HOSTNAME_NEGATIVE FRESH_UI OWNER_START B_NATIVE_PROOF OWNER_CONFIRM INJECTED_HELLO_NETWORK_LOSS B_VERIFY_AND_FETCH RECEIPT_RESUME BAD_PROOF UNAUTHORIZED_ORIGIN SCREENSHOTS COMPLETE C_PC_BASELINE_UI C_B_NATIVE_EDIT_UI C_PC_READ_AND_EDIT_UI C_CLEAN_EDITOR_REFRESH C_PC_DIRTY_BASELINE_CAS C_DIRTY_EDITOR_PRESERVED C_DURABLE_NATIVE_PEER_RECEIPTS C_B_READ_BASELINE_RUN C_B_SAVE_RUN C_B_STAR_RUN C_B_SELECT_NOTE C_B_SAVE_NOTE_FIRST C_B_SAVE_NOTE_SECOND C_B_UNCONFIRMED_BEFORE_SEND C_B_SEND_PENDING C_B_RELAY_ONLY_ASSERT C_PC_APPLY_B_PENDING C_B_COLLECT_PEER_RECEIPTS C_B_PEER_ASSERT C_B_CONFIRMATION_COUNT'.split(' '));
for(const phase of 'CONFLICT_BASE CONFLICT_SAME_BASE_EDITS CONFLICT_OFFLINE_PROPOSAL CONFLICT_STALE_COMPARE_REJECT CONFLICT_CANDIDATE_CONVERGENCE CONFLICT_COMPLETE'.split(' '))phases.add(phase);
export function safePhase(value:unknown){return typeof value==='string'&&phases.has(value)?value:'START';}
const manualCodes=new Set('RELAY_REJECTED RESPONSE_MISSING RESPONSE_TOO_LARGE NONCANONICAL_RESPONSE MAPPING_NOT_CONVERTED MAPPING_CAS_MISMATCH BINDING_CHANGED ENVELOPE_NOT_READY SEALED_MISSING IDENTITY_COLLISION BUSINESS_ABORTED VAULT_IDENTITY_MISMATCH VAULT_MISSING_OR_INCOMPLETE VAULT_INITIALIZATION_INCOMPLETE VAULT_AUTHORIZATION_MISMATCH AUTHORIZATION_CHANGED AUTHORIZATION_NOT_READY MANUAL_CLAIM_LOST MANUAL_SYNC_BUSY OPERATION_BASE_REQUIRED OPERATION_DEPENDENCY_CYCLE EXACT_PEER_TARGET_REQUIRED HISTORICAL_EPOCH_BLOCKED PEER_RECEIPT_CAS PEER_RECEIPT_CHANGED PEER_RECEIPT_RELAY_MISMATCH RECEIPT_CAS RELAY_RECEIPT_CHANGED RELAY_RECEIPT_MISMATCH INVALID_SIGNATURE INVALID_ENVELOPE DEPENDENCY_REQUIRED SYNC_NETWORK_UNCONFIRMED SYNC_BLOCKED MANUAL_FAILURE_UNCLASSIFIED'.split(' '));
export function safeManualDiagnostic(value:unknown){const match=typeof value==='string'?/^Error: ([A-Z_]+)$/.exec(value):null;return match&&manualCodes.has(match[1])?match[1]:'MANUAL_FAILURE_UNCLASSIFIED';}
export function safeBaselineDiagnostic(value:unknown){
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const row=value as Record<string,unknown>;
 if(Object.keys(row).sort().join(',')!=='dom,kernel,local')return null;
 const allowed={dom:['missing','ambiguous','hidden','expected','other','read_failed'],local:['missing','expected','other','read_failed'],kernel:['missing','conflicted','expected','other','read_failed']};
 for(const key of ['dom','local','kernel'] as const)if(typeof row[key]!=='string'||!allowed[key].includes(row[key] as string))return null;
 return {dom:row.dom,local:row.local,kernel:row.kernel};
}
const diagnostics=new Set('ERR_CERT_AUTHORITY_INVALID ERR_CERT_COMMON_NAME_INVALID ERR_CONNECTION_REFUSED OTHER_NETWORK_FAILURE NO_CERTIFICATE_FAILURE ASSERTION_OR_OPERATION_FAILED'.split(' '));
for(const code of manualCodes)diagnostics.add(code);
const errorTypes=new Set(['Error','TypeError','ReferenceError','SyntaxError','TimeoutError']);
const diagnosticPatterns:Record<string,string[]>={ACCESS_DENIED:['EACCES','Permission denied'],OPERATION_NOT_PERMITTED:['EPERM','Operation not permitted'],MISSING_BROWSER:["Executable doesn't exist"],MISSING_MODULE:['MODULE_NOT_FOUND'],SANDBOX_UNAVAILABLE:['No usable sandbox'],MISSING_SHARED_LIBRARY:['error while loading shared libraries'],BROWSER_DEPENDENCIES_MISSING:['Host system is missing dependencies'],BROWSER_CLOSED:['Target page, context or browser has been closed'],BROWSER_LAUNCH_TIMEOUT:['launchPersistentContext: Timeout']};
// Literal messages verified in Chromium Crashpad handler_main.cc, sandbox.c,
// setuid_sandbox_host.cc and process_singleton_posix.cc; classifications only.
Object.assign(diagnosticPatterns,{CRASHPAD_DATABASE_REQUIRED:['--database is required'],SANDBOX_NAMESPACE_FAILED:['Failed to move to new namespace:'],SANDBOX_HELPER_MISCONFIGURED:['The SUID sandbox helper binary was found, but is not'],PROFILE_SOCKET_DIRECTORY_FAILED:['Failed to create socket directory.'],PROFILE_SOCKET_PATH_TOO_LONG:['Socket path too long:']});
const signals=new Set('SIGHUP SIGINT SIGQUIT SIGILL SIGTRAP SIGABRT SIGBUS SIGFPE SIGKILL SIGSEGV SIGPIPE SIGALRM SIGTERM SIGXCPU SIGXFSZ SIGSYS'.split(' '));
type ProcessExit={exitCode:number|null;signal:string|null};
function processExits(message:string):ProcessExit[]{
 // Exact Playwright 1.64 processLauncher log grammar; never retain PID/argv.
 const result:ProcessExit[]=[];
 for(const match of message.matchAll(/<process did exit: exitCode=(null|[0-9]{1,6}), signal=(null|[A-Z0-9_]{1,64})>/g)){
  const exitCode=match[1]==='null'?null:Number(match[1]);if(exitCode!==null&&exitCode>255)continue;
  const signal=match[2]==='null'?null:signals.has(match[2])?match[2]:'OTHER';
  if(!result.some(e=>e.exitCode===exitCode&&e.signal===signal))result.push({exitCode,signal});
  if(result.length===8)break;
 }
 return result;
}
export function safeDiagnostics(message:string):string[]{
 return Object.keys(diagnosticPatterns).filter(code=>diagnosticPatterns[code].some(needle=>message.includes(needle)));
}
function sourceLocations(stack:string){
 const result:{file:string;line:number;column:number}[]=[];
 // Only explicitly paired directories/basenames and bounded positions escape.
 for(const match of stack.matchAll(/[\/]tests-network(?:[\/](manual-roundtrip\.ts|network\.spec\.ts)|-matrix[\/](conflict-roundtrip\.ts|conflict\.spec\.ts)):([1-9][0-9]{0,4}):([1-9][0-9]{0,3})(?=[)\s]|$)/g)){
  const value={file:match[1]??match[2],line:Number(match[3]),column:Number(match[4])};
  if(!result.some(old=>old.file===value.file&&old.line===value.line&&old.column===value.column))result.push(value);
  if(result.length===8)break;
 }
 return result;
}
export function summarizeError(error:{name?:string;message?:string;stack?:string}){
 const name=error.name??error.message?.match(/^(Error|TypeError|ReferenceError|SyntaxError|TimeoutError):/)?.[1];
 // Hash the complete diagnostic input; never emit any fragment of it.
 return {errorType:name&&errorTypes.has(name)?name:'UNKNOWN',sha256:createHash('sha256').update(JSON.stringify({name:error.name??null,message:error.message??null,stack:error.stack??null})).digest('hex'),diagnostics:safeDiagnostics(error.message??''),processExits:processExits(error.message??''),locations:sourceLocations(error.stack??'')};
}
function reviewedSummary(raw:any){return {errorType:errorTypes.has(raw?.errorType)?raw.errorType:'UNKNOWN',sha256:typeof raw?.sha256==='string'&&/^[a-f0-9]{64}$/.test(raw.sha256)?raw.sha256:null,diagnostics:Array.isArray(raw?.diagnostics)?raw.diagnostics.filter((v:unknown)=>typeof v==='string'&&Object.hasOwn(diagnosticPatterns,v)):[]};}
export function safeTitle(value:unknown){return value==='C conflict actual browser pairing and candidate convergence'?'C conflict actual browser pairing and candidate convergence':'B2 actual browser pairing, strict TLS and narrow CORS';}
/** Fixed-field summary only; errors, DOM, network bodies and stdout stay private. */
export default class NetworkReporter implements Reporter{
 private rows:{title:string;status:string;retry:number}[]=[];
 private errorDiagnostics=new Set<string>();
 private errors:ReturnType<typeof summarizeError>[]=[];
 onError(error:TestError){const summary=summarizeError(error);this.errors.push(summary);for(const code of summary.diagnostics)this.errorDiagnostics.add(code);}
 onTestEnd(test:TestCase,result:TestResult){for(const error of result.errors)this.onError(error);this.rows.push({title:safeTitle(test.title),status:result.status,retry:result.retry});}
 onEnd(result:FullResult){
  const dir=process.env.RH_B2_RESULTS!,path=resolve(dir,'phase.json');const p=existsSync(path)?JSON.parse(readFileSync(path,'utf8')):{};
  const cleanupPath=resolve(dir,'cleanup.json'),cleanup=existsSync(cleanupPath)?JSON.parse(readFileSync(cleanupPath,'utf8')):{};
   const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0?Number(v):0;
  writeFileSync(resolve(dir,'summary.json'),JSON.stringify({scope:'SYNTHETIC actual Linux Chromium TLS and browser Fetch',status:result.status,tlsCase:process.env.RH_B2_TLS_CASE==='trusted'?'trusted':'untrusted',buildHash:process.env.RH_B2_BUILD_HASH,sourceCommit:/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA??'')?process.env.GITHUB_SHA:null,node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()},nss:'dedicated-user-modern-nssdb',retries:0,errors:this.errors,cleanup:{state:['START','PASS','FAILED'].includes(cleanup.state)?cleanup.state:'NOT_STARTED',error:cleanup.error?reviewedSummary(cleanup.error):null},errorDiagnostics:[...this.errorDiagnostics].sort(),tests:this.rows,phase:safePhase(p.phase),baselineDiagnostic:safeBaselineDiagnostic(p.baselineDiagnostic),diagnostic:diagnostics.has(p.diagnostic)?p.diagnostic:null,preflights:count(p.preflights),signedPosts:count(p.signedPosts),chromium:typeof p.chromium==='string'&&/^\d+(\.\d+){1,3}$/.test(p.chromium)?p.chromium:null,hostnameMapping:'MAP localhost 127.0.0.1; original https localhost URL retained'},null,2),{mode:0o600});
 }
}
