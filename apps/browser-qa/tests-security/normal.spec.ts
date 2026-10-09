import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { launch, closeBrowser, stopServer } from '../tests/lifecycle';
test('normal 3B bundle excludes TEST ONLY fixture and fault bridges; UI stays unverified', async () => {
    const bundle = readFileSync('../../storage/runtime/browser-sync-qa/dist/app.js', 'utf8');
    expect(bundle).not.toContain('__B1_TEST_ONLY__');
    expect(bundle).not.toContain('__SYNC_QA_TEST_ONLY__');
    expect(bundle).not.toContain('TEST_ONLY-imported-keys');
    const server = spawn(process.execPath, ['scripts/server.mjs'], { env: { ...process.env, RH_QA_PROFILE: 'sync' }, stdio: 'pipe' });
    let context;
    try {
        await new Promise<void>((ok, no) => {
            server.stdout!.on('data', d => {
                if (String(d).includes('QA_READY'))
                    ok();
            });
            server.once('error', no);
            server.once('exit', c => no(Error(`server ${c}`)));
        });
        context = await launch(resolve('../../storage/runtime/browser-sync-qa/security', process.env.RH_B1_ATTEMPT!, 'normal-profile'));
        const evidence=resolve('../../storage/runtime/browser-sync-qa/security',process.env.RH_B1_ATTEMPT!);mkdirSync(evidence,{recursive:true});writeFileSync(resolve(evidence,'versions.json'),JSON.stringify({node:process.version,chromium:context.browser()!.version(),hpke:null,retries:0}));
        const p = await context.newPage();
        await p.goto('http://127.0.0.1:3314');
        expect(await p.evaluate(() => ({ b1: typeof (window as any).__B1_TEST_ONLY__, a2: typeof (window as any).__SYNC_QA_TEST_ONLY__ }))).toEqual({ b1: 'undefined', a2: 'undefined' });
        await expect(p.getByText('尚未加入受信项目。尚未验证项目所有者和设备授权，暂不能转换或发送。')).toBeVisible();
    }
    finally {
        const results = await Promise.allSettled([context ? closeBrowser(context) : Promise.resolve(), stopServer(server)]);
        const errors = results.filter(r => r.status === 'rejected');
        if (errors.length)
            throw new AggregateError(errors.map(r => (r as PromiseRejectedResult).reason), 'normal build cleanup failed');
    }
});
