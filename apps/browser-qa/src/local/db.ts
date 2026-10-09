import type {LocalSnapshot} from './model';
export const DB_NAME='researchhub-synthetic-local-v1';
export const STORES=['meta','projects','objects','operations','audit'] as const;
export async function openLocalDatabase():Promise<IDBDatabase>{
 return new Promise((resolve,reject)=>{
  const request=indexedDB.open(DB_NAME,1);let failed=false;
  request.onupgradeneeded=()=>{for(const name of STORES)request.result.createObjectStore(name,{keyPath:'id'});};
  request.onblocked=()=>{failed=true;reject(Error('数据库升级被其他标签页阻塞，请关闭旧标签页后重试；未删除任何数据。'));};
  request.onerror=()=>reject(request.error??Error('本地数据库打开失败，请重试；未删除任何数据。'));
  request.onsuccess=()=>{const db=request.result;if(failed){db.close();return;}db.onversionchange=()=>db.close();resolve(db);};
 });
}
// One readonly transaction supplies a consistent rescue/diagnostic snapshot.
export async function readSnapshot():Promise<LocalSnapshot>{
 const db=await openLocalDatabase();
 try{return await new Promise((resolve,reject)=>{
  const tx=db.transaction([...STORES],'readonly');const out:LocalSnapshot={identity:null,projects:[],objects:[],operations:[],audit:[]};
  tx.objectStore('meta').get('identity').onsuccess=e=>{out.identity=(e.target as IDBRequest).result??null;};
  for(const name of ['projects','objects','operations','audit'] as const)tx.objectStore(name).getAll().onsuccess=e=>{out[name]=(e.target as IDBRequest).result;};
  tx.oncomplete=()=>{db.close();resolve(out);};tx.onabort=()=>{db.close();reject(tx.error??Error('读取本地快照失败'));};
 });}finally{db.close();}
}
