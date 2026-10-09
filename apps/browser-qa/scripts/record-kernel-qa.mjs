/** One-shot C1 runner; owned loopback server, dedicated bundle/profile/attempt. */
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {mkdirSync,writeFileSync,readFileSync,openSync,closeSync,copyFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import os from 'node:os';
import {createServer} from 'node:http';
import {build} from 'esbuild';
import {runOwnedCommand} from './owned-command.mjs';
import {openOwnedKernelBrowser,closeOwnedKernelBrowser} from './owned-kernel-browser.mjs';
const repo=fileURLToPath(new URL('../../../',import.meta.url));
const attempt=process.argv[2];if(!attempt||!/^[a-zA-Z0-9_-]{1,80}$/.test(attempt))throw Error('UNIQUE_ATTEMPT_REQUIRED');
const fault=process.argv[3]??null;if(fault&&!['oracle-timeout','worker-timeout'].includes(fault))throw Error('UNKNOWN_FAULT');
const parent=join(repo,'storage/runtime/browser-sync-qa/c1-local');mkdirSync(parent,{recursive:true});
const output=join(parent,attempt);mkdirSync(output);
const python=process.env.RH_QA_PYTHON??join(repo,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const commands=[];
async function run(exe,args,name,env=process.env){
 const fd=openSync(join(output,name+'.txt'),'wx');
 const injected=(name==='oracle'&&fault==='oracle-timeout')||(name==='browser'&&fault==='worker-timeout');
 if(injected){exe=process.execPath;args=['-e','setInterval(()=>{},1000)'];}
 try{return (await runOwnedCommand(exe,args,{cwd:repo,env,stdio:['ignore',fd,fd],deadlineMs:injected?100:120000,observe:result=>commands.push({name,...result})})).code;}
 finally{closeSync(fd);}
}
let server,ownedBrowser,code=1,bundleSha256=null,phase='BROWSER_LAUNCH',browserCleanup='NOT_STARTED';const errors=[];
const sourceCommit=execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
const workingTreeDirty=Boolean(execFileSync('git',['status','--porcelain'],{cwd:repo,encoding:'utf8'}).trim());
try{
 ownedBrowser=await openOwnedKernelBrowser(join(output,'profile'));phase='ORACLE';
 const oracle=await run(python,['tests/sync_pg/record_kernel_oracle.py','--output',join(output,'oracle.json')],'oracle');if(oracle!==0)throw Error('ORACLE_FAILED');
 copyFileSync(join(repo,'fixtures/sync/v2/record_kernel_cases.json'),join(output,'fixture.json'));
 phase='BUILD';
 const result=await build({entryPoints:[join(repo,'apps/browser-qa/tests-kernel/entry.ts')],outfile:join(output,'kernel.js'),bundle:true,format:'iife',platform:'browser',target:'es2022',metafile:true});
 if(Object.keys(result.metafile.inputs).some(p=>/node_modules|node:/.test(p)))throw Error('NONPURE_KERNEL_BUNDLE');
 writeFileSync(join(output,'bundle-inputs.json'),JSON.stringify(result.metafile.inputs));
 bundleSha256=createHash('sha256').update(readFileSync(join(output,'kernel.js'))).digest('hex');
 phase='SERVER';
 server=createServer((req,res)=>{if(req.url==='/'){res.setHeader('content-type','text/html');res.end('<!doctype html><title>SYNTHETIC C1 kernel</title><script src="/kernel.js"></script>');}else if(req.url==='/kernel.js'){res.setHeader('content-type','text/javascript');res.end(readFileSync(join(output,'kernel.js')));}else{res.statusCode=404;res.end();}});
 await new Promise((done,reject)=>{server.once('error',reject);server.listen(3314,'127.0.0.1',done);});
 phase='BROWSER';code=await run(process.execPath,['apps/browser-qa/node_modules/@playwright/test/cli.js','test','--config','apps/browser-qa/playwright.kernel.config.ts'],'browser',{...process.env,RH_C1_RESULTS:output,RH_C1_CDP:ownedBrowser.endpoint});
 if(code===0)phase='COMPLETE';
}catch(error){errors.push(error);
}finally{
 try{if(server?.listening){server.closeAllConnections();await new Promise(done=>server.close(done));}}catch(error){errors.push(error);}
 if(ownedBrowser){try{await closeOwnedKernelBrowser(ownedBrowser);browserCleanup='PASS';}catch(error){browserCleanup='FAILED';errors.push(error);}}
 if(errors.length){code=1;const detail=error=>({name:error?.name,message:error?.message,stack:error?.stack,errors:Array.isArray(error?.errors)?error.errors.map(detail):undefined});writeFileSync(join(output,'error.txt'),JSON.stringify(errors.map(detail),null,2));}
 writeFileSync(join(output,'summary.json'),JSON.stringify({scope:fault?'FAULT_INJECTED_ONLY; synthetic hanging child with actual owned Chromium':'SYNTHETIC C1 real Chromium and isolated PG; no transport/IDB claim',status:code===0?'PASS':'FAIL',phase,attempt,fault,browserCleanup,commands,sourceCommit,workingTreeDirty,bundleSha256,node:process.version,os:{platform:os.platform(),release:os.release(),arch:os.arch()}},null,2));
}
process.exitCode=code??1;
