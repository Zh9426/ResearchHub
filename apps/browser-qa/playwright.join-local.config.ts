import {defineConfig} from '@playwright/test';
import {existsSync} from 'node:fs';
const attempt=process.env.RH_B2_LOCAL_ATTEMPT;
if(!attempt||!/^[A-Za-z0-9_-]{1,80}$/.test(attempt))throw Error('Explicit unique RH_B2_LOCAL_ATTEMPT required');
const root=`../../storage/runtime/browser-sync-qa/b2-local/${attempt}`;
if(!process.env.TEST_WORKER_INDEX&&existsSync(root))throw Error('Attempt exists; preserve first failure');
export default defineConfig({testDir:'./tests-security',testMatch:'join-ui.spec.ts',workers:1,retries:0,outputDir:root+'/results',reporter:[['list'],['junit',{outputFile:root+'/junit.xml'}]],webServer:{command:'node scripts/sync.mjs server',url:'http://127.0.0.1:3314',reuseExistingServer:false}});
