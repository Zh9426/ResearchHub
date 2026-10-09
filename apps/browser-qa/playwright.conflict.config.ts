import {defineConfig} from '@playwright/test';
import {existsSync,mkdirSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute} from 'node:path';
import {userInfo,platform} from 'node:os';
const home=realpathSync(userInfo().homedir),result=process.env.RH_B2_RESULTS;
if(platform()!=='linux'||userInfo().uid===0||!result||!isAbsolute(result)||relative(home,resolve(result)).startsWith('..')||resolve(result)===home)throw Error('Dedicated Linux user and results under actual home required');
if(!['trusted','untrusted'].includes(process.env.RH_B2_TLS_CASE??''))throw Error('Explicit TLS case required');
if(!/^[a-f0-9]{64}$/.test(process.env.RH_B2_BUILD_HASH??''))throw Error('Public build hash required');
if(!process.env.TEST_WORKER_INDEX){if(existsSync(result))throw Error('Attempt exists; preserve first failure');mkdirSync(result,{mode:0o700});}
export default defineConfig({testDir:'./tests-network-matrix',testMatch:'conflict.spec.ts',workers:1,retries:0,timeout:180000,outputDir:resolve(result,'results'),reporter:[['./scripts/network-evidence-reporter.ts']],use:{trace:'off',screenshot:'off',video:'off'}});
