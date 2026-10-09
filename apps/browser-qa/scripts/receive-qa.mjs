/** Owned one-shot actual Chromium/IDB/native crypto; no Relay network claim. */
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {build} from 'esbuild';
import {openOwnedKernelBrowser,closeOwnedKernelBrowser} from './owned-kernel-browser.mjs';
const repo=fileURLToPath(new URL('../../../',import.meta.url)),attempt=process.argv[2];
if(!attempt||!/^[a-zA-Z0-9_-]{1,80}$/.test(attempt))throw Error('UNIQUE_ATTEMPT_REQUIRED');
const parent=join(repo,'storage/runtime/browser-sync-qa/c-receive');mkdirSync(parent,{recursive:true});const output=join(parent,attempt);mkdirSync(output);
let browser,server,error,cleanup='NOT_STARTED',cases=[],browserVersion,bundleSha256;
const sourceCommit=execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim(),workingTreeDirty=Boolean(execFileSync('git',['status','--porcelain'],{cwd:repo,encoding:'utf8'}).trim());
async function deadline(promise,ms){let timer;try{return await Promise.race([promise,new Promise((_,no)=>{timer=setTimeout(()=>no(Error('RECEIVE_QA_DEADLINE')),ms);})]);}finally{clearTimeout(timer);}}
try{
 await build({entryPoints:[join(repo,'apps/browser-qa/tests-receive/entry.ts')],outfile:join(output,'app.js'),bundle:true,jsx:'automatic',alias:{react:join(repo,'apps/browser-qa/node_modules/react'),'react-dom':join(repo,'apps/browser-qa/node_modules/react-dom')},format:'iife',platform:'browser',target:'es2022'});
 bundleSha256=createHash('sha256').update(readFileSync(join(output,'app.js'))).digest('hex');
 server=createServer((req,res)=>{res.setHeader('content-type',req.url==='/app.js'?'text/javascript':'text/html');res.end(req.url==='/app.js'?readFileSync(join(output,'app.js')):'<!doctype html><title>SYNTHETIC receive QA</title><script src="/app.js"></script>');});
 await new Promise((ok,no)=>{server.once('error',no);server.listen(3314,'127.0.0.1',ok);});
 browser=await openOwnedKernelBrowser(join(output,'profile'));browserVersion=browser.context.browser().version();const page=await browser.context.newPage();await page.goto('http://127.0.0.1:3314');
 cases=await deadline(page.evaluate(async()=>{
  const q=window.receiveQA,passed=[];const assert=(v,message)=>{if(!v)throw Error(message);};
  assert(typeof q.sealer.authorization==='function','authorization installer missing');
  assert(typeof q.sealer.receiver==='function','atomic page receiver missing');
  const f=await q.fixture(),installer=await q.sealer.authorization();
  const options={ownerRoot:f.binding.trust.owner_root,recoveryRoot:f.binding.trust.recovery_root,grant:f.grant};
  for(const point of ['afterBlocked','afterPin','afterGrant']){
   let failed=false;try{await installer.install(f.wrapper,{...options,hooks:{[point]:async()=>{throw Error('TEST_ONLY_INTERRUPT');}}});}catch(e){failed=e.message==='TEST_ONLY_INTERRUPT';if(!failed)throw Error('install failed: '+e.message);}
   assert(failed,'install breakpoint '+point);const a=await q.meta('authorization:'+f.project.id);assert(a.state==='BLOCKED','blocked before pin');
  }
  const ready=await installer.install(f.wrapper,options),again=await installer.install(f.wrapper,options);assert(ready.generation===again.generation&&ready.state==='READY','idempotent install generation');passed.push('installation-three-breakpoints-and-retry');
  const receiver=await q.sealer.receiver(),tx=f.transaction('remote A'),valid=await f.page([tx]);
  const bad=await f.page([tx,f.transaction('bad tail')]);
  bad.rows[1].envelope.signature=q.security.b64encode(new Uint8Array(64));
  bad.rows[1].envelope_digest=await q.digest(bad.rows[1].envelope);
  bad.rows[1].chain_digest=await q.security.extendChain(bad.rows[0].chain_digest,1,[{sequence:2,envelope_digest:bad.rows[1].envelope_digest}]);bad.chain_digest=bad.rows[1].chain_digest;
  let denied=false;try{await receiver.receive(f.project.id,bad);}catch(e){denied=e.message==='INVALID_SIGNATURE';if(!denied)throw Error('unexpected signature gate: '+e.message);}assert(denied&&!await q.meta('record-kernel:'+f.project.id),'bad tail must roll back page');passed.push('whole-page-native-signature-tail-rejected');
  denied=false;try{await receiver.receive(f.project.id,valid,{abortCommit:true});}catch{denied=true;}assert(denied&&!await q.meta('record-kernel:'+f.project.id),'real IDB abort must preserve cursor and kernel');passed.push('real-idb-abort');
  await receiver.receive(f.project.id,valid);const stored=await q.meta('record-kernel:'+f.project.id),cursor=await q.meta('relay-cursor:'+f.project.id);assert(stored.state.sequence===1&&cursor.cursor===1,'atomic durable receive');passed.push('native-verified-page-commit');
  const original=(await q.commands.snapshot()).objects.find(o=>o.id===tx.changes[0].object_id);
  const c=await q.commands.save({...original,body:'offline C'});await q.commands.save({...c,body:'offline D'});
  const ops=(await q.commands.snapshot()).operations.filter(o=>o.object_id===original.id).sort((x,y)=>x.payload.local_edit_version-y.payload.local_edit_version);
  const parent=await q.digest(tx.changes[0]),remote=f.transaction('remote B',original.id,[parent],[tx.transaction_id]);
  await receiver.receive(f.project.id,await f.page([remote],1,cursor.chain_digest));
  const cm=await q.adapter.convert(ops[0].id),dm=await q.adapter.convert(ops[1].id);
  assert(JSON.stringify(cm.parents)===JSON.stringify([parent]),'offline C must retain A parent after pull B');assert(dm.parents[0]===cm.revision,'multi-step frozen predecessor');
  assert(JSON.stringify(await q.adapter.convert(ops[0].id))===JSON.stringify(cm),'converted exact retry after pull');
  const conflict=(await q.meta('record-kernel:'+f.project.id)).state;
  assert(conflict.heads['Note:'+original.id].length===2&&!conflict.projections['Note:'+original.id],'local converted branch participates in kernel conflict');
  assert((await q.commands.snapshot()).objects.find(o=>o.id===original.id).body==='offline D','pull preserves pending work');passed.push('offline-causal-branch-and-exact-retry');
  assert(!await receiver.completeHandoff(ops[0].id,cm.transaction_id,ops[0].payload.local_edit_version),'late handoff must retain newer pending');
  assert(await receiver.completeHandoff(ops[1].id,dm.transaction_id,ops[1].payload.local_edit_version),'exact latest handoff clears pending');
  assert(!(await q.meta('pending-operation:'+original.id)),'pending marker independent of immutable operations');
  assert((await q.commands.snapshot()).operations.every(o=>o.state==='pending'),'handoff must not rewrite operation log');passed.push('exact-handoff-and-immutable-operation-log');
  const currentCursor=await q.meta('relay-cursor:'+f.project.id);
  const next=await f.page([f.transaction('next')],2,currentCursor.chain_digest);denied=false;
  const revoke=await q.signed('Membership',{...f.head,membership_epoch:3,key_epoch:2,previous_digest:await q.digest(f.head),operation:'revoke',members:f.head.members.map(m=>m.device_id===f.device.deviceId?{...m,status:'REVOKED',revoked_at:1}:m)},f.owner.signing.privateKey);
  try{await receiver.receive(f.project.id,next,{beforeCommit:async()=>{await installer.revoke(f.project.id,[f.boot,f.head,revoke]);}});}catch(e){denied=e.message==='AUTHORIZATION_NOT_READY';if(!denied)throw e;}
  assert(denied&&(await q.meta('relay-cursor:'+f.project.id)).cursor===2,'authorization CAS prevents stale receive');passed.push('authorization-generation-cas');
  passed.push(...await q.receivedRunWorkbench(q));passed.push(...await q.remoteOnlyWorkbench(q));
  assert(typeof q.manualReceipts==='function','native manual receipt API missing');passed.push(...await q.manualReceipts(q));
  passed.push(...await q.adversarial(q));passed.push(...await q.identityCollisions(q));return passed;
 }),90000);
}catch(e){error=e;writeFileSync(join(output,'error.txt'),String(e.stack??e));}
finally{
 const results=await Promise.allSettled([Promise.resolve().then(async()=>{if(server?.listening){server.closeAllConnections();await deadline(new Promise(done=>server.close(done)),10000);}}),Promise.resolve().then(async()=>{if(browser)await closeOwnedKernelBrowser(browser);})]);
 const failures=results.filter(r=>r.status==='rejected');cleanup=failures.length?'FAILED':'PASS';if(failures.length){error??=failures[0].reason;writeFileSync(join(output,'cleanup-error.txt'),failures.map(r=>String(r.reason)).join('\n'));}
 writeFileSync(join(output,'summary.json'),JSON.stringify({attempt,status:error?'FAIL':'PASS',scope:'TEST_ONLY synthetic native Chromium IDB + crypto; no Relay network claim',cases,cleanup,sourceCommit,workingTreeDirty,bundleSha256,browserVersion,retries:0},null,2));
}
if(error){console.error(error.message);process.exitCode=1;}else console.log(JSON.stringify({status:'PASS',cases,cleanup}));
