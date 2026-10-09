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
