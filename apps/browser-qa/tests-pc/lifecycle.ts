import {spawn} from 'node:child_process';
import {resolve,delimiter} from 'node:path';
import {observeOwnedExit} from './owned-exit';
import {waitOwnedReady} from './owned-start';
const root=resolve('../..');const python=process.env.RH_QA_PYTHON??resolve(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const env={...process.env,HUB_SYNC_QA:'1',PYTHONPATH:['apps/api','.'].join(delimiter)};
export async function startPc(args:string[]=[]){
 const process_=spawn(python,['-m','researchhub.sync.pc_cli','start',...args],{cwd:root,env,stdio:['ignore','pipe','pipe']});
 const exited=observeOwnedExit(process_);
 process_.stderr!.on('data',d=>{if(String(d).includes('ConnectionResetError'))console.log('PC_STAGE CONNECTION_RESET');});
 await waitOwnedReady(process_);
 return {process_,exited};
}
export async function stopPc(server:Awaited<ReturnType<typeof startPc>>){
 const stop=spawn(python,['-m','researchhub.sync.pc_cli','stop'],{cwd:root,env,stdio:'ignore'});const result=await observeOwnedExit(stop);
 if(result.code!==0){if(server.process_.exitCode===null&&server.process_.signalCode===null)server.process_.kill();await server.exited;throw Error('PC_STOP_FAILED');}
 const closed=await server.exited;if(closed.code!==0)throw Error('PC_EXIT_NOT_CLEAN');
}
