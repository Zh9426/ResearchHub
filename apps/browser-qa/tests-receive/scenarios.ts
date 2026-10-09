/** TEST_ONLY additional adversarial scenarios, executed inside actual Chromium. */
export async function adversarial(q:any){
 const passed:string[]=[],assert=(v:unknown,message:string)=>{if(!v)throw Error(message);};
 const reject=async(work:()=>Promise<unknown>,code:string)=>{try{await work();}catch(e){if((e as Error).message===code||(e as any).code===code)return;throw e;}throw Error('EXPECTED_REJECTION_'+code);};
 const f=await q.fixture(),installer=await q.sealer.authorization(),receiver=await q.sealer.receiver();
 const options={ownerRoot:f.binding.trust.owner_root,recoveryRoot:f.binding.trust.recovery_root,grant:f.grant};await installer.install(f.wrapper,options);
 const tx=f.transaction('baseline');
 const fix=async(page:any)=>{let chain='0'.repeat(64);for(const row of page.rows){row.envelope_digest=await q.digest(row.envelope);chain=await q.security.extendChain(chain,row.sequence-1,[{sequence:row.sequence,envelope_digest:row.envelope_digest}]);row.chain_digest=chain;}page.chain_digest=chain;};
 const bad=await f.page([tx,f.transaction('AEAD tail')]),env=bad.rows[1].envelope,ct=q.security.b64decode(env.ciphertext);ct[0]^=1;
 env.ciphertext=q.security.b64encode(ct);env.ciphertext_digest=await q.security.sha256(ct);env.signature=q.security.b64encode(await q.security.sign(f.owner.signing.privateKey,q.security.signaturePreimage(env)));await fix(bad);
 await reject(()=>receiver.receive(f.project.id,bad),'DECRYPT_FAILED');assert(!await q.meta('record-kernel:'+f.project.id),'AEAD failure changed kernel');passed.push('native-AEAD-tail-rejected-with-valid-signature');
 const wrong=f.transaction('wrong principal');wrong.actor_id=crypto.randomUUID();wrong.changes[0].actor_id=wrong.actor_id;
 await reject(async()=>receiver.receive(f.project.id,await f.page([wrong])),'ACTOR_CONTEXT_MISMATCH');passed.push('signed-principal-mismatch');
 const old=await f.page([tx]);old.rows[0].envelope.membership_epoch=1;old.rows[0].envelope.signature=q.security.b64encode(await q.security.sign(f.owner.signing.privateKey,q.security.signaturePreimage(old.rows[0].envelope)));await fix(old);
 await reject(()=>receiver.receive(f.project.id,old),'HISTORICAL_OR_UNKNOWN_EPOCH_BLOCKED');passed.push('historical-epoch-no-cursor-skip');
 const missing=f.transaction('missing parent',crypto.randomUUID(),['a'.repeat(64)]);
 await reject(async()=>receiver.receive(f.project.id,await f.page([tx,missing])),'DEPENDENCY_REQUIRED');assert(!await q.meta('relay-cursor:'+f.project.id),'kernel tail error advanced cursor');passed.push('kernel-tail-error-whole-page-rollback');
 const good=await f.page([tx]);await receiver.receive(f.project.id,good);await receiver.receive(f.project.id,await f.page([tx],1,good.chain_digest));
 assert((await q.meta('record-kernel:'+f.project.id)).state.sequence===1&&(await q.meta('relay-cursor:'+f.project.id)).cursor===2,'kernel and Relay sequence must be independent');passed.push('echo-kernel-sequence-independent-of-relay-cursor');
 const object=(await q.commands.snapshot()).objects.find((o:any)=>o.id===tx.changes[0].object_id);const local=await q.commands.save({...object,body:'local branch'}),op=(await q.commands.snapshot()).operations.find((o:any)=>o.object_id===local.id);
 const mapping=await q.adapter.convert(op.id);await q.sealer.seal(op.id);const sealed=await q.sealer.ready(op.id);
 assert(await receiver.completeHandoff(op.id,mapping.transaction_id,local.local_edit_version),'exact handoff');
 const cursor=await q.meta('relay-cursor:'+f.project.id),remote=f.transaction('new trusted remote',object.id,[mapping.revision],[mapping.transaction_id]);await receiver.receive(f.project.id,await f.page([remote],2,cursor.chain_digest));
 assert((await q.commands.snapshot()).objects.find((o:any)=>o.id===object.id).body==='new trusted remote','completed work must follow trusted remote');
 assert(q.security.equal(sealed,await q.sealer.ready(op.id)),'sealed exact bytes after remote pull');assert((await q.adapter.convert(op.id)).transaction_digest===mapping.transaction_digest,'converted retry after later pull');passed.push('clean-handoff-follows-remote-and-sealed-exact-retry');
 const current=await q.meta('relay-cursor:'+f.project.id),race=await f.page([f.transaction('receiver raced')],3,current.chain_digest);
 await reject(()=>receiver.receive(f.project.id,race,{beforeCommit:async()=>{
  const saved=await q.commands.save({id:crypto.randomUUID(),project_id:f.project.id,kind:'Note',title:'parallel local',body:'parallel local',local_format_version:1,local_edit_version:0});const op=(await q.commands.snapshot()).operations.find((o:any)=>o.object_id===saved.id);await q.adapter.convert(op.id);
 }}),'RECEIVE_CAS_MISMATCH');assert((await q.meta('relay-cursor:'+f.project.id)).cursor===3,'kernel CAS advanced cursor');passed.push('concurrent-conversion-kernel-generation-cas');
 const bound=await q.meta('binding:'+f.project.id),before=await q.commands.snapshot();const db=await q.open();await new Promise<void>((ok,no)=>{const t=db.transaction('meta','readwrite');t.objectStore('meta').delete('authorization:'+f.project.id);t.oncomplete=()=>ok();t.onabort=()=>no(t.error);});db.close();
 await reject(()=>installer.install(f.wrapper,options),'AUTHORIZATION_MIRROR_MISSING');assert(JSON.stringify(bound)===JSON.stringify(await q.meta(bound.id))&&JSON.stringify(before)===JSON.stringify(await q.commands.snapshot()),'missing mirror must not repair binding or erase work');passed.push('missing-business-mirror-fails-closed');
 const g=await q.fixture();await installer.install(g.wrapper,{ownerRoot:g.binding.trust.owner_root,recoveryRoot:g.binding.trust.recovery_root,grant:g.grant});const base=g.transaction('handoff base');await receiver.receive(g.project.id,await g.page([base]));
 let work=(await q.commands.snapshot()).objects.find((o:any)=>o.id===base.changes[0].object_id);work=await q.commands.save({...work,body:'C before handoff'});let operation=(await q.commands.snapshot()).operations.find((o:any)=>o.object_id===work.id),mapped=await q.adapter.convert(operation.id);await receiver.completeHandoff(operation.id,mapped.transaction_id,work.local_edit_version);
 work=(await q.commands.snapshot()).objects.find((o:any)=>o.id===work.id);work=await q.commands.save({...work,body:'D after handoff'});operation=(await q.commands.snapshot()).operations.filter((o:any)=>o.object_id===work.id).sort((a:any,b:any)=>b.payload.local_edit_version-a.payload.local_edit_version)[0];const afterHandoff=await q.adapter.convert(operation.id);
 assert(afterHandoff.parents[0]===mapped.revision,'editing a completed local projection must parent its exact revision');passed.push('post-handoff-edit-freezes-current-projection');
 return passed;
}
