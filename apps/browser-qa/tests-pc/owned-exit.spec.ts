import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {observeOwnedExit} from './owned-exit';

test('owned signal退出早于cleanup等待：exitCode仍null但预注册promise完成',async()=>{
 const child=spawn(process.execPath,['-e',"console.log('READY');setInterval(()=>{},1000)"],{stdio:['ignore','pipe','pipe']});
 const observed=observeOwnedExit(child);
 await once(child.stdout!,'data');const signalExit=once(child,'exit');
 child.kill('SIGTERM');await signalExit;
 expect(child.exitCode).toBeNull();expect(child.signalCode).toBe('SIGTERM');
 // The old exitCode-only check subscribes after the sole exit event and never resolves.
 const old=new Promise<string>(resolve=>child.exitCode!==null?resolve('done'):child.once('exit',()=>resolve('done')));
 expect(await Promise.race([old,new Promise<string>(resolve=>setTimeout(()=>resolve('missed'),30))])).toBe('missed');
 expect(await observed).toEqual({code:null,signal:'SIGTERM'});
 expect(await observeOwnedExit(child)).toEqual({code:null,signal:'SIGTERM'});
});
