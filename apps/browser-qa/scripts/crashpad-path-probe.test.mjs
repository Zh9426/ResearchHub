import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readdirSync,writeFileSync,symlinkSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as probe from './crashpad-path-probe.mjs';
const qaParent=fileURLToPath(new URL('../../../storage/runtime/browser-sync-qa/',import.meta.url));
mkdirSync(qaParent,{recursive:true});
const root=mkdtempSync(join(qaParent,'crashpad-probe-unit-'));
const home=join(root,'home'),outside=join(root,'PRIVATE_OUTSIDE');mkdirSync(home);mkdirSync(outside);
test('Crashpad selector follows CfT precedence and reports only fixed metadata',()=>{
 assert.equal(typeof probe.inspectCrashpadPath,'function');
 const fallback=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home}});
 assert.equal(fallback.selector,'HOME_FALLBACK');assert.equal(fallback.absolute,true);assert.equal(fallback.realLocation,'INSIDE_HOME');assert.equal(fallback.createProbe,'CREATED_AND_REMOVED');
 assert.deepEqual(readdirSync(home),[]);
 const xdg=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,XDG_CONFIG_HOME:join(home,'config')}});
 assert.equal(xdg.selector,'XDG_CONFIG_HOME');assert.equal(xdg.createProbe,'CREATED_AND_REMOVED');
 const chrome=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,CHROME_CONFIG_HOME:outside,XDG_CONFIG_HOME:join(home,'ignored')}});
 assert.equal(chrome.selector,'CHROME_CONFIG_HOME');assert.equal(chrome.realLocation,'OUTSIDE_HOME');assert.equal(chrome.createProbe,'NOT_ATTEMPTED');
 assert.deepEqual(readdirSync(outside),[]);assert.equal(JSON.stringify(chrome).includes('PRIVATE_OUTSIDE'),false);assert.equal(JSON.stringify(chrome).includes(home),false);
});
test('empty CHROME_CONFIG_HOME remains relative while empty XDG falls back',()=>{
 const chrome=probe.inspectCrashpadPath({home,cwd:outside,env:{HOME:home,CHROME_CONFIG_HOME:''}});
 assert.equal(chrome.selector,'CHROME_CONFIG_HOME');assert.equal(chrome.absolute,false);assert.equal(chrome.realLocation,'OUTSIDE_HOME');assert.equal(chrome.createProbe,'NOT_ATTEMPTED');
 assert.equal(probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,XDG_CONFIG_HOME:''}}).selector,'HOME_FALLBACK');
 const blocked=join(home,'file');writeFileSync(blocked,'synthetic');
 const result=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,CHROME_CONFIG_HOME:blocked}});
 assert.equal(result.nearestType,'FILE');assert.equal(result.createProbe,'NOT_ATTEMPTED');
});


test('symlink escaping actual home remains read-only despite lexical containment',()=>{
 const link=join(home,'config-link');symlinkSync(outside,link,process.platform==='win32'?'junction':'dir');
 const result=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,CHROME_CONFIG_HOME:link}});
 assert.equal(result.lexicalLocation,'INSIDE_HOME');assert.equal(result.realLocation,'OUTSIDE_HOME');assert.equal(result.createProbe,'NOT_ATTEMPTED');assert.deepEqual(readdirSync(outside),[]);
});
test('probe targets CfT Crash Reports and leaves existing directory contents intact',()=>{
 const config=join(home,'real-config'),crash=join(config,'google-chrome-for-testing','Crash Reports');mkdirSync(crash,{recursive:true});writeFileSync(join(crash,'synthetic-marker'),'keep');
 const result=probe.inspectCrashpadPath({home,cwd:root,env:{HOME:home,CHROME_CONFIG_HOME:config}});
 assert.equal(result.targetState,'EXISTS');assert.equal(result.createProbe,'CREATED_AND_REMOVED');assert.deepEqual(readdirSync(crash),['synthetic-marker']);
});

test('sanitizing only directory overrides changes outside selection to actual-home fallback',()=>{
 const prior={HOME:home,XDG_CONFIG_HOME:outside,XDG_CACHE_HOME:outside,XDG_DATA_HOME:outside,XDG_STATE_HOME:outside,PRIVATE_BUSINESS_TOKEN:'PRIVATE_SECRET'};
 const before=probe.inspectCrashpadPath({home,cwd:root,env:prior});
 const cleaned={...prior};for(const key of ['CHROME_CONFIG_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME'])delete cleaned[key];
 const after=probe.inspectCrashpadPath({home,cwd:root,env:cleaned});
 assert.equal(before.selector,'XDG_CONFIG_HOME');assert.equal(before.realLocation,'OUTSIDE_HOME');assert.equal(before.createProbe,'NOT_ATTEMPTED');
 assert.equal(after.selector,'HOME_FALLBACK');assert.equal(after.realLocation,'INSIDE_HOME');assert.equal(after.createProbe,'CREATED_AND_REMOVED');
 assert.equal(cleaned.HOME,prior.HOME);assert.equal(prior.XDG_CONFIG_HOME,outside);assert.equal(cleaned.PRIVATE_BUSINESS_TOKEN,prior.PRIVATE_BUSINESS_TOKEN);
 assert.equal(JSON.stringify({before,after}).includes('PRIVATE'),false);
});
