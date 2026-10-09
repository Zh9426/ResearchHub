/** Conservative v2 Run/Note kernel. No IO, Node imports, transport or UI authority. */
import {canonicalBytes} from './canonical-core.ts';
import {digest} from './browser.ts';
import {validateTransaction,validateChange,ProtocolError,type ChangeSet,type SyncTransaction} from './protocol-core.ts';
type Document=Record<string,unknown>;
type Revision={semantic:ChangeSet;document:Document;lifecycle:string};
type Receipt={transaction_id:string;digest:string;state:string;receipt_state:string;sequence:number};
type Conflict={heads:string[];base:string|null;status:string;candidates:string[];resolution:string|null};
type Audit={transaction_id:string;action:string;content:Document};
export type RecordState={project_id:string;module_hash:string;sequence:number;watermark:number;transactions:Record<string,{raw:SyncTransaction;digest:string;state:string;receipt:Receipt}>;revisions:Record<string,Revision>;heads:Record<string,string[]>;dependencies:Record<string,string[]>;projections:Record<string,string>;conflicts:Conflict[];audits:Audit[]};
export type RecordContext={project_id:string;module:Document;module_hash:string;mode:'online'|'offline_proposal';principal:{principal_id:string;project_id:string;device_id:string;actor_id:string;actor_type:string;active:boolean}};
export function emptyRecordState(project_id:string,module_hash:string):RecordState{return {project_id,module_hash,sequence:0,watermark:0,transactions:{},revisions:{},heads:{},dependencies:{},projections:{},conflicts:[],audits:[]};}
const fail=(code:string):never=>{throw new ProtocolError(code,code);};
const key=(c:ChangeSet)=>c.object_type+':'+c.object_id;
const equal=(a:unknown,b:unknown)=>new TextDecoder().decode(canonicalBytes(a))===new TextDecoder().decode(canonicalBytes(b));
function ancestry(graph:Record<string,string[]>,roots:string[]):Set<string>{
 const found=new Set<string>(),pending=[...roots];
 while(pending.length){const id=pending.pop()!;if(found.has(id))continue;found.add(id);pending.push(...(graph[id]??[]));}
 return found;
}
export function commonBase(graph:Record<string,string[]>,heads:string[]):string|null{
 if(!heads.length)return null;
 const lineages=heads.map(h=>ancestry(graph,[h]));const common=[...lineages[0]].filter(id=>lineages.every(a=>a.has(id)));
 const below=new Set(common.flatMap(id=>graph[id]??[]));const maxima=common.filter(id=>!below.has(id));
 return maxima.length===1?maxima[0]:null;
}
function materialize(c:ChangeSet,parents:Revision[]):Revision{
 let document:Document={},lifecycle='active';
 if(parents.length===1){document={...parents[0].document};lifecycle=parents[0].lifecycle;}
 else if(parents.length>1){
  for(const field of new Set(parents.flatMap(p=>Object.keys(p.document)))){
   if(parents.every(p=>Object.hasOwn(p.document,field))&&parents.every(p=>equal(p.document[field],parents[0].document[field])))document[field]=parents[0].document[field];
   else if(!Object.hasOwn(c.payload,field))fail('REVIEW_INCOMPLETE');
  }
  lifecycle=parents.some(p=>p.lifecycle==='trashed')?'trashed':parents.some(p=>p.lifecycle==='archived')?'archived':'active';
 }
 Object.assign(document,c.payload);
 validateChange({...c,payload:document});
 if(['trash','archive','restore'].includes(c.operation))lifecycle={trash:'trashed',archive:'archived',restore:'active'}[c.operation]!;
 return {semantic:c,document,lifecycle};
}
function isProtected(c:ChangeSet,document:Document){return c.object_type==='ResearchRun'&&Boolean(document.human_conclusion);}
/** Never mutates input: an exception leaves the entire transaction unstaged. */
export async function applyRecord(source:RecordState,value:unknown,trusted:RecordContext):Promise<{snapshot:RecordState;receipt:Receipt}>{
 const input=structuredClone(source),context=structuredClone(trusted);
 const tx=validateTransaction(structuredClone(value));const p=context.principal;
 if(!input.project_id||input.project_id!==context.project_id||tx.project_id!==input.project_id)fail('PROJECT_REQUIRED');
 if(!input.module_hash||context.module_hash!==input.module_hash||await digest(context.module)!==input.module_hash)fail('MODULE_FROZEN');
 if(!['online','offline_proposal'].includes(context.mode))fail('INVALID_CONTEXT');
 if(!p||!p.active)fail('PRINCIPAL_REVOKED');
 if(['project_id','device_id','actor_id','actor_type'].some(field=>tx[field]!==p[field as keyof typeof p]))fail('ACTOR_CONTEXT_MISMATCH');
 if(tx.project_id!==context.project_id)fail('PROJECT_REQUIRED');
 const checksum=await digest(tx),previous=input.transactions[tx.transaction_id];
 if(previous){
  if(previous.digest!==checksum||!equal(previous.raw,tx))fail('IDENTITY_COLLISION');
  return {snapshot:structuredClone(input),receipt:{...previous.receipt,state:previous.state}};
 }
 if(tx.protocol_version!==2||tx.schema_version!==2)fail('RECORD_SCOPE_REQUIRED');
 if(await digest(context.module)!==context.module_hash||tx.changes.some(c=>c.module_snapshot_hash!==context.module_hash))fail('MODULE_FROZEN');
 const resolving=tx.changes.some(c=>c.operation==='resolve');
 if(resolving&&!tx.changes.every(c=>c.operation==='resolve'))fail('RECORD_SCOPE_REQUIRED');
 const state=structuredClone(input),items:{c:ChangeSet;rev:string;row:Revision}[]=[],dependencies=new Set(tx.dependencies);
 for(const c of tx.changes){
  if(!['ResearchRun','Note'].includes(c.object_type))fail('RECORD_SCOPE_REQUIRED');
  const hs=state.heads[key(c)]??[];
  if(resolving&&!equal(c.parents,hs))fail('CONFLICT_CHANGED');
  const parents=c.parents.map(id=>state.revisions[id]??fail('DEPENDENCY_REQUIRED'));
  if(parents.some(r=>r.semantic.project_id!==c.project_id||key(r.semantic)!==key(c)))fail('CROSS_OBJECT_PARENT');
  const row=materialize(c,parents);
  // Match the existing Python Domain authority: even clearing this field is
  // Human-only for AI actors; truthiness of the resulting document is not enough.
  if(p.actor_type!=='human'&&c.object_type==='ResearchRun'&&Object.hasOwn(c.payload,'human_conclusion')&&(c.operation!=='create'||Boolean(c.payload.human_conclusion)))fail('HUMAN_REQUIRED');
  if(c.operation==='restore'||[row,...parents,...hs.map(h=>state.revisions[h])].some(r=>isProtected(c,r.document)))fail('HUMAN_REQUIRED');
  const rev=await digest(c);
  if(state.revisions[rev]||Object.values(state.revisions).some(r=>r.semantic.change_id===c.change_id||r.semantic.audit_id===c.audit_id))fail('IDENTITY_COLLISION');
  for(const parent of parents)dependencies.add(parent.semantic.transaction_id);
  items.push({c,rev,row});
 }
 let relationshipBlocked=false;
 const byKey=new Map(items.map(item=>[key(item.c),item.row]));
 const reference=(kind:string,id:string):Document|null=>{
  const internal=byKey.get(kind+':'+id);if(internal){if(internal.lifecycle!=='active')relationshipBlocked=true;return internal.document;}
  const hs=state.heads[kind+':'+id]??[];if(!hs.length)fail('RELATIONSHIP_REQUIRED');
  const rows=hs.map(h=>state.revisions[h]);for(const row of rows)dependencies.add(row.semantic.transaction_id);
  if(rows.length!==1||rows.some(r=>r.lifecycle!=='active'))relationshipBlocked=true;
  return rows.length===1?rows[0].document:null;
 };
 for(const {row} of items)for(const [field,kind] of Object.entries({run_id:'ResearchRun',parent_run_id:'ResearchRun',artifact_ids:'Artifact'})){
  const value=row.document[field];if(value!==null&&value!==undefined)for(const id of Array.isArray(value)?value:[value])reference(kind,id as string);
 }
 const runParents=new Map(items.filter(i=>i.c.object_type==='ResearchRun').map(i=>[i.c.object_id,i.row.document.parent_run_id as string|null|undefined]));
 for(const oid of runParents.keys()){
  const visited=new Set<string>();let current:string|null|undefined=oid;
  while(current){if(visited.has(current))fail('DEPENDENCY_CYCLE');visited.add(current);current=runParents.has(current)?runParents.get(current):reference('ResearchRun',current)?.parent_run_id as string|null|undefined;}
 }
 for(const id of dependencies){const dep=state.transactions[id];if(!dep)fail('DEPENDENCY_REQUIRED');if(dep.raw.project_id!==tx.project_id)fail('CROSS_PROJECT_DEPENDENCY');}
 if(dependencies.has(tx.transaction_id))fail('DEPENDENCY_CYCLE');
 state.dependencies[tx.transaction_id]=[...dependencies].sort();
 for(const {c,rev,row} of items){state.revisions[rev]=row;state.heads[key(c)]=[...(state.heads[key(c)]??[]).filter(h=>!c.parents.includes(h)),rev].sort();}
 const graph=Object.fromEntries(Object.entries(state.revisions).map(([id,r])=>[id,r.semantic.parents]));
 const invalidated=new Set<string>();
 for(const {c,rev} of items){
  const hs=state.heads[key(c)];
  for(const conflict of state.conflicts.filter(x=>['open','resolving'].includes(x.status)&&x.heads.some(h=>key(state.revisions[h].semantic)===key(c)))){
   conflict.status=hs.length===1&&c.operation==='resolve'?'resolved':'superseded';if(conflict.status==='resolved')conflict.resolution=rev;
  }
  if(hs.length>1){
   const base=commonBase(graph,hs),before=base?ancestry(graph,[base]):new Set<string>();
   const candidates=[...new Set([...ancestry(graph,hs)].filter(r=>!before.has(r)).map(r=>state.revisions[r].semantic.transaction_id))].sort();
   state.conflicts.push({heads:[...hs],base,status:'open',candidates,resolution:null});for(const id of candidates)invalidated.add(id);
  }
 }
 let changed=true;while(changed){changed=false;for(const [id,deps] of Object.entries(state.dependencies))if(!invalidated.has(id)&&deps.some(d=>invalidated.has(d))){invalidated.add(id);changed=true;}}
 for(const id of invalidated){const old=state.transactions[id];if(old){if(old.state==='ACCEPTED')state.audits.push({transaction_id:id,action:'invalidate_sync_projection',content:{caused_by:tx.transaction_id}});old.state='CANDIDATE';}}
 for(const [object,rev] of Object.entries(state.projections))if(invalidated.has(state.revisions[rev].semantic.transaction_id))delete state.projections[object];
 const candidate=context.mode==='offline_proposal'||resolving||invalidated.has(tx.transaction_id)||relationshipBlocked||[...dependencies].some(d=>state.transactions[d].state!=='ACCEPTED')||items.some(i=>i.row.lifecycle!=='active'&&i.c.operation==='update');
 const status=candidate?'CANDIDATE':'ACCEPTED';
 const receipt:Receipt={transaction_id:tx.transaction_id,digest:checksum,state:status,receipt_state:status,sequence:state.sequence+1};
 state.transactions[tx.transaction_id]={raw:tx,digest:checksum,state:status,receipt};state.sequence++;
 for(const {c,rev} of items){if(!candidate)state.projections[key(c)]=rev;state.audits.push({transaction_id:tx.transaction_id,action:c.operation==='resolve'?'resolve_sync_conflict':c.operation,content:{change:c,revision:rev}});}
 const blocked=Object.values(state.transactions).filter(t=>!['ACCEPTED','SUPERSEDED'].includes(t.state)).map(t=>t.receipt.sequence);
 state.watermark=blocked.length?Math.min(...blocked)-1:state.sequence;
 return {snapshot:state,receipt:{...receipt}};
}
/** Pure staging only. Persistent IDB CAS/atomic installation belongs to the receiver. */
export async function stageRecordPage(state:RecordState,transactions:unknown[],context:RecordContext){
 let staged=structuredClone(state);const receipts:Receipt[]=[],page=structuredClone(transactions),trusted=structuredClone(context);
 for(const tx of page){const applied=await applyRecord(staged,tx,trusted);staged=applied.snapshot;receipts.push(applied.receipt);}
 return {snapshot:staged,receipts};
}
