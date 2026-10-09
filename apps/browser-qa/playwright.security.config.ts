import { existsSync } from 'node:fs';
import { defineConfig } from '@playwright/test';
const attempt = process.env.RH_B1_ATTEMPT;
if (!attempt || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(attempt))
    throw Error('RH_B1_ATTEMPT must be an explicit unique safe slug');
if (!process.env.TEST_WORKER_INDEX && existsSync(`../../storage/runtime/browser-sync-qa/security/${attempt}`))
    throw Error('Attempt already exists; preserve evidence');
export default defineConfig({ testDir: './tests-security', testMatch: process.env.RH_B1_NORMAL === '1' ? 'normal.spec.ts' : 'security.spec.ts', workers: 1, retries: 0, timeout: 60000, outputDir: `../../storage/runtime/browser-sync-qa/security/${attempt}/results`, reporter: [['./scripts/security-evidence-reporter.ts'], ['list'], ['junit', { outputFile: `../../storage/runtime/browser-sync-qa/security/${attempt}/junit.xml` }]] });
