/** TEST_ONLY: typed Kernel identities that the current oid-keyed local DTO cannot represent. */
export async function identityCollisions(q:any){
 const failures:string[]=[],passed:string[]=[],installer=await q.sealer.authorization(),receiver=await q.sealer.receiver();
 const setup=async()=>{const f=await q.fixture();await installer.install(f.wrapper,{ownerRoot:f.binding.trust.owner_root,recoveryRoot:f.binding.trust.recovery_root,grant:f.grant});return f;};
 const state=async()=>{const db=await q.open();try{return await new Promise<string>((ok,no)=>{const t=db.transaction(['meta','objects','operations','audit'],'readonly'),out:any={};for(const name of ['meta','objects','operations','audit']){const r=t.objectStore(name).getAll();r.onsuccess=()=>out[name]=r.result;}t.oncomplete=()=>ok(JSON.stringify(out));t.onabort=()=>no(t.error);});}finally{db.close();}};
 const blocked=async(name:string,code:string,work:()=>Promise<unknown>)=>{const before=await state();let actual='ACCEPTED';try{await work();}catch(e){actual=(e as Error).message;}const unchanged=before===await state();if(actual!==code||!unchanged)failures.push(name+': '+actual+(unchanged?'':' / durable state changed'));else passed.push(name);};
 const run=(f:any,oid:string)=>{const tx=f.transaction('same UUID Run',oid);tx.changes[0].object_type='ResearchRun';tx.changes[0].payload={title:'same UUID Run',run_type:f.project.module_snapshot.run_types[0].id};return tx;};
 {
  const f=await setup(),note=f.transaction('same UUID Note'),page=await f.page([note,run(f,note.changes[0].object_id)]);
  await blocked('same-page-typed-uuid-collision-atomic-block','LOCAL_IDENTITY_UNREPRESENTABLE',()=>receiver.receive(f.project.id,page));
 }
 {
  const f=await setup(),note=f.transaction('first-page Note'),first=await f.page([note]);await receiver.receive(f.project.id,first);
  const second=await f.page([run(f,note.changes[0].object_id)],1,first.chain_digest);
  await blocked('cross-page-typed-uuid-collision-atomic-block','LOCAL_IDENTITY_UNREPRESENTABLE',()=>receiver.receive(f.project.id,second));
 }
 for(const mode of ['kind-clean','kind-pending','project-clean','project-pending']){
  const f=await setup(),remote=f.transaction('remote collides with local'),oid=remote.changes[0].object_id,foreign=mode.startsWith('project')?await setup():f;
  const kind=mode.startsWith('kind')?'Run':'Note',object=kind==='Note'?{id:oid,project_id:foreign.project.id,kind,title:'existing local',body:'keep me',local_format_version:1,local_edit_version:0}:{id:oid,project_id:f.project.id,kind,title:'existing local',run_type:f.project.module_snapshot.run_types[0].id,objective:'',observation:'keep me',status:'planned',scientific_outcome:'unknown',is_highlighted:false,highlight_type:'',highlight_note:'',context_data:{},local_format_version:1,local_edit_version:0};
  await q.commands.save(object);
  if(mode.endsWith('clean')){const db=await q.open();await new Promise<void>((ok,no)=>{const t=db.transaction('meta','readwrite');t.objectStore('meta').delete('pending-operation:'+oid);t.oncomplete=()=>ok();t.onabort=()=>no(t.error);});db.close();}
  const page=await f.page([remote]);await blocked('existing-local-'+mode+'-atomic-block','LOCAL_OBJECT_SCOPE_COLLISION',()=>receiver.receive(f.project.id,page));
 }
 {
  const f=await setup(),saved=await q.commands.save({id:crypto.randomUUID(),project_id:f.project.id,kind:'Note',title:'handoff',body:'keep pending',local_format_version:1,local_edit_version:0}),op=(await q.commands.snapshot()).operations.find((o:any)=>o.object_id===saved.id),mapping=await q.adapter.convert(op.id);
  const db=await q.open();await new Promise<void>((ok,no)=>{const t=db.transaction('objects','readwrite');t.objectStore('objects').put({...saved,project_id:crypto.randomUUID()});t.oncomplete=()=>ok();t.onabort=()=>no(t.error);});db.close();
  await blocked('handoff-local-scope-collision-retains-pending','LOCAL_OBJECT_SCOPE_COLLISION',()=>receiver.completeHandoff(op.id,mapping.transaction_id,saved.local_edit_version));
 }
 if(failures.length)throw Error('IDENTITY_GUARD_FAILURES: '+failures.join('; '));return passed;
}
