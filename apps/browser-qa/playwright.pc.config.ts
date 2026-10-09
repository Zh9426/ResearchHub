import {defineConfig} from '@playwright/test';
const attempt=process.env.RH_PC_ATTEMPT;
if(!attempt||!/^[a-zA-Z0-9_-]+$/.test(attempt))throw Error('Unique RH_PC_ATTEMPT required');
export default defineConfig({testDir:'./tests-pc',workers:1,retries:0,timeout:90000,outputDir:`../../storage/runtime/browser-sync-qa/pc/${attempt}/browser`,reporter:[['list'],['junit',{outputFile:`../../storage/runtime/browser-sync-qa/pc/${attempt}/browser-junit.xml`}]]});
