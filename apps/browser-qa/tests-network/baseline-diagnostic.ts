import type {Page} from '@playwright/test';
/** Failure-only read; never return text, object identities, envelopes, or keys. */
export async function baselineDiagnostic(page:Page,expected:string){
 let dom='read_failed';
 try{const field=page.getByLabel('观察',{exact:true}),count=await field.count();dom=count===0?'missing':count!==1?'ambiguous':!await field.isVisible()?'hidden':await field.inputValue()===expected?'expected':'other';}catch{/* Preserve the original business assertion if diagnostic reads fail. */}
 let persisted={local:'read_failed',kernel:'read_failed'};
 try{persisted=await page.evaluate(async expected=>{
  const objectId=location.pathname.split('/').at(-1)!;
  const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-browser-sync-qa-business-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);r.onupgradeneeded=()=>{r.transaction?.abort();no(Error('DIAGNOSTIC_DATABASE_MISSING'));};});
  try{return await new Promise<{local:string;kernel:string}>((ok,no)=>{
   const tx=db.transaction(['objects','meta']),object=tx.objectStore('objects').get(objectId),meta=tx.objectStore('meta').getAll();
   tx.onabort=()=>no(tx.error);tx.onerror=()=>no(tx.error);
   tx.oncomplete=()=>{const value=object.result,key='ResearchRun:'+objectId;
    const state=meta.result.find(r=>r.id.startsWith('record-kernel:')&&Object.hasOwn(r.state?.heads??{},key))?.state;
    const heads=state?.heads[key]??[],revision=state?.projections[key],document=revision?state.revisions[revision]?.document:null;
    ok({local:!value?'missing':value.kind==='Run'&&value.observation===expected?'expected':'other',kernel:heads.length>1?'conflicted':!document?'missing':document.observation===expected?'expected':'other'});
   };
  });}finally{db.close();}
 },expected);}catch{/* Only fixed failure enums escape; no exception text. */}
 return {dom,...persisted};
}
