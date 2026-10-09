import {existsSync} from 'node:fs';
import {defineConfig} from '@playwright/test';
const attempt=process.env.RH_A2_ATTEMPT??`run-${Date.now()}`;
if(!process.env.TEST_WORKER_INDEX&&existsSync(`../../storage/runtime/browser-sync-qa/a2/${attempt}`))throw Error('Attempt already exists; preserve evidence and choose a new RH_A2_ATTEMPT');
export default defineConfig({testDir:'./tests-sync',workers:1,retries:0,timeout:60000,outputDir:`../../storage/runtime/browser-sync-qa/a2/${attempt}/results`,reporter:[['list'],['junit',{outputFile:`../../storage/runtime/browser-sync-qa/a2/${attempt}/junit.xml`}]]});
