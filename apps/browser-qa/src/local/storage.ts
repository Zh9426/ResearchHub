import {DB_NAME,openLocalDatabase} from './db';
export type StorageStatus={persistence:string;estimate:string;opfs:string;testOnly:boolean};
export async function inspectStorage(requestPersistence=false,probe?:'denied'|'unsupported'):Promise<StorageStatus>{
 const manager=navigator.storage;
 const result:StorageStatus={persistence:'持久化 API 不支持',estimate:'使用量估计 API 不支持',opfs:typeof manager?.getDirectory==='function'?'OPFS API 可探测（未创建文件，未验收完整文件系统）':'OPFS API 不支持',testOnly:!!probe};
 if(probe==='unsupported')return result;
 if(probe==='denied')result.persistence='TEST ONLY：模拟持久存储申请被拒绝';
 else if(manager&&typeof manager.persisted==='function'){
  try{
   const persisted=await manager.persisted();
   if(persisted)result.persistence='浏览器报告已授予持久存储';
   else if(requestPersistence&&typeof manager.persist==='function')result.persistence=await manager.persist()?'持久存储申请已获准':'持久存储申请被拒绝；数据仍可能被驱逐';
   else result.persistence=requestPersistence?'持久存储申请 API 不支持':'尚未获得持久存储；可申请';
  }catch(e){result.persistence=`持久存储检查或申请失败：${String(e)}`;}
 }
 if(typeof manager?.estimate==='function')try{const e=await manager.estimate();result.estimate=`使用量估计：${e.usage??'未知'} 字节 / 配额估计：${e.quota??'未知'} 字节（不是可用磁盘保证）`;}catch(e){result.estimate=`使用量估计失败：${String(e)}`;}
 return result;
}
/** Real same-schema version change; another page may intentionally hold an IDB connection. */
export async function probeDatabaseUpgrade(report:(message:string)=>void):Promise<void>{
 const current=await openLocalDatabase();const version=current.version;current.close();
 await new Promise<void>((resolve,reject)=>{
  const request=indexedDB.open(DB_NAME,version+1);
  request.onblocked=()=>report('TEST ONLY：真实升级被其他标签页连接阻塞。请关闭持有连接的旧标签页；本页输入与数据保留。');
  request.onerror=()=>reject(Error(`数据库升级失败：${request.error?.name??'未知错误'}；关闭旧标签页后重试，未删除数据。`));
  request.onsuccess=()=>{request.result.close();report('TEST ONLY：真实数据库升级完成，原数据与 store 保留。');resolve();};
 });
}
