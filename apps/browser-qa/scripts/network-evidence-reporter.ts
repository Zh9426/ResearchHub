import type {Reporter,TestCase,TestResult,FullResult,TestError} from '@playwright/test/reporter';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import os from 'node:os';
const phases=new Set('START UNTRUSTED_CA HOSTNAME_NEGATIVE FRESH_UI OWNER_START B_NATIVE_PROOF OWNER_CONFIRM INJECTED_HELLO_NETWORK_LOSS B_VERIFY_AND_FETCH RECEIPT_RESUME BAD_PROOF UNAUTHORIZED_ORIGIN SCREENSHOTS COMPLETE'.split(' '));
const diagnostics=new Set('ERR_CERT_AUTHORITY_INVALID ERR_CERT_COMMON_NAME_INVALID ERR_CONNECTION_REFUSED OTHER_NETWORK_FAILURE NO_CERTIFICATE_FAILURE ASSERTION_OR_OPERATION_FAILED'.split(' '));
export function safeDiagnostics(message:string):string[]{
 const patterns:Record<string,string[]>={ACCESS_DENIED:['EACCES','Permission denied'],OPERATION_NOT_PERMITTED:['EPERM','Operation not permitted'],MISSING_BROWSER:["Executable doesn't exist"],MISSING_MODULE:['MODULE_NOT_FOUND'],SANDBOX_UNAVAILABLE:['No usable sandbox'],MISSING_SHARED_LIBRARY:['error while loading shared libraries']};
 return Object.keys(patterns).filter(code=>patterns[code].some(needle=>message.includes(needle)));
}
/** Fixed-field summary only; errors, DOM, network bodies and stdout stay private. */
export default class NetworkReporter implements Reporter{
 private rows:{title:string;status:string;retry:number}[]=[];
 private errorDiagnostics=new Set<string>();
 onError(error:TestError){for(const code of safeDiagnostics(error.message??''))this.errorDiagnostics.add(code);}
 onTestEnd(test:TestCase,result:TestResult){for(const error of result.errors)this.onError(error);this.rows.push({title:'B2 actual browser pairing, strict TLS and narrow CORS',status:result.status,retry:result.retry});}
 onEnd(result:FullResult){
  const dir=process.env.RH_B2_RESULTS!,path=resolve(dir,'phase.json');const p=existsSync(path)?JSON.parse(readFileSync(path,'utf8')):{};
   const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0?Number(v):0;
  writeFileSync(resolve(dir,'summary.json'),JSON.stringify({scope:'SYNTHETIC actual Linux Chromium TLS and browser Fetch',status:result.status,tlsCase:process.env.RH_B2_TLS_CASE==='trusted'?'trusted':'untrusted',buildHash:process.env.RH_B2_BUILD_HASH,sourceCommit:/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA??'')?process.env.GITHUB_SHA:null,node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()},nss:'dedicated-user-modern-nssdb',retries:0,errorDiagnostics:[...this.errorDiagnostics].sort(),tests:this.rows,phase:phases.has(p.phase)?p.phase:'START',diagnostic:diagnostics.has(p.diagnostic)?p.diagnostic:null,preflights:count(p.preflights),signedPosts:count(p.signedPosts),chromium:typeof p.chromium==='string'&&/^\d+(\.\d+){1,3}$/.test(p.chromium)?p.chromium:null,hostnameMapping:'MAP localhost 127.0.0.1; original https localhost URL retained'},null,2),{mode:0o600});
 }
}
