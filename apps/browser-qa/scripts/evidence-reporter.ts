import type {Reporter,TestCase,TestResult,FullResult} from '@playwright/test/reporter';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import os from 'node:os';
export default class EvidenceReporter implements Reporter{
 private results:{title:string;status:string;durationMs:number;retry:number}[]=[];
 private browser:string|undefined;
 onStdOut(chunk:string|Buffer){for(const line of String(chunk).split('\n')){try{const value=JSON.parse(line);if(typeof value.browser==='string')this.browser=value.browser;}catch{/* Only explicit JSON metadata is accepted. */}}}
 onTestEnd(test:TestCase,result:TestResult){this.results.push({title:test.title,status:result.status,durationMs:result.duration,retry:result.retry});}
 onEnd(result:FullResult){const root=resolve('../../storage/runtime/browser-local-qa'),dir=resolve(root,'evidence');mkdirSync(dir,{recursive:true});const hash=createHash('sha256').update(readFileSync(resolve(root,'dist/app.js'))).update(readFileSync(resolve(root,'dist/app.css'))).digest('hex');writeFileSync(resolve(dir,'summary.json'),JSON.stringify({scope:'SYNTHETIC local browser QA; viewport is not a physical mobile device',timestamp:new Date().toISOString(),status:result.status,node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()},browser:this.browser??'not observed in this filtered run',buildHash:hash,command:process.argv.slice(1),retries:0,tests:this.results.length,results:this.results},null,2));}
}
