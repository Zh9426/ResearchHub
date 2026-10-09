/** Business authorization is the short-transaction CAS authority. Vault is a separate DB. */
import {canonicalBytes,digest,strictLoads} from '../../../../packages/sync-protocol/src/browser';
import {verifyBootstrap,verifyTransition,verifySigned,verifyGrant,memberOf,fields,type PublicObject} from '../../../../packages/secure-sync/src/membership-core';
import type {BrowserVault,Trust} from '../../../../packages/secure-sync/src/vault-browser';
import {previewBinding,type PublicProjectBinding} from './binding';
import type {BindingRecord} from './wire';
export const request=<T>(r:IDBRequest<T>)=>new Promise<T>((ok,no)=>{r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});
export async function businessTransaction<T>(open:()=>Promise<IDBDatabase>,stores:string[],mode:IDBTransactionMode,work:(tx:IDBTransaction)=>Promise<T>):Promise<T>{
 const db=await open(),tx=db.transaction(stores,mode);let result:T,error:unknown;
 const done=new Promise<T>((ok,no)=>{tx.oncomplete=()=>ok(result);tx.onabort=()=>no(error??tx.error??Error('BUSINESS_ABORTED'));});
 try{result=await work(tx);}catch(e){error=e;try{tx.abort();}catch{}}
 try{return await done;}finally{db.close();}
}
export type Authorization={id:string;state:'BLOCKED'|'READY';generation:number;token:string;install_digest:string;head:string;membership_epoch:number;key_epoch:number;principal_map_digest:string;target:PublicProjectBinding;binding_fingerprint?:string;phase:'INSTALLING'|'INSTALLED'};
export function requireAuthorization(a:Authorization|undefined,b:BindingRecord|undefined):asserts a is Authorization{
 if(!a||a.state!=='READY'||a.phase!=='INSTALLED'||!b||b.state!=='VERIFIED'||a.generation!==b.generation||a.head!==b.binding.trust.manifest_head||a.binding_fingerprint!==JSON.stringify(b))throw Error('AUTHORIZATION_NOT_READY');
}
type InstallOptions={ownerRoot:string;recoveryRoot:string;grant?:PublicObject;hooks?:{afterBlocked?:()=>Promise<void>;afterPin?:()=>Promise<void>;afterGrant?:()=>Promise<void>};beforeReady?:(trust:Trust)=>Promise<void>;commit?:(tx:IDBTransaction,record:BindingRecord)=>Promise<void>};
export class AuthorizationInstaller{
 constructor(private open:()=>Promise<IDBDatabase>,private vault:BrowserVault){}
 private read(project:string){return businessTransaction(this.open,['meta'],'readonly',async tx=>({a:await request(tx.objectStore('meta').get('authorization:'+project)) as Authorization|undefined,b:await request(tx.objectStore('meta').get('binding:'+project)) as BindingRecord|undefined}));}
 async install(input:PublicObject,options:InstallOptions):Promise<Authorization>{
  const wrapper=structuredClone(input);canonicalBytes(wrapper);fields(wrapper,['version','binding','signature']);if(wrapper.version!==1)throw Error('BINDING_INVALID');
  const binding=wrapper.binding as PublicProjectBinding,preview=await previewBinding(binding);if(preview.state==='BLOCKED')throw Error('BINDING_INVALID');
  const trust=binding.trust;if(trust.owner_root!==options.ownerRoot||trust.recovery_root!==options.recoveryRoot)throw Error('PIN_ROOT_MISMATCH');
  const chain=trust.manifest_chain as PublicObject[];let head=await verifyBootstrap(chain[0],options.ownerRoot,options.recoveryRoot);for(const next of chain.slice(1))head=await verifyTransition(head,next,options.recoveryRoot);
  if(await digest(head)!==trust.manifest_head||head.membership_epoch!==trust.membership_epoch||head.key_epoch!==trust.key_epoch||head.opaque_project_id!==binding.opaque_project_id)throw Error('BINDING_HEAD_MISMATCH');
  await verifySigned('PcProjectBinding',wrapper,memberOf(head,head.authority_device_id,['owner']).signing_public_key);
  const device=await this.vault.device(),self=memberOf(head,device.deviceId);
  if(binding.principal.device_id!==device.deviceId||self.role!==binding.principal.role||self.signing_public_key!==device.signingPublic||self.recipient_public_key!==device.recipientPublic)throw Error('TARGET_PRINCIPAL_MISMATCH');
  const active=head.members.filter((m:PublicObject)=>m.status==='ACTIVE');
  if(active.length!==binding.principal_map.length||active.some((m:PublicObject)=>!binding.principal_map.some(p=>p.device_id===m.device_id&&p.role===m.role)))throw Error('PRINCIPAL_MAP_MISMATCH');
  if(options.grant){await verifyGrant(options.grant,head);if(options.grant.context.recipient_device_id!==device.deviceId)throw Error('RECIPIENT_MISMATCH');}
  return this.installVerified(binding,await digest({wrapper,grant:options.grant??null}),options,false);
 }
 /** Existing pin roots only; a revoke cannot invent or rename any principal. */
 async revoke(project:string,chain:PublicObject[],hooks:InstallOptions['hooks']={}):Promise<Authorization>{
  chain=strictLoads(canonicalBytes(chain)) as PublicObject[];const prior=await this.read(project);
  if(!prior.a||!prior.b)throw Error('AUTHORIZATION_MIRROR_MISSING');
  const old=prior.b.binding,trust=old.trust;let head=await verifyBootstrap(chain[0],trust.owner_root,trust.recovery_root);for(const next of chain.slice(1))head=await verifyTransition(head,next,trust.recovery_root);
  if(head.operation!=='revoke'||head.opaque_project_id!==old.opaque_project_id)throw Error('REVOKE_REQUIRED');
  const principal_map=old.principal_map.filter(p=>head.members.some((m:PublicObject)=>m.device_id===p.device_id&&m.status==='ACTIVE'));
  const target={...old,principal_map,trust:{...trust,manifest_chain:chain,manifest_head:await digest(head),membership_epoch:head.membership_epoch,key_epoch:head.key_epoch}};
  // Revocation without a new epoch grant stays BLOCKED, even for a surviving device.
  return this.installVerified(target,await digest({revoke:chain}),{ownerRoot:trust.owner_root,recoveryRoot:trust.recovery_root,hooks},true);
 }
 private async installVerified(binding:PublicProjectBinding,installDigest:string,options:InstallOptions,revoked:boolean):Promise<Authorization>{
  const saved=await this.read(binding.semantic_project_id),old=saved.b?.binding;
  if(saved.b&&!saved.a)throw Error('AUTHORIZATION_MIRROR_MISSING');
  if(saved.a&&!saved.b&&saved.a.phase==='INSTALLED')throw Error('BINDING_MISSING');
  if(old){
   if(old.opaque_project_id!==binding.opaque_project_id||old.module_snapshot_hash!==binding.module_snapshot_hash||old.trust.owner_root!==options.ownerRoot||old.trust.recovery_root!==options.recoveryRoot)throw Error('BINDING_IDENTITY_CHANGED');
   if(old.trust.manifest_chain.length>binding.trust.manifest_chain.length)throw Error('ROLLBACK_DETECTED');
   for(let i=0;i<old.trust.manifest_chain.length;i++)if(await digest(old.trust.manifest_chain[i])!==await digest(binding.trust.manifest_chain[i]))throw Error('MEMBERSHIP_FORK');
   for(const p of old.principal_map){const next=binding.principal_map.find(n=>n.device_id===p.device_id);if(next&&await digest(next)!==await digest(p))throw Error('PRINCIPAL_IDENTITY_CHANGED');}
   if(old.trust.manifest_head===binding.trust.manifest_head&&await digest(old)!==await digest(binding))throw Error('BINDING_IDENTITY_CHANGED');
  }
  const mapDigest=await digest(binding.principal_map),token=crypto.randomUUID();
  const pending=await businessTransaction(this.open,['meta'],'readwrite',async tx=>{
   const s=tx.objectStore('meta'),a=await request(s.get('authorization:'+binding.semantic_project_id)) as Authorization|undefined,b=await request(s.get('binding:'+binding.semantic_project_id));
   if(JSON.stringify(a)!==JSON.stringify(saved.a)||JSON.stringify(b)!==JSON.stringify(saved.b))throw Error('AUTHORIZATION_CAS_MISMATCH');
   if(a?.install_digest===installDigest){if(JSON.stringify(a.target)!==JSON.stringify(binding))throw Error('IDENTITY_COLLISION');return a;}
   if(a?.phase==='INSTALLING')throw Error('AUTHORIZATION_TRANSITION_INCOMPLETE');
   const next:Authorization={id:'authorization:'+binding.semantic_project_id,state:'BLOCKED',generation:(a?.generation??0)+1,token,install_digest:installDigest,head:binding.trust.manifest_head,membership_epoch:binding.trust.membership_epoch,key_epoch:binding.trust.key_epoch,principal_map_digest:mapDigest,target:binding,phase:'INSTALLING'};
   await request(s.put(next));return next;
  });
  if(pending.phase==='INSTALLED'){
   const trust=await this.vault.trust(binding.opaque_project_id);if(trust.headDigest!==pending.head)throw Error('VAULT_HEAD_CHANGED');
   if(pending.state==='READY'){requireAuthorization(pending,saved.b);await this.vault.keyInfo(binding.opaque_project_id,binding.trust.key_epoch);}
   return pending;
  }
  await options.hooks?.afterBlocked?.();
  const trust=await this.vault.pin(options.ownerRoot,options.recoveryRoot,binding.trust.manifest_chain);await options.hooks?.afterPin?.();
  if(options.grant)await this.vault.acceptGrant(options.grant);await options.hooks?.afterGrant?.();
  if(!revoked)await this.vault.keyInfo(binding.opaque_project_id,binding.trust.key_epoch);
  await options.beforeReady?.(trust);
  const observed=await this.vault.trust(binding.opaque_project_id);if(observed.headDigest!==pending.head)throw Error('VAULT_HEAD_CHANGED');
  return businessTransaction(this.open,['meta','projects','objects','operations','audit'],'readwrite',async tx=>{
   const s=tx.objectStore('meta'),a=await request(s.get(pending.id));
   if(JSON.stringify(a)!==JSON.stringify(pending))throw Error('AUTHORIZATION_CAS_MISMATCH');
   const record:BindingRecord={id:'binding:'+binding.semantic_project_id,state:revoked?'BLOCKED':'VERIFIED',generation:pending.generation,binding};
   await options.commit?.(tx,record);await request(s.put(record));
   const ready:Authorization={...pending,state:revoked?'BLOCKED':'READY',phase:'INSTALLED',binding_fingerprint:JSON.stringify(record)};await request(s.put(ready));return ready;
  });
 }
}
