import type {Reporter,TestCase,TestResult,FullResult,TestError} from '@playwright/test/reporter';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
const phases=new Set('START BROWSER_LAUNCH BROWSER_VERSION UNTRUSTED_CA HOSTNAME_NEGATIVE FRESH_UI OWNER_START B_NATIVE_PROOF OWNER_CONFIRM INJECTED_HELLO_NETWORK_LOSS B_VERIFY_AND_FETCH RECEIPT_RESUME BAD_PROOF UNAUTHORIZED_ORIGIN SCREENSHOTS COMPLETE'.split(' '));
const diagnostics=new Set('ERR_CERT_AUTHORITY_INVALID ERR_CERT_COMMON_NAME_INVALID ERR_CONNECTION_REFUSED OTHER_NETWORK_FAILURE NO_CERTIFICATE_FAILURE ASSERTION_OR_OPERATION_FAILED'.split(' '));
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
export function summarizeError(error:{name?:string;message?:string;stack?:string}){
 const name=error.name??error.message?.match(/^(Error|TypeError|ReferenceError|SyntaxError|TimeoutError):/)?.[1];
 // Hash the complete diagnostic input; never emit any fragment of it.
 return {errorType:name&&errorTypes.has(name)?name:'UNKNOWN',sha256:createHash('sha256').update(JSON.stringify({name:error.name??null,message:error.message??null,stack:error.stack??null})).digest('hex'),diagnostics:safeDiagnostics(error.message??''),processExits:processExits(error.message??'')};
}
function reviewedSummary(raw:any){return {errorType:errorTypes.has(raw?.errorType)?raw.errorType:'UNKNOWN',sha256:typeof raw?.sha256==='string'&&/^[a-f0-9]{64}$/.test(raw.sha256)?raw.sha256:null,diagnostics:Array.isArray(raw?.diagnostics)?raw.diagnostics.filter((v:unknown)=>typeof v==='string'&&Object.hasOwn(diagnosticPatterns,v)):[]};}
/** Fixed-field summary only; errors, DOM, network bodies and stdout stay private. */
export default class NetworkReporter implements Reporter{
 private rows:{title:string;status:string;retry:number}[]=[];
 private errorDiagnostics=new Set<string>();
 private errors:ReturnType<typeof summarizeError>[]=[];
 onError(error:TestError){const summary=summarizeError(error);this.errors.push(summary);for(const code of summary.diagnostics)this.errorDiagnostics.add(code);}
 onTestEnd(test:TestCase,result:TestResult){for(const error of result.errors)this.onError(error);this.rows.push({title:'B2 actual browser pairing, strict TLS and narrow CORS',status:result.status,retry:result.retry});}
 onEnd(result:FullResult){
  const dir=process.env.RH_B2_RESULTS!,path=resolve(dir,'phase.json');const p=existsSync(path)?JSON.parse(readFileSync(path,'utf8')):{};
  const cleanupPath=resolve(dir,'cleanup.json'),cleanup=existsSync(cleanupPath)?JSON.parse(readFileSync(cleanupPath,'utf8')):{};
   const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0?Number(v):0;
  writeFileSync(resolve(dir,'summary.json'),JSON.stringify({scope:'SYNTHETIC actual Linux Chromium TLS and browser Fetch',status:result.status,tlsCase:process.env.RH_B2_TLS_CASE==='trusted'?'trusted':'untrusted',buildHash:process.env.RH_B2_BUILD_HASH,sourceCommit:/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA??'')?process.env.GITHUB_SHA:null,node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()},nss:'dedicated-user-modern-nssdb',retries:0,errors:this.errors,cleanup:{state:['START','PASS','FAILED'].includes(cleanup.state)?cleanup.state:'NOT_STARTED',error:cleanup.error?reviewedSummary(cleanup.error):null},errorDiagnostics:[...this.errorDiagnostics].sort(),tests:this.rows,phase:phases.has(p.phase)?p.phase:'START',diagnostic:diagnostics.has(p.diagnostic)?p.diagnostic:null,preflights:count(p.preflights),signedPosts:count(p.signedPosts),chromium:typeof p.chromium==='string'&&/^\d+(\.\d+){1,3}$/.test(p.chromium)?p.chromium:null,hostnameMapping:'MAP localhost 127.0.0.1; original https localhost URL retained'},null,2),{mode:0o600});
 }
}
