import {spawn} from 'node:child_process';
export async function runOwnedCommand(exe,args,{deadlineMs=120000,observe=()=>{},onSpawn=()=>{},...options}={}){
 return new Promise((resolve,reject)=>{
  const child=spawn(exe,args,options);let timedOut=false,finished=false,escalation,limit;const errors=[];
  const finish=(code,signal,error)=>{
   if(finished)return;finished=true;clearTimeout(timer);clearTimeout(escalation);clearTimeout(limit);
   if(error)errors.push(error);const result={code,signal,timedOut,exited:child.pid===undefined||child.exitCode!==null||child.signalCode!==null};
   try{observe(result);}catch(error){errors.push(error);}
   if(errors.length)reject(errors.length===1?errors[0]:new AggregateError(errors,'COMMAND_AND_CLEANUP_FAILED'));else resolve(result);
  };
  const timer=setTimeout(()=>{
   timedOut=true;errors.push(Error('COMMAND_DEADLINE'));
   try{child.kill('SIGTERM');}catch(error){errors.push(error);}
   escalation=setTimeout(()=>{if(!finished){try{child.kill('SIGKILL');}catch(error){errors.push(error);}}},5000);
   limit=setTimeout(()=>finish(child.exitCode,child.signalCode,Error('COMMAND_CLEANUP_DEADLINE')),10000);
  },deadlineMs);
  child.once('error',error=>{if(child.pid===undefined)finish(null,null,error);else{errors.push(error);try{child.kill('SIGKILL');}catch(e){errors.push(e);}}});
  child.once('exit',(code,signal)=>finish(code,signal));
  try{onSpawn(child);}catch(error){errors.push(error);child.kill('SIGKILL');}
 });
}
