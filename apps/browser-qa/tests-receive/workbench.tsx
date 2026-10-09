import {QaShell} from '../src/QaShell';
import {JoinPanel} from '../src/sync/JoinPanel';
import {BindingPanel} from '../src/sync/BindingPanel';
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
 const first=f.transaction('SYNTHETIC C manual Run');first.changes[0].object_type='ResearchRun';first.changes[0].payload={title:'SYNTHETIC C manual Run',run_type:'simulation',observation:'',objective:'  SYNTHETIC 中文目标  ',is_highlighted:true,highlight_note:'  SYNTHETIC 中文星标说明  ',context_data:{repository:'  SYNTHETIC 中文代码仓库  '}};
 const second=f.transaction('unused',first.changes[0].object_id,[await revision(first.changes[0])],[first.transaction_id]);second.changes[0].object_type='ResearchRun';second.changes[0].payload={observation:'SYNTHETIC PC baseline second save'};
 const note=f.transaction('SYNTHETIC C manual Note');await (await q.sealer.receiver()).receive(f.project.id,await f.page([first,second,note]));
 const snapshot=await q.commands.snapshot(),object=snapshot.objects.find((o:any)=>o.id===first.changes[0].object_id);
 if(object?.observation!=='SYNTHETIC PC baseline second save')throw Error('RECEIVED_RUN_DURABLE_OBSERVATION_MISMATCH');
 const older=snapshot.projects.find((p:any)=>p.id!==f.project.id&&p.route_alias===f.project.route_alias);
 if(!older)throw Error('OLDER_SAME_ALIAS_FIXTURE_REQUIRED');
 q.receivedWorkbenchProject=f.project.id;
 const cases:string[]=[];
 for(const olderFirst of [true,false]){
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  history.replaceState(null,'',`/projects/${f.project.route_alias}`);
  // Real fixture rows, deterministically permuted before this component's scope filter.
  const commands=Object.create(q.commands);commands.snapshot=async()=>{
   const current=await q.commands.snapshot(),pair=olderFirst?[older,f.project]:[f.project,older];
   const ordered=[...pair,...current.projects.filter((p:any)=>p.id!==older.id&&p.id!==f.project.id)];
   return {...current,projects:ordered.filter((p:any)=>p.id===f.project.id),objects:current.objects.filter((o:any)=>o.project_id===f.project.id)};
  };
  const adapter:any={sync:true,initialize:async()=>{},commands};
  try{root.render(<Workbench adapter={adapter}/>);for(let i=0;i<100&&!host.querySelector('.qa-record');i++)await new Promise(ok=>setTimeout(ok,10));
   const button=[...host.querySelectorAll('button.qa-record')].find(x=>x.textContent?.includes('SYNTHETIC C manual Run')) as HTMLButtonElement|undefined;
   if(!button)throw Error('RECEIVED_RUN_BUTTON_MISSING');button.click();await new Promise(ok=>setTimeout(ok,25));
   const field=[...host.querySelectorAll('label')].find(x=>x.textContent?.startsWith('观察'))?.querySelector('textarea');
   if(field?.value!=='SYNTHETIC PC baseline second save')throw Error('RECEIVED_RUN_EDITOR_OBSERVATION_MISMATCH');
   cases.push(olderFirst?'native-same-page-run-create-update-ordinary-editor':'native-same-page-run-editor-new-project-first');
  }finally{root.unmount();host.remove();history.replaceState(null,'','/');}
 }
 return cases;
}

/** Mount the actual B shell and panels for external Playwright exact-label checks. */
export async function mountAccessibleWorkbench(q:any,pc=false){
 const current=await q.commands.snapshot(),project=current.projects.find((p:any)=>p.id===q.receivedWorkbenchProject);
 if(!project)throw Error('NATIVE_RECEIVED_PROJECT_REQUIRED');
 const snapshot={...current,projects:[project],objects:current.objects.filter((o:any)=>o.project_id===project.id)};
 const commands=Object.create(q.commands);commands.snapshot=async()=>snapshot;
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 history.replaceState(null,'',`/projects/${project.route_alias}`);
 q.unmountAccessibleWorkbench=()=>{root.unmount();host.remove();history.replaceState(null,'','/');};
 root.render(<QaShell sync pc={pc}><Workbench adapter={{sync:true,pc,initialize:async()=>{},commands}} extension={({refresh,snapshot})=><><JoinPanel refresh={refresh}/><BindingPanel refreshToken={snapshot}/></>}/></QaShell>);
}
