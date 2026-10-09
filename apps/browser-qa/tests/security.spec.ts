import { test, expect, type BrowserContext } from '@playwright/test';
import { resolve } from 'node:path';
import { runtime, origin, startServer, stopServer, launch, closeBrowser } from './lifecycle';
test('独立 QA key、nonce 并发、完整重试及进程重开', async () => {
    const server = await startServer();
    let context: BrowserContext | undefined;
    const profile = resolve(runtime, 'profiles', `crypto-${Date.now()}`);
    try {
        context = await launch(profile);
        let p = await context.newPage();
        await p.goto(origin);
        expect(await p.evaluate(() => typeof (window as any).__SECURITY_QA__)).toBe('object');
        const id = await p.evaluate(() => (window as any).__SECURITY_QA__.create());
        const q = await context.newPage();
        await q.goto(origin);
        const results = await Promise.all([p, q].map((page, i) => page.evaluate(async ({ id, i }) => (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-action-' + i, 'TESTONLY-payload'), { id, i })));
        expect(results[0].nonce).not.toBe(results[1].nonce);
        const race = await Promise.allSettled([p, q].map(page => page.evaluate(({ id }) => (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-cross-tab', 'TESTONLY-payload'), { id })));
        const completed = race.filter(x => x.status === 'fulfilled') as PromiseFulfilledResult<any>[];
        expect(completed.length).toBeGreaterThan(0);
        for (const x of completed)
            expect(x.value).toEqual(completed[0].value);
        await p.reload();
        const refreshed = await p.evaluate(({ id }) => (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-refreshed', 'TESTONLY-payload'), { id });
        expect([results[0].nonce, results[1].nonce, completed[0].value.nonce]).not.toContain(refreshed.nonce);
        expect(await p.evaluate(({ id }) => (window as any).__SECURITY_QA__.open(id, 'TESTONLY-action-0'), { id })).toBe('TESTONLY-payload');
        expect(await q.evaluate(({ id }) => (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-action-0', 'TESTONLY-payload'), { id })).toEqual(results[0]);
        expect(await p.evaluate(async ({ id }) => { try {
            await (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-action-0', 'TESTONLY-changed');
            return 'bad';
        }
        catch {
            return 'rejected';
        } }, { id })).toBe('rejected');
        // TEST ONLY stalls encryption after the real reservation commit; process exit loses the unfinished action.
        await p.evaluate(({id})=>{SubtleCrypto.prototype.encrypt=()=>new Promise(()=>{});void (window as any).__SECURITY_QA__.seal(id,'TESTONLY-interrupted','TESTONLY-payload');},{id});
        await expect.poll(()=>p.evaluate(({id})=>(window as any).__SECURITY_QA__.status(id).then((s:any)=>s.counter),{id})).toBe(5);
        await closeBrowser(context);
        context = await launch(profile);
        p = await context.newPage();
        await p.goto(origin);
        expect(await p.evaluate(({ id }) => (window as any).__SECURITY_QA__.seal(id, 'TESTONLY-action-0', 'TESTONLY-payload'), { id })).toEqual(results[0]);
        expect(await p.evaluate(({ id }) => (window as any).__SECURITY_QA__.open(id, 'TESTONLY-action-0'), { id })).toBe('TESTONLY-payload');
        expect(await p.evaluate(async({id})=>{try{await (window as any).__SECURITY_QA__.seal(id,'TESTONLY-interrupted','TESTONLY-payload');return false;}catch{return true;}},{id})).toBe(true);
        expect(await p.evaluate(({ id }) => (window as any).__SECURITY_QA__.status(id), { id })).toMatchObject({ counter: 5, extractable: false, network: 'BLOCKED FOR NETWORK USE' });
    }
    finally {
        await context?.close();
        await stopServer(server);
    }
});
test('局部损坏与旧ledger拒绝，失败耗号且同action并发只生成一次', async () => {
    const server = await startServer();
    const context = await launch(resolve(runtime, 'profiles', `crypto-failure-${Date.now()}`));
    try {
        const p = await context.newPage();
        await p.goto(origin);
        const result = await p.evaluate(async () => {
            const qa = (window as any).__SECURITY_QA__;
            const fails = async (f: () => Promise<any>) => { try {
                await f();
                return false;
            }
            catch {
                return true;
            } };
            const edit = async (store: string, id: string, fn: (v: any) => any) => { const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open('researchhub-TESTONLY-security-v1'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); }); await new Promise<void>((ok, no) => { const tx = db.transaction(store, 'readwrite'), s = tx.objectStore(store), r = s.get(id); r.onsuccess = () => { const v = fn(r.result); if (v === undefined)
                s.delete(id);
            else
                s.put(v); }; tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); }); db.close(); };
            const id = await qa.create();
            const original = SubtleCrypto.prototype.encrypt;
            let count = 0;
            SubtleCrypto.prototype.encrypt = function (...args: any[]) { count++; return original.apply(this, args as any); };
            const race = await Promise.allSettled([qa.seal(id, 'TESTONLY-race', 'TESTONLY-payload'), qa.seal(id, 'TESTONLY-race', 'TESTONLY-payload')]);
            const fulfilled = race.filter(x => x.status === 'fulfilled') as PromiseFulfilledResult<any>[];
            if (fulfilled.length === 2 && JSON.stringify(fulfilled[0].value) !== JSON.stringify(fulfilled[1].value))
                throw Error('divergent envelope');
            const encryptions = count;
            SubtleCrypto.prototype.encrypt = function () { return Promise.reject(Error('TEST ONLY post-reservation encryption failure')); };
            const burn = await fails(() => qa.seal(id, 'TESTONLY-burn', 'TESTONLY-payload'));
            SubtleCrypto.prototype.encrypt = original;
            const pending = await fails(() => qa.seal(id, 'TESTONLY-burn', 'TESTONLY-payload'));
            const counter = (await qa.status(id)).counter;
            await edit('actions', id + ':TESTONLY-race', v => ({ ...v, envelope: { ...v.envelope, ciphertext: '00' } }));
            const corruptEnvelope = await fails(() => qa.seal(id, 'TESTONLY-race', 'TESTONLY-payload'));
            const missingKey = await qa.create();
            await edit('keys', missingKey, () => undefined);
            const keyRejected = await fails(() => qa.seal(missingKey, 'TESTONLY-new', 'TESTONLY-payload'));
            const missingLedger = await qa.create();
            await edit('ledger', missingLedger, () => undefined);
            const ledgerRejected = await fails(() => qa.seal(missingLedger, 'TESTONLY-new', 'TESTONLY-payload'));
            const corruptKey=await qa.create();await edit('keys',corruptKey,v=>({...v,key:{algorithm:{name:'AES-GCM'}}}));const corruptKeyRejected=await fails(()=>qa.status(corruptKey));
            const corrupt = await qa.create();
            await edit('ledger', corrupt, v => ({ ...v, counter: -1 }));
            const corruptRejected = await fails(() => qa.status(corrupt));
            const old = await qa.create();
            await qa.seal(old, 'TESTONLY-first', 'TESTONLY-payload');
            await edit('ledger', old, v => ({ ...v, counter: 0 }));
            const oldRejected = await fails(() => qa.status(old));
            const importRejected = await fails(() => qa.importLedger({ counter: 0 }));
            const overflow = await qa.create();
            await edit('keys', overflow, v => ({ ...v, high: Number.MAX_SAFE_INTEGER }));
            await edit('ledger', overflow, v => ({ ...v, counter: Number.MAX_SAFE_INTEGER }));
            const overflowRejected = await fails(() => qa.seal(overflow, 'TESTONLY-overflow', 'TESTONLY-payload'));
            return { corruptKeyRejected, encryptions, burn, pending, counter, corruptEnvelope, keyRejected, ledgerRejected, corruptRejected, oldRejected, importRejected, overflowRejected };
        });
        expect(result).toEqual({ corruptKeyRejected:true, encryptions: 1, burn: true, pending: true, counter: 2, corruptEnvelope: true, keyRejected: true, ledgerRejected: true, corruptRejected: true, oldRejected: true, importRejected: true, overflowRejected: true });
        console.log(JSON.stringify(result));
    }
    finally {
        await context.close();
        await stopServer(server);
    }
});
test('真实 key DB 存在时救援包排除 key 与 nonce，fresh profile 不克隆身份', async () => {
    const server = await startServer();
    const source = await launch(resolve(runtime, 'profiles', `key-rescue-source-${Date.now()}`));
    const target = await launch(resolve(runtime, 'profiles', `key-rescue-target-${Date.now()}`));
    try {
        const p = await source.newPage();
        await p.goto(origin);
        await p.getByRole('button', { name: '初始化合成工作区', exact: true }).click();
        await expect(p.getByLabel('项目选择')).toBeVisible();
        const before = await p.evaluate(() => (window as any).__LOCAL_QA__.snapshot());
        const id = await p.evaluate(async () => { const q = (window as any).__SECURITY_QA__; const id = await q.create(); await q.seal(id, 'TESTONLY-rescue', 'TESTONLY-payload'); return id; });
        await p.getByText('诊断与合成草稿救援', { exact: true }).click();
        const wait = p.waitForEvent('download');
        await p.getByRole('button', { name: '导出合成救援包', exact: true }).click();
        const download = await wait;
        const stream = await download.createReadStream();
        const chunks: Buffer[] = [];
        for await (const chunk of stream!)
            chunks.push(chunk);
        const raw = Buffer.concat(chunks).toString('utf8');
        expect(raw).not.toContain(id);
        for (const field of ['ciphertext', 'nonce', 'CryptoKey', 'ledger'])
            expect(raw).not.toContain('"' + field + '"');
        const q = await target.newPage();
        await q.goto(origin);
        await q.getByText('诊断与合成草稿救援', { exact: true }).click();
        await q.getByLabel('选择合成救援包').setInputFiles({ name: 'synthetic.json', mimeType: 'application/json', buffer: Buffer.from(raw) });
        await q.getByRole('button', { name: '确认恢复到空工作区', exact: true }).click();
        await expect(q.getByTestId('rescue-status')).toContainText('恢复已提交');
        const after = await q.evaluate(() => (window as any).__LOCAL_QA__.snapshot());
        expect(after.identity.device_id).not.toBe(before.identity.device_id);
        expect(await q.evaluate(async () => (await indexedDB.databases()).map(x => x.name))).not.toContain('researchhub-TESTONLY-security-v1');
        expect(await q.evaluate(async (id) => { try {
            await (window as any).__SECURITY_QA__.open(id, 'TESTONLY-rescue');
            return false;
        }
        catch {
            return true;
        } }, id)).toBe(true);
        const fresh = await q.evaluate(() => (window as any).__SECURITY_QA__.create());
        expect(fresh).not.toBe(id);
        expect(await p.evaluate(id => (window as any).__SECURITY_QA__.open(id, 'TESTONLY-rescue'), id)).toBe('TESTONLY-payload');
    }
    finally {
        await source.close();
        await target.close();
        await stopServer(server);
    }
});
