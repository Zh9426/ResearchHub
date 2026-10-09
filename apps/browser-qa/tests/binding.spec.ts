import {test,expect,type BrowserContext} from '@playwright/test';
import {resolve} from 'node:path';
import {runtime,origin,startServer,launch,cleanup} from './lifecycle';

for(const field of ['identity','action','aad','digest'])test(`cached envelope rejects independent ${field} misbinding without encryption or counter change`,async()=>{
 const server=await startServer();let context:BrowserContext|undefined;
 try{
  context=await launch(resolve(runtime,'profiles',`binding-${field}-${Date.now()}`));
  const p=await context.newPage();await p.goto(origin);
  const result=await p.evaluate(async(field)=>{
   const qa=(window as any).__SECURITY_QA__,id=await qa.create(),action='TESTONLY-binding',payload='TESTONLY-payload';
   const envelope=await qa.seal(id,action,payload),before=await qa.status(id);
   const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-TESTONLY-security-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});
   const write=(value:any)=>new Promise<void>((ok,no)=>{const tx=db.transaction('actions','readwrite');tx.objectStore('actions').put(value);tx.oncomplete=()=>ok();tx.onabort=()=>no(tx.error);});
   const row={id:id+':'+action,digest:envelope.digest,state:'complete',envelope};
   const altered={...envelope,[field]:field==='digest'?'0'.repeat(64):'TESTONLY-mismatched-'+field};
   let encryptions=0,rejected=false;const original=SubtleCrypto.prototype.encrypt;
   SubtleCrypto.prototype.encrypt=function(...args:any[]){encryptions++;return original.apply(this,args as any);};
   try{
    await write({...row,envelope:altered});
    try{await qa.seal(id,action,payload);}catch{rejected=true;}
    const after=await qa.status(id);
    await write(row);const retry=await qa.seal(id,action,payload);
    return {rejected,counterUnchanged:before.counter===after.counter,encryptions,exactRetry:JSON.stringify(retry)===JSON.stringify(envelope),opened:await qa.open(id,action)};
   }finally{SubtleCrypto.prototype.encrypt=original;db.close();}
  },field);
  expect(result).toEqual({rejected:true,counterUnchanged:true,encryptions:0,exactRetry:true,opened:'TESTONLY-payload'});
 }finally{await cleanup(server,[context]);}
});
