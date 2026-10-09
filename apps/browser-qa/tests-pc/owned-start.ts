import type {ChildProcess} from 'node:child_process';
export async function waitOwnedReady(child:ChildProcess,deadlineMs=15000){
 try{
  await new Promise<void>((resolve,reject)=>{
   let tail='';
   const clear=()=>{clearTimeout(timer);child.off('error',error);child.off('exit',exit);child.stdout?.off('data',data);};
   const error=(cause:Error)=>{clear();reject(cause);};
   const exit=()=>error(Error('PC_START_FAILED'));
   const data=(chunk:Buffer)=>{const text=tail+String(chunk);tail=text.slice(-64);if(text.includes('PC_QA_READY')){clear();resolve();}};
   const timer=setTimeout(()=>error(Error('PC_START_DEADLINE')),deadlineMs);
   child.once('error',error);child.once('exit',exit);child.stdout?.on('data',data);
   if(child.exitCode!==null||child.signalCode!==null)exit();
  });
 }catch(primary){
  // No PID on spawn failure means there is no owned process to reap.
  if(child.pid!==undefined&&child.exitCode===null&&child.signalCode===null){
   try{
    await new Promise<void>((resolve,reject)=>{
     const clear=()=>{clearTimeout(timer);child.off('exit',exit);child.off('error',error);};
     const exit=()=>{clear();resolve();};
     const error=(cause:Error)=>{clear();reject(cause);};
     const timer=setTimeout(()=>error(Error('PC_START_CLEANUP_DEADLINE')),5000);
     child.once('exit',exit);child.once('error',error);
     try{child.kill('SIGKILL');}catch(cause){error(cause as Error);}
    });
   }catch(cleanup){throw new AggregateError([primary,cleanup],'PC startup and owned cleanup failed');}
  }
  throw primary;
 }
}
