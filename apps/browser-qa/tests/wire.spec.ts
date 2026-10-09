import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runtime, origin, startServer, stopServer, launch } from './lifecycle';
const vectors = Object.fromEntries(['canonical', 'protocol', 'nesting', 'kernel_cases'].map(name => [name, JSON.parse(readFileSync(resolve('../../fixtures/sync/v1', name + '.json'), 'utf8'))]));
test('冻结 wire 向量在真实浏览器保持 bytes precision digest revisions', async () => {
    const server = await startServer();
    const context = await launch(resolve(runtime, 'profiles', `wire-${Date.now()}`));
    try {
        const p = await context.newPage();
        await p.goto(origin);
        expect(await p.evaluate(() => typeof (window as any).__WIRE_QA__)).toBe('object');
        const result = await p.evaluate(async (vectors) => {
            const w = (window as any).__WIRE_QA__;
            const checks: string[] = [];
            const equal = (a: any, b: any, name: string) => { if (JSON.stringify(a) !== JSON.stringify(b))
                throw Error(name); checks.push(name); };
            const rejects = (f: () => any, name: string) => { try {
                f();
            }
            catch {
                checks.push(name);
                return;
            } throw Error('accepted ' + name); };
            const hex = (b: Uint8Array) => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
            for (const v of vectors.canonical) {
                equal(new TextDecoder().decode(w.canonicalBytes(v.input)), v.canonical, v.name + ' bytes');
                equal(hex(w.canonicalBytes(v.input)), v.hex, v.name + ' hex');
                equal(await w.digest(v.input), v.sha256, v.name + ' digest');
            }
            for (const c of vectors.protocol) {
                if (c.valid) {
                    const tx = w.validateTransaction(w.strictLoads(c.raw), c.context);
                    equal(await w.transactionDigest(tx), c.digest, c.name);
                    equal(await Promise.all(tx.changes.map(w.revision)), c.revisions, c.name + ' revisions');
                }
                else
                    rejects(() => w.validateTransaction(w.strictLoads(c.raw), c.context), c.name);
            }
            for (const c of vectors.nesting) {
                let value: any = 0;
                for (let i = 0; i < c.depth; i++)
                    value = [value];
                if (c.valid) {
                    equal(new TextDecoder().decode(w.canonicalBytes(w.strictLoads(c.raw))), c.raw, c.name);
                    equal(new TextDecoder().decode(w.canonicalBytes(value)), c.raw, c.name + ' direct');
                }
                else {
                    rejects(() => w.canonicalBytes(value), c.name);
                    rejects(() => w.strictLoads(c.raw), c.name);
                }
            }
            for (const c of vectors.kernel_cases)
                for (const step of c.steps) {
                    const tx = w.strictLoads(step.raw);
                    equal(hex(w.canonicalBytes(tx)), step.canonical_hex, c.name);
                    equal(await w.digest(tx), step.digest, c.name);
                    equal(await Promise.all(tx.changes.map(w.digest)), step.revisions, c.name);
                    if (step.wire_valid)
                        w.validateTransaction(tx, step.context);
                    else {
                        let code;
                        try {
                            w.validateTransaction(tx, step.context);
                        }
                        catch (e) {
                            code = (e as any).code;
                        }
                        equal(code, step.wire_error, c.name);
                    }
                }
            for (const [a, b] of [['1', '1.00'], ['1e0', '1.0'], ['1.60', '1.600'], ['-0', '0e99'], ['9e18', '9000000000000000000']]) {
                equal(w.scientificEqual(a, b), true, 'decimal equality');
                equal((await w.digest({ value: a })) !== (await w.digest({ value: b })), true, 'decimal identity');
            }
            equal(w.scientificEqual('9007199254740992', '9007199254740993'), false, 'precision');
            for (const raw of ['{"x":1,"\\u0078":2}', '1.0', '1e0', '-0', '9007199254740992', 'NaN', '"\\ud800"', '[] trailing'])
                rejects(() => w.strictLoads(raw), 'strict');
            for (const v of ['1e100001', '1'.repeat(1025), '+1', '01', '1.'])
                rejects(() => w.scientificEqual(v, '1'), 'decimal reject');
            const change = structuredClone(w.strictLoads(vectors.protocol[0].raw).changes[0]);
            change.object_type = 'ResearchRun';
            change.payload = { title: 'SYNTHETIC', scientific_outcome: 'unknown' };
            w.validateChange(change);
            change.payload.is_highlighted = true;
            rejects(() => w.validateChange(change), 'highlight needs adapter');
            return { checks: checks.length, canonical: vectors.canonical.length, protocol: vectors.protocol.length, nesting: vectors.nesting.length, kernel: vectors.kernel_cases.length, steps: vectors.kernel_cases.flatMap((c: any) => c.steps).length };
        }, vectors);
        expect(result).toMatchObject({ canonical: 26, protocol: 59, nesting: 3, kernel: 10, steps: 20 });
        console.log(JSON.stringify(result));
    }
    finally {
        await context.close();
        await stopServer(server);
    }
});
