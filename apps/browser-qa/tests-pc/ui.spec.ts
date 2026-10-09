import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {resolve,delimiter} from 'node:path';
import {launch,closeBrowser} from '../tests/lifecycle';
import {observeOwnedExit} from './owned-exit';

test('PC独立业务界面：Run/Note创建编辑，星标不提交脏正文，公共绑定验证',async()=>{
 const root=resolve('../..');const python=process.env.RH_QA_PYTHON??resolve(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 const env={...process.env,HUB_SYNC_QA:'1',PYTHONPATH:['apps/api','.'].join(delimiter)};
 const server=spawn(python,['-m','researchhub.sync.pc_cli','start'],{cwd:root,env,stdio:'pipe'});
 const began=Date.now();const stage=(name:string)=>console.log('PC_UI_STAGE',name,Date.now()-began);const exited=observeOwnedExit(server);
 server.stdout!.on('data',d=>{for(const name of ['PC_QA_READY','stop_requested','server_run_returned'])if(String(d).includes(name))stage(name);});
 server.stderr!.on('data',d=>{const value=String(d);for(const name of ['ConnectionResetError','Waiting for application shutdown','Application shutdown complete','Finished server process'])if(value.includes(name))stage(name.replaceAll(' ','_'));});
 let context:Awaited<ReturnType<typeof launch>>|undefined;
 try{
  await new Promise<void>((ok,no)=>{server.stdout!.on('data',d=>{if(String(d).includes('PC_QA_READY'))ok();});server.on('exit',c=>no(Error(`PC server exited ${c}`)));});
  context=await launch(resolve(root,'storage/runtime/browser-sync-qa/pc/profiles',`ui-${process.env.RH_PC_ATTEMPT}`));
  const p=await context.newPage();p.on('response',async r=>{if(r.url().endsWith('/api/command')&&!r.ok()){const value=await r.json();console.log('PC_COMMAND_REJECTED',r.status(),typeof value.error==='string'&&/^[A-Z_]+$/.test(value.error)?value.error:'REQUEST_REJECTED');}});await p.goto('http://127.0.0.1:3315');await expect(p.getByRole('note')).toContainText('PC 合成节点');
  await expect(p.getByTestId('binding-preview')).toHaveText('结构校验通过，仍须独立信任确认');
  expect(await p.evaluate(()=>Boolean((window as any).__LOCAL_QA__))).toBe(false);
  await p.getByRole('button',{name:'新建 Run',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC PC Run '+process.env.RH_PC_ATTEMPT);
  await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
  await p.getByRole('textbox',{name:'观察',exact:true}).fill('持久正文');await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
  await p.getByRole('textbox',{name:'观察',exact:true}).fill('尚未保存 🧪');await p.getByRole('button',{name:'设为星标',exact:true}).click();await expect(p.getByRole('button',{name:'取消星标',exact:true})).toBeVisible();await expect(p.getByRole('textbox',{name:'观察',exact:true})).toHaveValue('尚未保存 🧪');
  const persisted=await p.evaluate(async()=>{const r=await fetch('/api/snapshot');return r.json();});
  // Locate by latest opened route; process.env is deliberately not used inside the page.
  const oid=new URL(p.url()).pathname.split('/').pop();const saved=persisted.snapshot.objects.find((o:any)=>o.id===oid);
  expect(saved.observation).toBe('持久正文');expect(saved.is_highlighted).toBe(true);
  await p.screenshot({path:test.info().outputPath('synthetic-pc-dirty-star.png'),fullPage:true});
  await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
  await p.getByRole('button',{name:'新建 Note',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC PC Note');const body='  中文 🧪\n\t  ';
  await p.getByRole('textbox',{name:'笔记正文',exact:true}).fill(body);await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
  await p.getByRole('textbox',{name:'笔记正文',exact:true}).fill(body+'后继');await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');await p.reload();await expect(p.getByRole('textbox',{name:'笔记正文',exact:true})).toHaveValue(body+'后继');
  await p.getByRole('button',{name:'刷新可信状态',exact:true}).click();await p.screenshot({path:test.info().outputPath('synthetic-pc-note.png'),fullPage:true});
 }finally{
  const errors:unknown[]=[];
  try{stage('browser_close_begin');if(context)await closeBrowser(context);stage('browser_closed');}catch(e){errors.push(e);}
  try{await new Promise<void>((ok,no)=>{const stop=spawn(python,['-m','researchhub.sync.pc_cli','stop'],{cwd:root,env,stdio:'ignore'});stop.once('error',no);stop.once('exit',c=>{stage('stop_cli_exit_'+c);c===0?ok():no(Error('PC stop failed'));});});}catch(e){errors.push(e);if(server.exitCode===null&&server.signalCode===null)server.kill();}
  stage('waiting_owned_server_exit');const result=await exited;stage('server_exit_'+result.code);if(result.code!==0)errors.push(Error('Owned PC exit was not clean'));
  if(errors.length)throw new AggregateError(errors,'PC QA cleanup failed');
 }
});
