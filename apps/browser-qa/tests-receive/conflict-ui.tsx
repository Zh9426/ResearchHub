import React from 'react';
import {createRoot} from 'react-dom/client';
import {ConflictPanel} from '../src/sync/ConflictPanel';
import {BrowserConflicts} from '../src/sync/conflicts';
export async function mountConflictUI(q:any){
 const f=await q.fixture();await(await q.sealer.authorization()).install(f.wrapper,{ownerRoot:f.binding.trust.owner_root,recoveryRoot:f.binding.trust.recovery_root,grant:f.grant});
 const receiver=await q.sealer.receiver(),base=f.transaction('SYNTHETIC UI BASE');await receiver.receive(f.project.id,await f.page([base]));
 const oid=base.changes[0].object_id,parent=await q.digest(base.changes[0]);const local=(await q.commands.snapshot()).objects.find((o:any)=>o.id===oid);await q.commands.save({...local,body:'SYNTHETIC UI local'});const op=(await q.commands.snapshot()).operations.find((o:any)=>o.object_id===oid);await q.adapter.convert(op.id);
 const addRemote=async(content:string)=>{const cursor=await q.meta('relay-cursor:'+f.project.id),tx=f.transaction('SYNTHETIC UI BASE',oid,[parent],[base.transaction_id]);tx.changes[0].payload.content=content;await receiver.receive(f.project.id,await f.page([tx],cursor.cursor,cursor.chain_digest));};
 await addRemote('SYNTHETIC UI remote');const host=document.createElement('div');document.body.append(host);const root=createRoot(host),service=new BrowserConflicts(q.open);
 const render=()=>root.render(<ConflictPanel service={service} project={f.project.id} refreshToken={Math.random()} refresh={async()=>{render();}}/>);render();
 q.conflictUI={oid,addThird:async()=>{await addRemote('SYNTHETIC UI third');render();},unmount:()=>{root.unmount();host.remove();}};
}
