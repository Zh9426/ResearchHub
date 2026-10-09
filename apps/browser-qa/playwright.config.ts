import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,retries:0,timeout:60000,outputDir:'../../storage/runtime/browser-local-qa/test-results',reporter:[['list']]});
