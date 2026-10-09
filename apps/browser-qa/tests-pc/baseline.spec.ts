import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {resolve,delimiter} from 'node:path';
import {launch,closeBrowser} from '../tests/lifecycle';
import {observeOwnedExit} from './owned-exit';

async function deadline<T>(promise:Promise<T>,milliseconds:number,stage:string){let timer:ReturnType<typeof setTimeout>|undefined;try{return await Promise.race([promise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error(stage)),milliseconds);})]);}finally{clearTimeout(timer);}}

test('SYNTHETIC manual baseline three consecutive UI saves retain observation',async()=>{
 const root=resolve('../..');const python=process.env.RH_QA_PYTHON??resolve(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 const env={...process.env,HUB_SYNC_QA:'1',PYTHONPATH:['apps/api','.'].join(delimiter)};
 const server=spawn(python,['-m','researchhub.sync.pc_cli','start','--node','baseline-'+randomUUID()],{cwd:root,env,stdio:'pipe'});
 const began=Date.now();const stage=(name:string)=>console.log('PC_UI_STAGE',name,Date.now()-began);const exited=observeOwnedExit(server);
 server.stdout!.on('data',d=>{for(const name of ['PC_QA_READY','stop_requested','server_run_returned'])if(String(d).includes(name))stage(name);});
 server.stderr!.on('data',d=>{const value=String(d);for(const name of ['ConnectionResetError','Waiting for application shutdown','Application shutdown complete','Finished server process'])if(value.includes(name))stage(name.replaceAll(' ','_'));});
 let context:Awaited<ReturnType<typeof launch>>|undefined,primary:unknown;
 try{
  await deadline(new Promise<void>((ok,no)=>{server.stdout!.on('data',d=>{if(String(d).includes('PC_QA_READY'))ok();});server.once('error',no);server.once('exit',c=>no(Error(`PC server exited ${c}`)));}),20000,'PC_START_DEADLINE');
  context=await launch(resolve(root,'storage/runtime/browser-sync-qa/pc/profiles',`baseline-${process.env.RH_PC_ATTEMPT}`));
  const p=await context.newPage();await p.goto('http://127.0.0.1:3315');await expect(p.getByRole('note')).toContainText('PC 合成节点');
  await expect(p.getByTestId('binding-preview')).toHaveText('结构校验通过，仍须独立信任确认');
  expect(await p.evaluate(()=>Boolean((window as any).__LOCAL_QA__))).toBe(false);
  const save=async()=>{await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');};
  const commands:any[]=[];p.on('request',request=>{if(request.url().endsWith('/api/command'))commands.push(request.postDataJSON());});
  await p.getByRole('button',{name:'新建 Run',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC C manual Run');await save();
  await p.getByLabel('观察',{exact:true}).fill('SYNTHETIC PC baseline second save');await save();
  await p.getByRole('button',{name:'新建 Note',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC C manual Note');await p.getByLabel('笔记正文',{exact:true}).fill('SYNTHETIC PC note');await save();
  expect(commands).toHaveLength(3);expect(commands[1].patch.observation).toBe('SYNTHETIC PC baseline second save');
  const snapshot=await p.evaluate(async()=>{const r=await fetch('/api/snapshot');return r.json();});
  const run=snapshot.snapshot.objects.find((o:any)=>o.kind==='Run');expect(run.observation).toBe('SYNTHETIC PC baseline second save');
  const record=snapshot.records.find((r:any)=>r.object_id===run.id);expect(record.trusted.accepted.observation).toBe('SYNTHETIC PC baseline second save');
  console.log('PC_BASELINE_THREE_COMMANDS_REQUEST_WORK_AND_KERNEL_MATCH');
 }catch(error){primary=error;throw error;}finally{
  const errors:unknown[]=[];
  try{stage('browser_close_begin');if(context)await deadline(closeBrowser(context),20000,'PC_BROWSER_CLOSE_DEADLINE');stage('browser_closed');}catch(e){errors.push(e);}
  try{if(server.exitCode===null&&server.signalCode===null)await deadline(new Promise<void>((ok,no)=>{const stop=spawn(python,['-m','researchhub.sync.pc_cli','stop'],{cwd:root,env,stdio:'ignore'});stop.once('error',no);stop.once('exit',c=>{stage('stop_cli_exit_'+c);c===0?ok():no(Error('PC stop failed'));});}),15000,'PC_STOP_DEADLINE');}catch(e){errors.push(e);if(server.exitCode===null&&server.signalCode===null)server.kill();}
  try{stage('waiting_owned_server_exit');const result=await deadline(exited,15000,'PC_EXIT_DEADLINE');stage('server_exit_'+result.code);if(result.code!==0)errors.push(Error('Owned PC exit was not clean'));}catch(error){errors.push(error);if(server.exitCode===null&&server.signalCode===null)server.kill();}
  if(errors.length)throw new AggregateError(primary?[primary,...errors]:errors,'PC QA cleanup failed');
 }
});
