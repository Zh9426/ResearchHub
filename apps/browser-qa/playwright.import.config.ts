import {defineConfig} from '@playwright/test';
import {existsSync,mkdirSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute} from 'node:path';
import {userInfo,platform} from 'node:os';
const home=realpathSync(userInfo().homedir),result=process.env.RH_B2_RESULTS,source=process.env.RH_IMPORT_SOURCE_DIR;
for(const path of [result,source])if(platform()!=='linux'||userInfo().uid===0||!path||!isAbsolute(path)||relative(home,resolve(path)).startsWith('..')||resolve(path)===home)throw Error('Dedicated Linux user and private results/source under actual home required');
if(!['prepare','apply'].includes(process.env.RH_IMPORT_PHASE??'')||!['hdsp','ice-sonocuring'].includes(process.env.RH_IMPORT_MODULE??''))throw Error('Explicit import phase and source module required');
if(process.env.RH_B2_TLS_CASE!=='trusted'||!/^[a-f0-9]{64}$/.test(process.env.RH_B2_BUILD_HASH??''))throw Error('Trusted TLS and public build hash required');
if(!process.env.TEST_WORKER_INDEX){if(existsSync(result!))throw Error('Attempt exists; preserve first failure');mkdirSync(result!,{mode:0o700});if(process.env.RH_IMPORT_PHASE==='prepare'){if(existsSync(source!))throw Error('Source directory exists');mkdirSync(source!,{mode:0o700});}}
export default defineConfig({testDir:'./tests-network-matrix',testMatch:'import.spec.ts',workers:1,retries:0,timeout:180000,outputDir:resolve(result!,'results'),reporter:[['./scripts/network-evidence-reporter.ts']],use:{trace:'off',screenshot:'off',video:'off'}});
