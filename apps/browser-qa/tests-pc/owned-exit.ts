import type {ChildProcess} from 'node:child_process';
export function observeOwnedExit(child:ChildProcess){
 return new Promise<{code:number|null;signal:NodeJS.Signals|null}>(resolve=>{
  if(child.exitCode!==null||child.signalCode!==null){resolve({code:child.exitCode,signal:child.signalCode});return;}
  child.once('exit',(code,signal)=>resolve({code,signal}));
 });
}
