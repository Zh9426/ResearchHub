import generic from '../../../../packages/project-modules/generic/manifest.json';
import hdsp from '../../../../packages/project-modules/hdsp/manifest.json';
import ice from '../../../../packages/project-modules/ice-sonocuring/manifest.json';
import {openLocalDatabase,STORES} from './db';
import type {Identity,ModuleSnapshot,Project} from './model';
export async function prepareSyntheticProjects():Promise<Project[]>{
 return Promise.all([generic,hdsp,ice].map(async(raw,index)=>{
  const snapshot=structuredClone(raw) as ModuleSnapshot;
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(snapshot)));
  return {id:crypto.randomUUID(),route_alias:['generic','hdsp','ice'][index],title:`${snapshot.name} · SYNTHETIC`,scope:'SYNTHETIC',module_id:snapshot.id,module_version:snapshot.version,module_snapshot:snapshot,module_hash:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join(''),local_format_version:1};
 }));
}
export async function initializeSyntheticWorkspace(open=openLocalDatabase):Promise<void>{
 // Hashing/UUIDs occur before entering a short transaction.
 const projects=await prepareSyntheticProjects();const identity:Identity={id:'identity',workspace_id:crypto.randomUUID(),device_id:crypto.randomUUID(),scope:'SYNTHETIC_QA',authorization:'none'};
 const db=await open();
 return new Promise((resolve,reject)=>{
  const tx=db.transaction([...STORES],'readwrite');let error:Error|undefined;
  const checks=STORES.map(name=>tx.objectStore(name).count());let pending=checks.length;
  for(const request of checks)request.onsuccess=()=>{if(--pending)return;if(checks.some(r=>r.result>0)){error=Error('工作区非空，不会覆盖已有数据。');tx.abort();return;}tx.objectStore('meta').add(identity);for(const project of projects)tx.objectStore('projects').add(project);};
  tx.oncomplete=()=>{db.close();resolve();};tx.onabort=()=>{db.close();reject(error??tx.error??Error('合成初始化未提交'));};
 });
}
