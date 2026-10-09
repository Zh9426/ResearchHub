import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {waitOwnedReady} from '../tests-pc/owned-start.ts';
test('no READY reaches deadline and reaps only its own child',async()=>{
 const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)']);
 try{
  await assert.rejects(Promise.race([waitOwnedReady(child,50),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('TEST_WATCHDOG')),1500);timer.unref();})]),/PC_START_DEADLINE/);
  assert.ok(child.exitCode!==null||child.signalCode!==null);
 }finally{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');}
});
test('early exit fails without hanging',async()=>{
 const child=spawn(process.execPath,['-e','process.exit(7)']);
 await assert.rejects(waitOwnedReady(child,1000),/PC_START_FAILED/);assert.equal(child.exitCode,7);
});
test('spawn failure does not await an exit that cannot happen',async()=>{
 const child=spawn('rh-nonexistent-synthetic-executable-20261009',[]);
 await assert.rejects(waitOwnedReady(child,1000),{code:'ENOENT'});assert.equal(child.pid,undefined);
});
test('split READY keeps the owned process alive and removes startup listeners',async()=>{
 const child=spawn(process.execPath,['-e',"process.stdout.write('PC_QA_');setTimeout(()=>process.stdout.write('READY'),50);setInterval(()=>{},1000)"]);
 try{await waitOwnedReady(child,1000);assert.equal(child.exitCode,null);assert.equal(child.signalCode,null);assert.equal(child.listenerCount('exit'),0);assert.equal(child.listenerCount('error'),0);assert.equal(child.stdout!.listenerCount('data'),0);}
 finally{const exited=new Promise<void>(resolve=>child.once('exit',()=>resolve()));child.kill('SIGKILL');await exited;}
});
