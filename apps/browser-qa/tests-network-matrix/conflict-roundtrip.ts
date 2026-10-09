import {resolve} from 'node:path';
import {expect,type Page} from '@playwright/test';
/** Fresh normal pairing required. Actual B WebCrypto and distinct PC DB; no fixture writes. */
export async function conflictRoundTrip(b:Page,pc:Page,mark:(stage:string)=>void){
 const sync=async(p:Page)=>{await p.getByRole('button',{name:'立即同步',exact:true}).click();await expect(p.getByTestId('manual-sync-status')).toContainText('本轮发送',{timeout:60000});};
 const save=async(p:Page)=>{await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');};
 const title='SYNTHETIC conflict roundtrip Note',base='SYNTHETIC common BASE',local='SYNTHETIC B branch',remote='SYNTHETIC PC branch',proposal='SYNTHETIC reviewed offline proposal';
 mark('CONFLICT_BASE');await pc.getByRole('button',{name:'新建 Note',exact:true}).click();await pc.getByLabel('标题',{exact:true}).fill(title);await pc.getByLabel('笔记正文',{exact:true}).fill(base);await save(pc);const oid=new URL(pc.url()).pathname.split('/').at(-1)!;
 await sync(pc);await sync(b);await sync(pc);await b.locator('button.qa-record').filter({hasText:title}).click();
 mark('CONFLICT_SAME_BASE_EDITS');await pc.getByLabel('笔记正文',{exact:true}).fill(remote);await save(pc);await b.getByLabel('笔记正文',{exact:true}).fill(local);await save(b);
 await sync(b);await sync(pc);await sync(b);await sync(pc);
 for(const p of [b,pc]){await p.getByRole('button',{name:'比较 '+oid,exact:true}).click();const comparison=p.getByRole('region',{name:'字段三方比较'});await expect(comparison.getByText(base,{exact:true})).toBeVisible();await expect(comparison.getByText(local,{exact:true})).toBeVisible();await expect(comparison.getByText(remote,{exact:true})).toBeVisible();await expect(comparison.getByText(/本地分支/)).toHaveCount(2);}
 await b.getByRole('region',{name:'字段三方比较'}).screenshot({path:resolve(process.env.RH_B2_RESULTS!,'conflict-comparison.png')});
 mark('CONFLICT_OFFLINE_PROPOSAL');await pc.getByLabel('笔记正文提案',{exact:true}).fill('SYNTHETIC stale input retained');await b.getByLabel('笔记正文提案',{exact:true}).fill(proposal);await b.getByRole('button',{name:'保存离线提案（待人工批准）',exact:true}).click();await expect(b.getByText('提案已保存到本机：CANDIDATE，待人工批准。冲突收束不等于已接受。',{exact:true})).toBeVisible();
 await sync(b);await sync(pc);await sync(b);
 mark('CONFLICT_STALE_COMPARE_REJECT');await pc.getByRole('button',{name:'保存离线提案（待人工批准）',exact:true}).click();await expect(pc.getByRole('alert')).toContainText('输入已保留');await expect(pc.getByLabel('笔记正文提案',{exact:true})).toHaveValue('SYNTHETIC stale input retained');
 mark('CONFLICT_CANDIDATE_CONVERGENCE');
 const bview=await b.evaluate(async oid=>{const db=await new Promise<IDBDatabase>((ok,no)=>{const r=indexedDB.open('researchhub-browser-sync-qa-business-v1');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});try{return await new Promise<any>((ok,no)=>{const r=db.transaction('meta').objectStore('meta').getAll();r.onerror=()=>no(r.error);r.onsuccess=()=>{const state=r.result.find(x=>x.id.startsWith('record-kernel:')).state,heads=state.heads['Note:'+oid];ok({heads,documents:heads.map((h:string)=>state.revisions[h].document),states:heads.map((h:string)=>state.transactions[state.revisions[h].semantic.transaction_id].state),accepted:state.projections['Note:'+oid]??null});};});}finally{db.close();}},oid);
 const pcview=await pc.evaluate(async oid=>{const data=await(await fetch('/api/snapshot')).json(),r=data.records.find((r:any)=>r.object_id===oid);return {heads:r.trusted.heads,documents:r.trusted.candidates.map((c:any)=>c.document),states:r.trusted.candidates.map((c:any)=>c.state),accepted:r.trusted.accepted_revision};},oid);
 expect(bview).toEqual(pcview);expect(bview.heads).toHaveLength(1);expect(bview.states).toEqual(['CANDIDATE']);expect(bview.accepted).toBeNull();expect(bview.documents[0].content).toBe(proposal);
 await b.getByRole('button',{name:'比较 '+oid,exact:true}).click();await b.getByRole('region',{name:'字段三方比较'}).screenshot({path:resolve(process.env.RH_B2_RESULTS!,'conflict-candidate.png')});
 mark('CONFLICT_COMPLETE');
}
