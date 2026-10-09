import {defineConfig} from '@playwright/test';
import {resolve} from 'node:path';
const root=process.env.RH_C1_RESULTS;
if(!root)throw Error('Owned C1 runner must supply results');
export default defineConfig({testDir:'./tests-kernel',testMatch:'record-kernel.spec.ts',workers:1,retries:0,timeout:90000,outputDir:resolve(root,'results'),reporter:[['list'],['junit',{outputFile:resolve(root,'junit.xml')}]]});
