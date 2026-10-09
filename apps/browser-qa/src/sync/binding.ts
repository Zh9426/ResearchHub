import {digest} from '../../../../packages/sync-protocol/src/browser';
import type {ModuleSnapshot,Project} from '../local/model';
export type PublicPrincipal={device_id:string;actor_id:string;actor_type:'human'|'codex'|'chatgpt'|'system';role:'owner'|'writer'|'reader'};
export type PublicProjectBinding={
 binding_version:1;semantic_project_id:string;opaque_project_id:string;module_snapshot:ModuleSnapshot;module_snapshot_hash:string;
 local_module_hash:{algorithm:'sha256-json-stringify';value:string};capabilities:{protocol_version:2;schema_version:2;object_types:['ResearchRun','Note']};
 principal:PublicPrincipal;principal_map:PublicPrincipal[];
 trust:{membership_epoch:number;key_epoch:number;manifest_head:string;owner_root:string;recovery_root:string;manifest_chain:Record<string,unknown>[]};
};
export type BindingPreview={state:'UNVERIFIED'|'BLOCKED';binding?:PublicProjectBinding;reasons:string[]};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function validUuid(value:unknown){return typeof value==='string'&&uuid.test(value)&&value!=='00000000-0000-0000-0000-000000000000';}
const hash=/^[0-9a-f]{64}$/;
function exact(value:unknown,keys:string[],path:string,reasons:string[]):value is Record<string,unknown>{
 if(!value||typeof value!=='object'||Array.isArray(value)){reasons.push(`${path}: object required`);return false;}
 const obj=value as Record<string,unknown>;for(const key of keys)if(!Object.hasOwn(obj,key))reasons.push(`${path}.${key}: required`);for(const key of Object.keys(obj))if(!keys.includes(key))reasons.push(`${path}.${key}: unknown field`);return true;
}
export async function jsonHash(value:unknown){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');}
/** Structure/content validation only. Claimed roots and manifest chain NEVER establish trust. */
export async function previewBinding(input:unknown,localProject?:Project):Promise<BindingPreview>{
 const reasons:string[]=[];
 if(!exact(input,['binding_version','semantic_project_id','opaque_project_id','module_snapshot','module_snapshot_hash','local_module_hash','capabilities','principal','principal_map','trust'],'binding',reasons))return {state:'BLOCKED',reasons};
 const b=input as unknown as PublicProjectBinding;
 for(const key of ['semantic_project_id','opaque_project_id'] as const)if(!validUuid(b[key]))reasons.push(`${key}: invalid UUID`);
 if(b.binding_version!==1)reasons.push('binding_version: unsupported');
 if(exact(b.local_module_hash,['algorithm','value'],'local_module_hash',reasons)){
  if(b.local_module_hash.algorithm!=='sha256-json-stringify'||!hash.test(b.local_module_hash.value))reasons.push('local_module_hash: invalid source');
 }
 if(exact(b.capabilities,['protocol_version','schema_version','object_types'],'capabilities',reasons)&&JSON.stringify(b.capabilities)!==JSON.stringify({protocol_version:2,schema_version:2,object_types:['ResearchRun','Note']})){
  if(b.capabilities.protocol_version!==2||b.capabilities.schema_version!==2||JSON.stringify(b.capabilities.object_types)!=='["ResearchRun","Note"]')reasons.push('capabilities: unsupported');
 }
 if(exact(b.principal,['device_id','actor_id','actor_type','role'],'principal',reasons)){
  for(const k of ['device_id','actor_id'] as const)if(!validUuid(b.principal[k]))reasons.push(`principal.${k}: invalid UUID`);
  if(!['human','codex','chatgpt','system'].includes(b.principal.actor_type)||!['owner','writer','reader'].includes(b.principal.role))reasons.push('principal: unsupported');
 }
 if(!Array.isArray(b.principal_map)||!b.principal_map.length)reasons.push('principal_map: full mapping required');
 else {
  const seen=new Set<string>();for(const [i,p] of b.principal_map.entries()){
   if(exact(p,['device_id','actor_id','actor_type','role'],`principal_map.${i}`,reasons)){
    if(!validUuid(p.device_id)||!validUuid(p.actor_id)||!['human','codex','chatgpt','system'].includes(p.actor_type)||!['owner','writer','reader'].includes(p.role)||seen.has(p.device_id))reasons.push(`principal_map.${i}: invalid or duplicate principal`);seen.add(p.device_id);
   }
  }
  if(!b.principal_map.some(p=>p&&p.device_id===b.principal?.device_id&&p.actor_id===b.principal?.actor_id&&p.actor_type===b.principal?.actor_type&&p.role===b.principal?.role))reasons.push('principal: absent from principal_map');
 }
 if(exact(b.trust,['membership_epoch','key_epoch','manifest_head','owner_root','recovery_root','manifest_chain'],'trust',reasons)){
  for(const k of ['membership_epoch','key_epoch'] as const)if(!Number.isSafeInteger(b.trust[k])||b.trust[k]<1)reasons.push(`trust.${k}: invalid epoch`);
  for(const k of ['manifest_head','owner_root','recovery_root'] as const)if(!hash.test(b.trust[k]))reasons.push(`trust.${k}: invalid digest`);
  if(!Array.isArray(b.trust.manifest_chain)||!b.trust.manifest_chain.length||b.trust.manifest_chain.some(x=>!x||typeof x!=='object'||Array.isArray(x)))reasons.push('trust.manifest_chain: full chain required');
 }
 try{
  if(!b.module_snapshot||b.module_snapshot.version!=='0.2.1'||!['generic','hdsp','ice-sonocuring'].includes(b.module_snapshot.id)||!Array.isArray(b.module_snapshot.run_types)||!b.module_snapshot.run_types.length||b.module_snapshot.run_types.some(t=>typeof t.id!=='string'||typeof t.name!=='string'))reasons.push('module_snapshot: unsupported schema');
  if(!hash.test(b.module_snapshot_hash)||await digest(b.module_snapshot)!==b.module_snapshot_hash)reasons.push('module_snapshot_hash: content mismatch');
  if(await jsonHash(b.module_snapshot)!==b.local_module_hash?.value)reasons.push('local_module_hash: content mismatch');
  if(localProject){if(localProject.id!==b.semantic_project_id)reasons.push('semantic_project_id: local identity mismatch; names never merge');if(await digest(localProject.module_snapshot)!==b.module_snapshot_hash||localProject.module_hash!==b.local_module_hash.value)reasons.push('module_snapshot: local frozen snapshot mismatch');}
 }catch{reasons.push('module_snapshot: canonical validation failed');}
 return reasons.length?{state:'BLOCKED',reasons}:{state:'UNVERIFIED',binding:structuredClone(b),reasons:['TRUST_NOT_VERIFIED: owner pin, signatures and device authorization required']};
}
