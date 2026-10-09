import {test,expect} from '@playwright/test';
import {build} from 'esbuild';
import {resolve} from 'node:path';

test('3A import preserves edits and atomically archives in native IndexedDB',async({page})=>{
 const bundle=await build({entryPoints:[resolve('tests-network-matrix/import-unit-entry.ts')],bundle:true,write:false,format:'iife',platform:'browser'});
 await page.route('http://127.0.0.1:3314/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body>独立合成导入验证</body></html>'}));
 await page.goto('http://127.0.0.1:3314/import-unit');
 await page.addScriptTag({content:bundle.outputFiles[0].text});
 expect(await page.evaluate(async()=>await (window as any).importUnit())).toEqual({passed:true});
});
