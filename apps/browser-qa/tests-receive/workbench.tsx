import {revision} from '../../../packages/sync-protocol/src/browser';
/** TEST_ONLY ordinary Workbench component with a persisted remote-only PC snapshot. */
import React from 'react';
import {createRoot} from 'react-dom/client';
import {Workbench} from '../src/Workbench';
import {newDraft} from '../src/local/model';
export async function remoteOnlyWorkbench(q:any){
 const f=await q.fixture(),object={...newDraft(f.project,'Run'),title:'SYNTHETIC remote-only Run',observation:'SYNTHETIC received observation',is_highlighted:true};
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 const snapshot={identity:(await q.commands.snapshot()).identity,projects:[f.project],objects:[object],operations:[],audit:[],drafts:[]};
 const adapter:any={pc:true,sync:true,synchronize:async()=>{snapshot.objects=[];return {sent:0,received:1,confirmed:0,has_more:false,peer:'UNCONFIRMED',review:'NOT_REQUESTED'};},initialize:async()=>{},commands:{snapshot:async()=>snapshot,notifications:null}};
 history.replaceState(null,'',`/projects/${f.project.route_alias}/records/${object.id}`);
 try{root.render(<Workbench adapter={adapter}/>);
  for(let i=0;i<100&&!host.querySelector('.qa-record');i++)await new Promise(ok=>setTimeout(ok,10));
  (host.querySelector('.qa-record') as HTMLButtonElement).click();
  await new Promise(ok=>setTimeout(ok,25));
  const labels=[...host.querySelectorAll('label')];
  if(!labels.some(x=>x.textContent?.startsWith('观察')&&(x.querySelector('textarea') as HTMLTextAreaElement)?.value===object.observation))throw Error('REMOTE_ONLY_RUN_OBSERVATION_HIDDEN');
  if(![...host.querySelectorAll('button')].some(x=>x.textContent==='取消星标'))throw Error('REMOTE_ONLY_RUN_HIGHLIGHT_HIDDEN');
  const observation=labels.find(x=>x.textContent?.startsWith('观察'))!.querySelector('textarea')!;
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(observation,'SYNTHETIC dirty input');observation.dispatchEvent(new Event('input',{bubbles:true}));
  await new Promise(ok=>setTimeout(ok,25));
  ([...host.querySelectorAll('button')].find(x=>x.textContent==='立即同步') as HTMLButtonElement).click();
  await new Promise(ok=>setTimeout(ok,50));
  if(![...host.querySelectorAll('textarea')].some(x=>x.value==='SYNTHETIC dirty input'))throw Error('DIRTY_OBSERVATION_HIDDEN_AFTER_PROJECTION_REMOVED');
  return ['ordinary-dirty-editor-visible-after-projection-removed','ordinary-pc-remote-only-run-fields-version-zero'];
 }finally{root.unmount();host.remove();history.replaceState(null,'','/');}
}

/** Actual native verified same-page Run create/update and ordinary B editor read. */
export async function receivedRunWorkbench(q:any){
 const f=await q.fixture();await (await q.sealer.authorization()).install(f.wrapper,{ownerRoot:f.binding.trust.owner_root,recoveryRoot:f.binding.trust.recovery_root,grant:f.grant});
 const first=f.transaction('SYNTHETIC C manual Run');first.changes[0].object_type='ResearchRun';first.changes[0].payload={title:'SYNTHETIC C manual Run',run_type:'simulation',observation:''};
 const second=f.transaction('unused',first.changes[0].object_id,[await revision(first.changes[0])],[first.transaction_id]);second.changes[0].object_type='ResearchRun';second.changes[0].payload={observation:'SYNTHETIC PC baseline second save'};
 const note=f.transaction('SYNTHETIC C manual Note');await (await q.sealer.receiver()).receive(f.project.id,await f.page([first,second,note]));
 const snapshot=await q.commands.snapshot(),object=snapshot.objects.find((o:any)=>o.id===first.changes[0].object_id);
 if(object?.observation!=='SYNTHETIC PC baseline second save')throw Error('RECEIVED_RUN_DURABLE_OBSERVATION_MISMATCH');
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 history.replaceState(null,'',`/projects/${f.project.route_alias}`);
 const adapter:any={sync:true,initialize:async()=>{},commands:q.commands};
 try{root.render(<Workbench adapter={adapter}/>);for(let i=0;i<100&&!host.querySelector('.qa-record');i++)await new Promise(ok=>setTimeout(ok,10));
  const button=[...host.querySelectorAll('button.qa-record')].find(x=>x.textContent?.includes('SYNTHETIC C manual Run')) as HTMLButtonElement;button.click();await new Promise(ok=>setTimeout(ok,25));
  const field=[...host.querySelectorAll('label')].find(x=>x.textContent?.startsWith('观察'))?.querySelector('textarea');
  if(field?.value!=='SYNTHETIC PC baseline second save')throw Error('RECEIVED_RUN_EDITOR_OBSERVATION_MISMATCH');
  return ['native-same-page-run-create-update-ordinary-editor'];
 }finally{root.unmount();host.remove();history.replaceState(null,'','/');}
}
