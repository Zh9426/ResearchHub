import {test,expect} from '@playwright/test';
import {resolve} from 'node:path';
import {launch,closeBrowser} from '../tests/lifecycle';
import {startPc,stopPc} from './lifecycle';
test('PC重启后原页面重建会话，脏内容和prepared命令身份不变',async()=>{
 let server=await startPc();const context=await launch(resolve('../../storage/runtime/browser-sync-qa/pc/profiles','restart-'+process.env.RH_PC_ATTEMPT));
 try{
  const p=await context.newPage();await p.goto('http://127.0.0.1:3315');await p.getByRole('button',{name:'新建 Note',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC restart');await p.getByRole('textbox',{name:'笔记正文',exact:true}).fill('初始');await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
  await p.getByRole('textbox',{name:'笔记正文',exact:true}).fill('  重启时未保存 🧪  ');await stopPc(server);server=await startPc();
  const commands:unknown[]=[];p.on('request',r=>{if(r.url().endsWith('/api/command'))commands.push(r.postDataJSON());});
  await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('本次修改未保存');await expect(p.getByRole('textbox',{name:'笔记正文',exact:true})).toHaveValue('  重启时未保存 🧪  ');
  let sessionCalls=0;let release!:()=>void;const hold=new Promise<void>(resolve=>{release=resolve;});
  await p.route('**/api/session',async route=>{sessionCalls++;await hold;await route.continue();});
  try{await p.getByRole('button',{name:'刷新可信状态',exact:true}).click();await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect.poll(()=>sessionCalls).toBe(1);await expect(p.getByTestId('local-save')).toHaveText('正在保存…');}finally{release();}
  await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');expect(sessionCalls).toBe(1);expect(commands).toHaveLength(2);expect(commands[0]).toEqual(commands[1]);
 }finally{const outcomes=await Promise.allSettled([closeBrowser(context),stopPc(server)]);const errors=outcomes.filter(x=>x.status==='rejected');if(errors.length)throw new AggregateError(errors,'QA cleanup failed');}
});
