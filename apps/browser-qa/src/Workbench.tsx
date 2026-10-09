import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Panel,Empty,human} from '../../web/src/components/presentational';
import {localCommands,LocalConflictError} from './local/commands';
import {initializeSyntheticWorkspace} from './local/seeds';
import {newDraft,RUN_STATUSES,OUTCOMES,type LocalObject,type LocalSnapshot} from './local/model';
import {testOnlyDisconnectedAdapter} from './local/testTransport';
export type WorkbenchExtensionContext={snapshot:LocalSnapshot;draft:LocalObject|null;dirty:boolean;busy:boolean;refresh:()=>Promise<void>;openRescueDraft:(draft:LocalObject)=>void};
export type WorkbenchAdapter={commands:Pick<typeof localCommands,'snapshot'|'save'|'setHighlight'|'notifications'|'injectNextAbort'>;initialize:()=>Promise<void>;sync?:boolean};
const defaultAdapter:WorkbenchAdapter={commands:localCommands,initialize:initializeSyntheticWorkspace};
type SaveState='editing'|'saving'|'saved'|'save_failed';
declare global {interface Window {__LOCAL_QA__?:{snapshot:typeof localCommands.snapshot;currentDraft:()=>LocalObject|null;injectNextAbort:()=>void;testOnlyTransportProbe:()=>Promise<never>}}}
export function Workbench({extension,adapter=defaultAdapter}:{extension?:(context:WorkbenchExtensionContext)=>ReactNode;adapter?:WorkbenchAdapter}){
 const localCommands=adapter.commands;
 const [data,setData]=useState<LocalSnapshot|null>(null),[alias,setAlias]=useState(location.pathname.split('/')[2]||'generic');
 const [draft,setDraft]=useState<LocalObject|null>(null),[dirty,setDirty]=useState(false),[saveState,setSaveState]=useState<SaveState>('editing');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[conflict,setConflict]=useState(false),[comparison,setComparison]=useState<LocalObject|null>(null),[onlyStars,setOnlyStars]=useState(false);
 const draftRef=useRef(draft),dirtyRef=useRef(dirty);draftRef.current=draft;dirtyRef.current=dirty;
 const busy=saveState==='saving';
 async function refresh(){setData(await localCommands.snapshot());}
 useEffect(()=>{
  let active=true;
  void localCommands.snapshot().then(snapshot=>{if(!active)return;setData(snapshot);const id=location.pathname.split('/')[4];const found=snapshot.objects.find(x=>x.id===id);if(found){setDraft(found);setSaveState('saved');}}).catch(e=>{if(active)setError(String(e));});
  const api={snapshot:localCommands.snapshot,currentDraft:()=>structuredClone(draftRef.current),injectNextAbort:()=>localCommands.injectNextAbort(),testOnlyTransportProbe:()=>testOnlyDisconnectedAdapter.send()};window.__LOCAL_QA__=api;
  const change=()=>{setNotice('其他标签页有本地更新；当前编辑内容保持不变。');void refresh().catch(e=>setError(String(e)));};
  localCommands.notifications?.addEventListener('message',change);
  const unload=(e:BeforeUnloadEvent)=>{if(dirtyRef.current){e.preventDefault();e.returnValue='';}};
  const link=(e:MouseEvent)=>{if((e.target as Element).closest('a[href]')&&dirtyRef.current&&!confirm('本次修改尚未保存，确定离开？')){e.preventDefault();e.stopPropagation();}};
  window.addEventListener('beforeunload',unload);document.addEventListener('click',link,true);
  return()=>{active=false;localCommands.notifications?.removeEventListener('message',change);window.removeEventListener('beforeunload',unload);document.removeEventListener('click',link,true);delete window.__LOCAL_QA__;};
 },[]);
 const project=data?.projects.find(p=>p.route_alias===alias);
 function canLeave(){return !dirty||confirm('本次修改尚未保存，确定放弃当前编辑？');}
 // Full-document links retain native beforeunload protection. Local selections
 // replace the current URL, avoiding same-document back entries without a router.
 function choose(next:LocalObject|null,nextAlias=alias){if(busy||!canLeave())return;setDraft(next);setAlias(nextAlias);setDirty(false);setError('');setConflict(false);setComparison(null);setSaveState(next?'saved':'editing');history.replaceState(null,'',`/projects/${nextAlias}${next?`/${next.kind==='Run'?'runs':'notes'}/${next.id}`:''}`);}
 function create(kind:LocalObject['kind']){if(!project||busy||!canLeave())return;setDraft(newDraft(project,kind));setDirty(true);setSaveState('editing');setError('');setConflict(false);setComparison(null);}
 function edit(patch:Partial<LocalObject>){if(!draft||busy)return;setDraft({...draft,...patch} as LocalObject);setDirty(true);setSaveState('editing');}
 async function save(asCopy=false){
  if(!draft||busy)return;setSaveState('saving');setError('');let saved:LocalObject;
  try{const input=asCopy?{...draft,id:crypto.randomUUID(),local_edit_version:0}:draft;saved=await localCommands.save(input);}
  catch(e){setSaveState('save_failed');setDirty(true);setConflict(e instanceof LocalConflictError);setError(`${String(e)}；本次修改尚未保存，输入已保留。`);return;}
  setDraft(saved);setDirty(false);setSaveState('saved');setConflict(false);setComparison(null);
  history.replaceState(null,'',`/projects/${alias}/${saved.kind==='Run'?'runs':'notes'}/${saved.id}`);
  try{await refresh();}catch(e){setError(`记录已提交到本机，但列表刷新失败，请重新读取：${String(e)}`);}
 }
 async function highlight(){
  if(!draft||draft.kind!=='Run'||busy)return;
  const original=draft;setError('');setSaveState('saving');
  try{const saved=await localCommands.setHighlight(draft.id,draft.local_edit_version,{is_highlighted:!draft.is_highlighted,highlight_type:draft.highlight_type,highlight_note:draft.highlight_note});
   if(saved.kind!=='Run')throw Error('Run type mismatch');
   setDraft({...original,local_edit_version:saved.local_edit_version,is_highlighted:saved.is_highlighted,highlight_type:saved.highlight_type,highlight_note:saved.highlight_note});setSaveState(dirty?'editing':'saved');setNotice('星标已保存到本机；正文编辑保持。');await refresh();
  }catch(e){setSaveState('save_failed');setError(String(e));}
 }
 async function initialize(){setSaveState('saving');setError('');try{await adapter.initialize();await refresh();setSaveState('editing');}catch(e){setError(String(e));setSaveState('save_failed');}}
 function openRescueDraft(savedDraft:LocalObject){if(busy||!canLeave())return;const p=data?.projects.find(x=>x.id===savedDraft.project_id);if(!p)return;setAlias(p.route_alias);setDraft({...structuredClone(savedDraft),id:crypto.randomUUID(),local_edit_version:0});setDirty(true);setSaveState('editing');setError('');setConflict(false);setComparison(null);history.replaceState(null,'',`/projects/${p.route_alias}`);}
 return <>
 {error&&<p role="alert" className="error qa-content">{error}</p>}
 {!data?<Panel title="本地工作区"><p className="qa-content">读取本地数据… <button onClick={()=>void refresh().catch(e=>setError(String(e)))}>重试读取</button></p></Panel>:!data.identity?<Panel title="空 QA 工作区"><div className="qa-content"><p>仅首次点击时写入三个 SYNTHETIC 项目及冻结模块快照。记录以明文保存在此隔离浏览器中。</p><button className="primary" disabled={busy} onClick={initialize}>初始化合成工作区</button></div></Panel>:<>
 <Panel title="合成项目"><div className="qa-content qa-toolbar"><label>项目选择<select value={alias} disabled={busy} onChange={e=>choose(null,e.target.value)}>{data.projects.map(p=><option key={p.id} value={p.route_alias}>{p.title}</option>)}</select></label><button disabled={busy} onClick={()=>create('Run')}>新建 Run</button><button disabled={busy} onClick={()=>create('Note')}>新建 Note</button></div><p className="muted qa-content">模块 {project?.module_id} · {project?.module_version} · 本地版本不等于科研 revision</p></Panel>
 <div className="qa-work-grid"><Panel title="记录列表"><div className="qa-content"><label className="qa-check"><input type="checkbox" checked={onlyStars} onChange={e=>setOnlyStars(e.target.checked)}/>仅看星标</label>{data.objects.filter(o=>o.project_id===project?.id&&(!onlyStars||o.kind==='Run'&&o.is_highlighted)).map(o=><button className="qa-record" disabled={busy} key={o.id} onClick={()=>choose(o)}><span>{o.kind==='Run'&&o.is_highlighted?'★ ':''}{o.title}</span><small>{o.kind} · 本地 v{o.local_edit_version}</small></button>)}{!data.objects.some(o=>o.project_id===project?.id)&&<Empty>还没有本地记录。</Empty>}</div></Panel>
 <Panel title={draft?`${draft.kind} · ${draft.local_edit_version?'记录详情':'新建记录'}`:'记录详情'}>{draft?<div className="qa-content qa-editor">
 <p data-testid="local-save" role="status">{saveState==='saving'?'正在保存…':saveState==='saved'?'已保存到本机':saveState==='save_failed'?'本次修改未保存':'编辑中 · 尚未保存'}</p>
 <fieldset disabled={busy}><label>标题<input value={draft.title} maxLength={500} onChange={e=>edit({title:e.target.value})}/></label>
 {draft.kind==='Run'?<><label>记录类型<select value={draft.run_type} onChange={e=>edit({run_type:e.target.value})}>{project?.module_snapshot.run_types.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>本次目标（可选）<textarea value={draft.objective} onChange={e=>edit({objective:e.target.value})}/></label>{draft.local_edit_version>0&&<>
 <label>观察<textarea rows={5} value={draft.observation} onChange={e=>edit({observation:e.target.value})}/></label><div className="qa-toolbar"><label>运行状态<select value={draft.status} onChange={e=>edit({status:e.target.value as typeof draft.status})}>{RUN_STATUSES.map(v=><option key={v} value={v}>{human(v)}</option>)}</select></label><label>科研结果<select value={draft.scientific_outcome} onChange={e=>edit({scientific_outcome:e.target.value as typeof draft.scientific_outcome})}>{OUTCOMES.map(v=><option key={v} value={v}>{human(v)}</option>)}</select></label></div>
 <button type="button" aria-pressed={draft.is_highlighted} onClick={()=>adapter.sync?void highlight():edit({is_highlighted:!draft.is_highlighted})}>{draft.is_highlighted?'取消星标':'设为星标'}</button><p className="muted">星标独立于运行状态和科研结果；失败或阴性结果也可标记。</p>
 {draft.is_highlighted&&<><label>星标类型（可选）<input value={draft.highlight_type} onChange={e=>edit({highlight_type:e.target.value})}/></label><label>星标说明（可选）<textarea value={draft.highlight_note} onChange={e=>edit({highlight_note:e.target.value})}/></label></>}
 <details><summary>高级语境（可选）</summary>{(alias==='hdsp'?[['repository','代码仓库'],['config','仿真配置说明']]:alias==='ice'?[['experiment_conditions','实验条件说明'],['unexpected_events','异常观察']]:[['context','补充语境']]).map(([key,label])=><label key={key}>{label}<textarea value={draft.context_data[key]??''} onChange={e=>edit({context_data:{...draft.context_data,[key]:e.target.value}})}/></label>)}</details>
 </>}</>:<label>笔记正文<textarea rows={8} value={draft.body} onChange={e=>edit({body:e.target.value})}/></label>}
 </fieldset><button className="primary" disabled={busy} onClick={()=>void save()}>保存到本机</button>
 {conflict&&<div><p>审核状态：conflict（本地编辑冲突，未请求科研批准）</p><button onClick={async()=>{try{const snapshot=await localCommands.snapshot();setComparison(snapshot.objects.find(o=>o.id===draft.id)??null);}catch(e){setError(String(e));}}}>比较当前记录</button><button onClick={()=>void save(true)}>另存草稿</button>{comparison&&<pre data-testid="comparison">{JSON.stringify(comparison,null,2)}</pre>}</div>}
 </div>:<Empty>选择记录，或创建一条 Run / Note。</Empty>}</Panel></div>
 <Panel title="本地队列与状态"><div className="qa-content">{adapter.sync?<><p data-testid="transport">已保存到本机，尚未连接传输服务；对端接收未确认。</p><p>待处理操作 {data.operations.length} 条 · 本地历史 {data.audit.length} 条</p><p>尚未请求科研批准。</p></>:<><p data-testid="transport">transport：not_configured · 待同步：本轮尚未连接传输服务</p><p>review：{conflict?'conflict':'not_requested'} · 未请求科研批准</p><p>待处理操作 {data.operations.length} 条 · 本地历史 {data.audit.length} 条 · NEEDS_WIRE_ADAPTER</p><p className="muted">本地操作保留完整内容，尚不是可发送的 SyncTransaction。明文合成数据，不含真实设备授权。</p></>}{notice&&<p role="status">{notice}</p>}</div></Panel>
 </>}
 {data&&extension?.({snapshot:data,draft,dirty,busy,refresh,openRescueDraft})}
 </>;
}
