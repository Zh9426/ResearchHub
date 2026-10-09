import type {Reporter,TestCase,TestResult,FullResult} from '@playwright/test/reporter';
import {mkdirSync,readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import os from 'node:os';

/** CI allowlist: never copies stdout, errors, oracle inputs, proofs or key material. */
export default class SecurityEvidenceReporter implements Reporter {
 private results:{title:string;status:string;durationMs:number;retry:number}[]=[];
 onTestEnd(test:TestCase,result:TestResult){
  this.results.push({title:test.title,status:result.status,durationMs:result.duration,retry:result.retry});
 }
 onEnd(result:FullResult){
  const attempt=process.env.RH_B1_ATTEMPT;
  if(!attempt||!/^[a-zA-Z0-9_-]+$/.test(attempt))throw Error('Valid unique RH_B1_ATTEMPT required');
  const root=resolve('../../storage/runtime/browser-sync-qa'),dir=resolve(root,'security',attempt);
  mkdirSync(dir,{recursive:true});
  const versionsPath=resolve(dir,'versions.json');
  const versions=existsSync(versionsPath)?JSON.parse(readFileSync(versionsPath,'utf8')):{};
  const observedVersion=(v:unknown)=>typeof v==='string'&&/^v?\d+(\.\d+){1,3}$/.test(v)?v:null;
  const buildHash=createHash('sha256').update(readFileSync(resolve(root,'dist/app.js')))
   .update(readFileSync(resolve(root,'dist/app.css'))).digest('hex');
  writeFileSync(resolve(dir,'summary.json'),JSON.stringify({
   scope:'SYNTHETIC B1 Chromium cryptography; network and pairing UI NOT VERIFIED',
   timestamp:new Date().toISOString(),attempt,status:result.status,
   sourceCommit:process.env.GITHUB_SHA??'WORKTREE',buildHash,
   node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()},
   chromium:observedVersion(versions.chromium),hpke:observedVersion(versions.hpke),
   retries:0,tests:this.results.length,results:this.results,
  },null,2));
 }
}
