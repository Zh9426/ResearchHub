import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests-network-matrix',testMatch:'import-unit.spec.ts',workers:1,retries:0,timeout:60000,outputDir:process.env.RH_IMPORT_UNIT_RESULTS??'../../storage/runtime/browser-sync-qa/import/unit-results',reporter:'list',use:{headless:true}});
