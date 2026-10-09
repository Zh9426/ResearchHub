import {test,expect} from '@playwright/test';
import {resolve} from 'node:path';
import {launch,closeBrowser} from '../tests/lifecycle';
import {startPc,stopPc} from './lifecycle';
for(const [module,alias,runType] of [['generic','generic','simulation'],['hdsp','hdsp','phase_retrieval'],['ice-sonocuring','ice','numerical_validation']]){
 test(`PC真实${module}根入口使用冻结模块合法语境字段`,async()=>{
  const server=await startPc(['--node',`qa-${module}-${process.env.RH_PC_ATTEMPT}`,'--module',module]);const context=await launch(resolve('../../storage/runtime/browser-sync-qa/pc/profiles',`${module}-${process.env.RH_PC_ATTEMPT}`));
  try{const p=await context.newPage();await p.goto('http://127.0.0.1:3315');await expect(p.getByRole('combobox',{name:'项目选择',exact:true})).toHaveValue(alias);await p.getByRole('button',{name:'新建 Run',exact:true}).click();await p.getByLabel('标题',{exact:true}).fill('SYNTHETIC '+module);await p.getByRole('combobox',{name:'记录类型',exact:true}).selectOption(runType);await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');await p.getByText('高级语境（可选）',{exact:true}).click();await p.getByRole('textbox',{name:'代码仓库',exact:true}).fill('合成代码路径');await p.getByRole('button',{name:'保存到本机',exact:true}).click();await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');await p.reload();await p.getByText('高级语境（可选）',{exact:true}).click();await expect(p.getByRole('textbox',{name:'代码仓库',exact:true})).toHaveValue('合成代码路径');
  }finally{const outcomes=await Promise.allSettled([closeBrowser(context),stopPc(server)]);const errors=outcomes.filter(x=>x.status==='rejected');if(errors.length)throw new AggregateError(errors,'QA cleanup failed');}
 });
}
