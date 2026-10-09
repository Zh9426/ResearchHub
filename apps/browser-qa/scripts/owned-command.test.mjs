import {test} from 'node:test';
import assert from 'node:assert/strict';
import {runOwnedCommand} from './owned-command.mjs';
test('deadline fails and reaps this exact silent child',async()=>{
 let child,result;
 try{await assert.rejects(Promise.race([runOwnedCommand(process.execPath,['-e','setInterval(()=>{},1000)'],{deadlineMs:60,stdio:'ignore',onSpawn:p=>child=p,observe:r=>result=r}),new Promise((_,reject)=>{const t=setTimeout(()=>reject(Error('TEST_WATCHDOG')),1500);t.unref();})]),/COMMAND_DEADLINE/);
 assert.equal(result.timedOut,true);assert.ok(child.exitCode!==null||child.signalCode!==null);
 }finally{if(child&&child.exitCode===null&&child.signalCode===null){const exited=new Promise(done=>child.once('exit',done));child.kill('SIGKILL');await exited;}}
});
test('normal exit and spawn failure are bounded and retained',async()=>{
 const result=await runOwnedCommand(process.execPath,['-e','process.exit(7)'],{deadlineMs:1000,stdio:'ignore'});assert.equal(result.code,7);assert.equal(result.timedOut,false);
 await assert.rejects(runOwnedCommand('rh-nonexistent-command-20261009',[],{deadlineMs:1000,stdio:'ignore'}),{code:'ENOENT'});
});
