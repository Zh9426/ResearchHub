import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, delimiter } from 'node:path';
import { launch, closeBrowser, stopServer } from '../tests/lifecycle';
const root = resolve('../..');
const attempt = process.env.RH_B1_ATTEMPT!;
const dir = resolve(root, 'storage/runtime/browser-sync-qa/security', attempt);
const profile = resolve(dir, 'profile');
let context: BrowserContext, p: Page, server: ChildProcess, material: any, proof: any, noteOp: string;
const envelopes: any[] = [];
function oracle(action: string, data: any) { mkdirSync(dir, { recursive: true }); const input = resolve(dir, `${action}-input.TEST_ONLY.json`), output = resolve(dir, `${action}-output.TEST_ONLY.json`); writeFileSync(input, JSON.stringify({ action, ...data })); const python = process.env.RH_QA_PYTHON ?? resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'); const child = spawnSync(python, ['tests/secure_sync/browser_security_oracle.py', input, output], { cwd: root, env: { ...process.env, PYTHONPATH: [root, resolve(root, 'apps/api')].join(delimiter) }, encoding: 'utf8' }); writeFileSync(resolve(dir, `${action}-oracle.log`), child.stdout + child.stderr); expect(child.status, 'Python oracle exit status; inspect ignored stage log').toBe(0); return JSON.parse(readFileSync(output, 'utf8')); }
test.describe.serial('B1 actual Chromium formal security', () => {
    test.beforeAll(async () => {
        mkdirSync(dir, { recursive: true });
        server = spawn(process.execPath, ['scripts/server.mjs'], { env: { ...process.env, RH_QA_PROFILE: 'sync' }, stdio: 'pipe' });
        await new Promise<void>((ok, no) => {
            server.stdout!.on('data', d => {
                if (String(d).includes('QA_READY'))
                    ok();
            });
            server.once('error', no);
            server.once('exit', c => no(Error(`server ${c}`)));
        });
        context = await launch(profile);
        p = await context.newPage();
        await p.goto('http://127.0.0.1:3314');
        await p.getByRole('button', { name: '初始化合成工作区', exact: true }).click();
        await p.waitForFunction(() => !!(window as any).__B1_TEST_ONLY__);
        const setup = await p.evaluate(async () => { const q = (window as any).__B1_TEST_ONLY__; return { device: await q.publicDevice(), semanticProject: (await q.commands.snapshot()).projects.find((x: any) => x.route_alias === 'generic').id }; });
        expect(setup.device.nonextractable).toBe(true);
        material = oracle('init', setup);
        await p.evaluate(x => (window as any).__B1_TEST_ONLY__.install(x), material);
        writeFileSync(resolve(dir, 'versions.json'), JSON.stringify({ node: process.version, chromium: context.browser()!.version(), hpke: '1.9.0', retries: 0 }));
    });
    test.afterAll(async () => {
        const results = await Promise.allSettled([context ? closeBrowser(context) : Promise.resolve(), server ? stopServer(server) : Promise.resolve()]);
        const errors = results.filter(r => r.status === 'rejected');
        if (errors.length)
            throw new AggregateError(errors.map(r => (r as PromiseRejectedResult).reason), 'B1 cleanup failed');
    });
    test('fixed v1 + independent Python v2 HPKE, signatures, challenge, nonextractable keys', async () => {
        const f = JSON.parse(readFileSync(resolve(root, 'fixtures/sync/secure-v1/transaction-envelope.TEST_ONLY.json'), 'utf8'));
        const fixed = await p.evaluate(x => (window as any).__B1_TEST_ONLY__.fixed(x), f);
        expect(fixed.canonical).toBe(f.plaintext_canonical_hex);
        const result = await p.evaluate(async (m: any) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), d = await v.device();
            const opened = await v.openTransaction(m.pythonEnvelope, m.pythonTransaction.project_id);
            const proof = await q.security.answerChallenge(m.challenge, m.chain[0], d, { confirmation: q.security.confirmation(m.challenge), now: 1100 });
            let denied = 0;
            for (const key of [d.signing.privateKey, d.recipient.privateKey]) {
                try {
                    await crypto.subtle.exportKey('pkcs8', key);
                }
                catch {
                    denied++;
                }
            }
            return { opened, proof, denied };
        }, material);
        expect(result.opened).toEqual(material.pythonTransaction);
        expect(result.denied).toBe(2);
        proof = result.proof;
    });
    test('real LocalCommandService Note Run star mapping seals exact bytes; Python opens', async () => {
        await p.getByRole('button', { name: '新建 Note', exact: true }).click();
        await p.getByLabel('标题', { exact: true }).fill('SYNTHETIC 安全笔记');
        await p.getByRole('textbox', { name: '笔记正文', exact: true }).fill('  中文 🧪 e\u0301\n\t保留空白\n');
        await p.getByRole('button', { name: '保存到本机', exact: true }).click();
        await expect(p.getByTestId('local-save')).toHaveText('已保存到本机');
        const result = await p.evaluate(async () => {
            const q = (window as any).__B1_TEST_ONLY__;
            const before = await q.commands.snapshot(), project = before.projects.find((x: any) => x.route_alias === 'generic');
            const note = before.operations[0];
            const run = await q.commands.save({ id: crypto.randomUUID(), project_id: project.id, kind: 'Run', local_format_version: 1, local_edit_version: 0, title: 'SYNTHETIC Run', run_type: project.module_snapshot.run_types[0].id, objective: ' 空白 ', observation: '实验 🧪', status: 'failed', scientific_outcome: 'unknown', is_highlighted: false, highlight_type: '', highlight_note: '', context_data: {} });
            await q.commands.setHighlight(run.id, run.local_edit_version, { is_highlighted: true, highlight_type: '', highlight_note: ' 星标 🧪 ' });
            const s = await q.commands.snapshot(), out = [];
            for (const op of s.operations.slice().sort((a: any, b: any) => a.payload.local_edit_version - b.payload.local_edit_version)) {
                const mapping = await q.adapter.convert(op.id);
                const sealed = await q.sealer.seal(op.id);
                const repeated = await q.sealer.seal(op.id);
                const ready = await q.sealer.ready(op.id);
                out.push({ env: await q.security.decodeEnvelope(ready), same: q.security.equal(sealed.envelope, repeated.envelope), tx: mapping.transaction });
            }
            return { out, noteOp: note.id };
        });
        noteOp = result.noteOp;
        expect(result.out).toHaveLength(3);
        expect(result.out.every((x: any) => x.same)).toBe(true);
        expect(result.out.find((x: any) => x.tx.changes[0].object_type === 'Note')!.tx.changes[0].payload.content).toBe('  中文 🧪 e\u0301\n\t保留空白\n');
        expect(result.out.find((x: any) => x.tx.changes[0].operation === 'update')!.tx.changes[0].payload.is_highlighted).toBe(true);
        envelopes.push(...result.out.map((x: any) => x.env));
        const verified = oracle('verify', { proof, envelopes });
        expect(verified).toEqual({ verified_envelopes: 3, verified_pairing_proof: true });
    });
    test('reopen persists CryptoKeys; dual tabs CAS consume nonces; sealed recovery copies exact bytes', async () => {
        await closeBrowser(context);
        context = await launch(profile);
        p = await context.newPage();
        await p.goto('http://127.0.0.1:3314');
        await p.waitForFunction(() => !!(window as any).__B1_TEST_ONLY__);
        const reopen = await p.evaluate(async (id) => { const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), d = await v.device(); const raw = await q.sealer.ready(id), env = await q.security.decodeEnvelope(raw), mapping = await q.sealer.inspect(id); await v.openTransaction(env, mapping.identity.projectId); return { nonextractable: !d.signing.privateKey.extractable && !d.recipient.privateKey.extractable, ready: q.security.hexEncode(raw) }; }, noteOp);
        expect(reopen.nonextractable).toBe(true);
        const fixture = JSON.parse(readFileSync(resolve(root, 'fixtures/sync/secure-v1/transaction-envelope.TEST_ONLY.json'), 'utf8'));
        const imported = await p.evaluate(x => (window as any).__B1_TEST_ONLY__.fixed(x), fixture);
        expect(imported.reused).toBe(true);
        expect(imported.unwrapMatches).toBe(true);
        expect(imported.privateNonextractable).toBe(true);
        const prepared = await p.evaluate(async (id) => { const q = (window as any).__B1_TEST_ONLY__, s = await q.commands.snapshot(), o = s.objects.find((x: any) => x.kind === 'Note'); await q.commands.save({ ...o, body: o.body + '后继' }); const next = (await q.commands.snapshot()).operations.find((x: any) => x.object_id === o.id && x.payload.local_edit_version === 2); await q.adapter.convert(next.id); return next.id; }, noteOp);
        const interrupted = await p.evaluate(async (id) => { const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id); return s.vault.reserve(s.identity); }, prepared);
        await closeBrowser(context);
        context = await launch(profile);
        p = await context.newPage();
        await p.goto('http://127.0.0.1:3314');
        await p.waitForFunction(() => !!(window as any).__B1_TEST_ONLY__);
        const tab = await context.newPage();
        await tab.goto('http://127.0.0.1:3314');
        await tab.waitForFunction(() => !!(window as any).__B1_TEST_ONLY__);
        const reserve = (page: Page) => page.evaluate(async (id) => { const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id); return s.vault.reserve(s.identity); }, prepared);
        const both = await Promise.all([reserve(p), reserve(tab)]);
        const [a, b] = both.sort((x, y) => x.nonce.localeCompare(y.nonce));
        expect(a.nonce > interrupted.nonce).toBe(true);
        expect(a.nonce).not.toBe(b.nonce);
        expect(a.token).not.toBe(b.token);
        const altered = await p.evaluate(async ({ id, b }) => {
            const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id);
            try {
                await s.vault.seal({ ...b, nonce: '000000020000000000000001' }, s.mapping.transaction);
                return 'accepted';
            }
            catch (e) {
                return String(e);
            }
        }, { id: prepared, b });
        expect(altered).toContain('STALE_PREPARATION_TOKEN');
        const stale = await p.evaluate(async ({ id, a }) => {
            const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id);
            try {
                await s.vault.seal(a, s.mapping.transaction);
                return 'accepted';
            }
            catch (e) {
                return String(e);
            }
        }, { id: prepared, a });
        expect(stale).toContain('STALE_PREPARATION_TOKEN');
        const inflight = await p.evaluate(async ({ id, b }) => {
            const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id), nativeSign = crypto.subtle.sign.bind(crypto.subtle);
            let entered!: () => void, release!: () => void;
            const enteredGate = new Promise<void>(ok => entered = ok), releaseGate = new Promise<void>(ok => release = ok);
            (crypto.subtle as any).sign = async (...args: any[]) => { entered(); await releaseGate; return (nativeSign as any)(...args); };
            try {
                const pending = s.vault.seal(b, s.mapping.transaction).then(() => 'ACCEPTED', (e: any) => String(e));
                await enteredGate;
                const replacement = await s.vault.reserve(s.identity);
                release();
                const result = await pending;
                return { result, replacement };
            }
            finally {
                release();
                crypto.subtle.sign = nativeSign;
            }
        }, { id: prepared, b });
        expect(inflight.result).toContain('STALE_PREPARATION_TOKEN');
        expect(inflight.replacement.nonce).not.toBe(b.nonce);
        const committed = await tab.evaluate(async ({ id, b }) => { const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id); const x = await s.vault.seal(b, s.mapping.transaction); return { hex: q.security.hexEncode(x.sealed), nonce: x.nonce }; }, { id: prepared, b: inflight.replacement });
        const lostSeal = await p.evaluate(async (id) => {
            const q = (window as any).__B1_TEST_ONLY__, s = await q.sealer.inspect(id), v = s.vault, original = await v.preparation(id);
            const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            let marker: any;
            await new Promise<void>((ok, no) => { const tx = db.transaction(['preparations', 'meta'], 'readwrite'); const r = tx.objectStore('meta').get(`prepare:${id}`); r.onsuccess = () => { marker = r.result; tx.objectStore('preparations').put({ ...original, sealed: null }); }; tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            let result = 'ACCEPTED';
            try {
                await v.reserve(s.identity);
            }
            catch (e) {
                result = String(e);
            }
            await new Promise<void>((ok, no) => { const tx = db.transaction(['preparations', 'meta'], 'readwrite'); tx.objectStore('preparations').put(original); tx.objectStore('meta').put(marker); tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            db.close();
            return result;
        }, prepared);
        expect(lostSeal).toContain('PREPARATION_MISSING_OR_CORRUPT');
        const recovered = await p.evaluate(async (id) => {
            const q = (window as any).__B1_TEST_ONLY__, r = await q.sealer.seal(id), s = await q.sealer.inspect(id), a = await s.vault.reserve(s.identity), b = await s.vault.reserve(s.identity);
            let collision = '';
            try {
                await s.vault.reserve({ ...s.identity, messageId: crypto.randomUUID() });
            }
            catch (e) {
                collision = String(e);
            }
            return { hex: q.security.hexEncode(r.envelope), same: a.token === b.token && a.nonce === b.nonce, collision };
        }, prepared);
        expect(recovered.hex).toBe(committed.hex);
        expect(recovered.same).toBe(true);
        expect(recovered.collision).toContain('IDENTITY_COLLISION');
        await tab.close();
    });
    test('signed ciphertext substitution, missing key authorization and same-epoch fork are rejected', async () => {
        const result = await p.evaluate(async ({ m, id }) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), s = await q.sealer.inspect(id);
            const rejected: any = {};
            try {
                await v.pin(m.ownerRoot, m.recoveryRoot, [m.chain[0], m.fork]);
            }
            catch (e) {
                rejected.fork = String(e);
            }
            const edit = async (store: string, work: (st: IDBObjectStore, ok: (v: any) => void) => void) => {
                const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
                try {
                    return await new Promise<any>((ok, no) => { const tx = db.transaction(store, 'readwrite'); let value: any; work(tx.objectStore(store), x => value = x); tx.oncomplete = () => ok(value); tx.onabort = () => no(tx.error); });
                }
                finally {
                    db.close();
                }
            };
            const original = await v.preparation(s.identity.prepareId);
            const other = await edit('preparations', (st, ok) => { st.getAll().onsuccess = e => ok((e.target as IDBRequest).result.find((x: any) => x.id !== original.id && x.sealed)); });
            await edit('preparations', (st, ok) => { st.put({ ...original, sealed: other.sealed, sealedDigest: other.sealedDigest }); ok(null); });
            const savedMarker = await edit('meta', (st, ok) => { st.get(`prepare:${original.id}`).onsuccess = e => { const marker = (e.target as IDBRequest).result; ok(marker); st.put({ ...marker, sealedDigest: other.sealedDigest }); }; });
            try {
                await v.ready(original.id, other.sealed);
            }
            catch (e) {
                rejected.substitution = String(e);
            }
            await edit('preparations', (st, ok) => { st.put(original); ok(null); });
            await edit('meta', (st, ok) => { st.put(savedMarker); ok(null); });
            const keyId = `${s.identity.opaqueProjectId}:${s.identity.keyEpoch}`;
            const key = await edit('keys', (st, ok) => { st.get(keyId).onsuccess = e => { ok((e.target as IDBRequest).result); st.delete(keyId); }; });
            try {
                await v.acceptGrant(m.grant);
            }
            catch (e) {
                rejected.missingKey = String(e);
            }
            try {
                await v.acceptGrant(m.changedGrant);
            }
            catch (e) {
                rejected.changedKey = String(e);
            }
            await edit('keys', (st, ok) => { st.put(key); ok(null); });
            const before = await v.preparation(original.id);
            await v.acceptGrant(m.grant);
            const after = await v.preparation(original.id);
            return { rejected, same: before.nonce === after.nonce && before.token === after.token };
        }, { m: material, id: noteOp });
        expect(result.rejected.fork).toContain('MEMBERSHIP_FORK');
        expect(result.rejected.substitution).toContain('ENVELOPE_BINDING_MISMATCH');
        expect(result.rejected.missingKey).toContain('PROJECT_KEY_MISSING_OR_CORRUPT');
        expect(result.rejected.changedKey).toContain('PROJECT_KEY_IDENTITY_COLLISION');
        expect(result.same).toBe(true);
    });
    test('missing authorization markers and mutated business READY identities fail closed', async () => {
        const result = await p.evaluate(async (id) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), inspected = await q.sealer.inspect(id), original = inspected.mapping;
            const edit = async (name: string, store: string, work: (st: IDBObjectStore, done: (v: any) => void) => void) => {
                const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
                try {
                    return await new Promise<any>((ok, no) => { const tx = db.transaction(store, 'readwrite'); let value: any; work(tx.objectStore(store), x => value = x); tx.oncomplete = () => ok(value); tx.onabort = () => no(tx.error); });
                }
                finally {
                    db.close();
                }
            };
            const failures: any = {};
            const marker = `authorization:${inspected.identity.opaqueProjectId}:${inspected.identity.keyEpoch}`;
            const saved = await edit(v.name, 'meta', (st, done) => { st.get(marker).onsuccess = e => { done((e.target as IDBRequest).result); st.delete(marker); }; });
            for (const [name, call] of [['keyInfo', () => v.keyInfo(inspected.identity.opaqueProjectId, inspected.identity.keyEpoch)], ['reserve', () => v.reserve(inspected.identity)], ['seal', async () => v.seal(await v.preparation(id), original.transaction)], ['ready', () => v.ready(id, original.envelope)]] as const) {
                try {
                    await call();
                    failures[name] = 'ACCEPTED';
                }
                catch (e) {
                    failures[name] = String(e);
                }
            }
            await edit(v.name, 'meta', (st, done) => { st.put(saved); done(null); });
            const tombstoneId = `key:${inspected.identity.keyFingerprint}:${inspected.identity.prefix}`;
            const tombstone = await edit(v.name, 'meta', (st, done) => { st.get(tombstoneId).onsuccess = e => { const row = (e.target as IDBRequest).result; done(row); st.put({ ...row, prefix: row.prefix + 1 }); }; });
            try {
                await v.reserve(inspected.identity);
                failures.corruptTombstone = 'ACCEPTED';
            }
            catch (e) {
                failures.corruptTombstone = String(e);
            }
            await edit(v.name, 'meta', (st, done) => { st.put(tombstone); done(null); });
            for (const field of ['operation_id', 'prepare_id', 'transaction_id', 'message_id', 'transaction_digest', 'object_id', 'binding_generation']) {
                const damaged = { ...original, [field]: field === 'transaction_digest' ? 'f'.repeat(64) : field === 'binding_generation' ? 999 : crypto.randomUUID() };
                await edit('researchhub-browser-sync-qa-business-v1', 'meta', (st, done) => { st.put(damaged); done(null); });
                try {
                    await q.sealer.ready(id);
                    failures[field] = 'ACCEPTED';
                }
                catch (e) {
                    failures[field] = String(e);
                }
                await edit('researchhub-browser-sync-qa-business-v1', 'meta', (st, done) => { st.put(original); done(null); });
            }
            const preparation = await v.preparation(id);
            await edit(v.name, 'preparations', (st, done) => { st.delete(id); done(null); });
            try {
                await q.sealer.seal(id);
                failures.missingPreparation = 'ACCEPTED';
            }
            catch (e) {
                failures.missingPreparation = String(e);
            }
            await edit(v.name, 'preparations', (st, done) => { st.put(preparation); done(null); });
            await edit('researchhub-browser-sync-qa-business-v1', 'meta', (st, done) => { st.put(original); done(null); });
            return failures;
        }, noteOp);
        expect(result.corruptTombstone).toContain('NONCE_AUTHORIZATION_MISSING_OR_CORRUPT');
        expect(result.missingPreparation).toContain('PREPARATION_MISSING_OR_CORRUPT');
        for (const field of ['keyInfo', 'reserve', 'seal', 'ready'])
            expect(result[field], field).toContain('NONCE_AUTHORIZATION_MISSING_OR_CORRUPT');
        for (const field of ['operation_id', 'prepare_id', 'transaction_id', 'message_id', 'transaction_digest', 'object_id', 'binding_generation'])
            expect(result[field], field).not.toBe('ACCEPTED');
    });
    test('matching counter rollback below a retained reservation fails closed without repairing counters', async () => {
        const result = await p.evaluate(async () => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), snapshot = await q.commands.snapshot(), project = snapshot.projects.find((x: any) => x.route_alias === 'generic');
            const note = await q.commands.save({ id: crypto.randomUUID(), project_id: project.id, kind: 'Note', local_format_version: 1, local_edit_version: 0, title: 'SYNTHETIC 高水位', body: '保留待发' });
            const op = (await q.commands.snapshot()).operations.find((x: any) => x.object_id === note.id);
            await q.adapter.convert(op.id);
            const inspected = await q.sealer.inspect(op.id), key = `${inspected.identity.keyFingerprint}:${inspected.identity.prefix}`;
            const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            let original: any;
            await new Promise<void>((ok, no) => { const tx = db.transaction(['ledgers', 'mirrors'], 'readwrite'), r = tx.objectStore('ledgers').get(key); r.onsuccess = () => { original = r.result; const lowered = { ...original, counter: original.counter - 1 }; tx.objectStore('ledgers').put(lowered); tx.objectStore('mirrors').put(lowered); }; tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            let rejection = 'ACCEPTED';
            try {
                await v.reserve(inspected.identity);
            }
            catch (e) {
                rejection = String(e);
            }
            const after = await new Promise<any>((ok, no) => { const tx = db.transaction('ledgers'), r = tx.objectStore('ledgers').get(key); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            if (rejection !== 'ACCEPTED')
                await new Promise<void>((ok, no) => { const tx = db.transaction(['ledgers', 'mirrors'], 'readwrite'); tx.objectStore('ledgers').put(original); tx.objectStore('mirrors').put(original); tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            db.close();
            return { rejection, unchanged: after.counter === original.counter - 1 };
        });
        expect(result.rejection).toContain('NONCE_COUNTER_ROLLBACK');
        expect(result.unchanged).toBe(true);
    });
    test('last safe nonce seals and remains retryable; exhaustion cannot reserve another nonce', async () => {
        const result = await p.evaluate(async (originalOperation) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), s = await q.commands.snapshot(), note = s.objects.find((x: any) => x.id === s.operations.find((o: any) => o.id === originalOperation).object_id);
            await q.commands.save({ ...note, body: note.body + '极限' });
            const op = (await q.commands.snapshot()).operations.find((x: any) => x.object_id === note.id && x.payload.local_edit_version === 3);
            await q.adapter.convert(op.id);
            const inspect = await q.sealer.inspect(op.id), ledgerId = `${inspect.identity.keyFingerprint}:${inspect.identity.prefix}`;
            const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            await new Promise<void>((ok, no) => { const tx = db.transaction(['ledgers', 'mirrors'], 'readwrite'); const r = tx.objectStore('ledgers').get(ledgerId); r.onsuccess = () => { const row = { ...r.result, counter: Number.MAX_SAFE_INTEGER - 1 }; tx.objectStore('ledgers').put(row); tx.objectStore('mirrors').put(row); }; tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            db.close();
            const reserved = await v.reserve(inspect.identity);
            await v.seal(reserved, inspect.mapping.transaction);
            await q.sealer.seal(op.id);
            await q.sealer.ready(op.id);
            const repeated = await v.reserve(inspect.identity);
            const current = (await q.commands.snapshot()).objects.find((x: any) => x.id === note.id);
            await q.commands.save({ ...current, body: current.body + '保留待发' });
            const next = (await q.commands.snapshot()).operations.find((x: any) => x.object_id === note.id && x.payload.local_edit_version === 4);
            await q.adapter.convert(next.id);
            let exhausted = '';
            try {
                await q.sealer.seal(next.id);
            }
            catch (e) {
                exhausted = String(e);
            }
            return { counter: reserved.nonce.slice(8), same: reserved.nonce === repeated.nonce && reserved.token === repeated.token, exhausted };
        }, noteOp);
        expect(result.counter).toBe('001fffffffffffff');
        expect(result.same).toBe(true);
        expect(result.exhausted).toContain('NONCE_EXHAUSTED');
    });
    test('old chains, tampered READY, missing and corrupt ledger fail closed preserving operations', async () => {
        const result = await p.evaluate(async ({ m, id }) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), before = await q.commands.snapshot();
            const rejected: any = {};
            try {
                await v.pin(m.ownerRoot, m.recoveryRoot, [m.chain[0]]);
            }
            catch (e) {
                rejected.rollback = String(e);
            }
            const s = await q.sealer.inspect(id);
            const raw = await q.sealer.ready(id);
            raw[0] ^= 1;
            try {
                await v.ready(s.identity.prepareId, raw);
            }
            catch (e) {
                rejected.ready = String(e);
            }
            const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            const key = `${s.identity.keyFingerprint}:${s.identity.prefix}`;
            await new Promise<void>((ok, no) => { const tx = db.transaction('mirrors', 'readwrite'); const r = tx.objectStore('mirrors').get(key); r.onsuccess = () => { (window as any).__B1_SAVED_MIRROR_TEST_ONLY__ = r.result; tx.objectStore('mirrors').delete(key); }; tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            db.close();
            try {
                await q.sealer.ready(id);
            }
            catch (e) {
                rejected.ledger = String(e);
            }
            try {
                await v.acceptGrant(m.grant);
            }
            catch (e) {
                rejected.reimport = String(e);
            }
            const restore = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open(v.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
            await new Promise<void>((ok, no) => { const tx = restore.transaction('mirrors', 'readwrite'); tx.objectStore('mirrors').put((window as any).__B1_SAVED_MIRROR_TEST_ONLY__); tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
            restore.close();
            delete (window as any).__B1_SAVED_MIRROR_TEST_ONLY__;
            return { rejected, unchanged: JSON.stringify(before) === JSON.stringify(await q.commands.snapshot()) };
        }, { m: material, id: noteOp });
        expect(result.unchanged).toBe(true);
        expect(result.rejected.rollback).toContain('ROLLBACK_DETECTED');
        expect(result.rejected.ready).toContain('IDENTITY_COLLISION');
        expect(result.rejected.ledger).toContain('NONCE_LEDGER_MISSING_OR_CORRUPT');
        expect(result.rejected.reimport).toContain('NONCE_LEDGER_MISSING_OR_CORRUPT');
    });
    test('full pinned revoke chain blocks current send, retains historical quarantine and checkpoint validation', async () => {
        const result = await p.evaluate(async ({ m, id }) => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), before = await v.preparation(id);
            await q.security.verifyCheckpoint(m.checkpoint, m.chain[1]);
            await v.pin(m.ownerRoot, m.recoveryRoot, [...m.chain, m.revoked]);
            const other = (await q.commands.snapshot()).operations.find((x: any) => x.object_type === 'Run' && x.payload.local_edit_version === 1);
            let send = '', reseal = '';
            try {
                await q.sealer.ready(other.id);
            }
            catch (e) {
                send = String(e);
            }
            try {
                await q.sealer.seal(id);
            }
            catch (e) {
                reseal = String(e);
            }
            const env = await q.security.decodeEnvelope(before.sealed);
            const historical = await q.security.verifyHistoricalEnvelope(env, m.chain[1], m.revoked);
            await q.security.verifyCheckpoint(m.checkpoint, m.chain[1]);
            const after = await v.preparation(id);
            return { send, reseal, historical, blocked: (await q.sealer.inspect(other.id)).mapping.transport, same: q.security.equal(before.sealed, after.sealed) };
        }, { m: material, id: noteOp });
        expect(result.send).toMatch(/REVOKED_DEVICE|STALE_MEMBERSHIP_OR_KEY_EPOCH/);
        expect(result.reseal).toMatch(/REVOKED_DEVICE|STALE_MEMBERSHIP_OR_KEY_EPOCH/);
        expect(result.historical.status).toBe('QUARANTINED');
        expect(result.same).toBe(true);
        expect(result.blocked).toBe('BLOCKED');
    });
    test('complete vault loss cannot regenerate existing identity or consume pending work', async () => {
        const result = await p.evaluate(async () => {
            const q = (window as any).__B1_TEST_ONLY__, v = await q.sealer.vault(), before = await q.commands.snapshot();
            await new Promise<void>((ok, no) => { const r = indexedDB.deleteDatabase(v.name); r.onsuccess = () => ok(); r.onerror = () => no(r.error); r.onblocked = () => no(Error('delete blocked')); });
            let blocked = '';
            try {
                await q.sealer.initialize();
            }
            catch (e) {
                blocked = String(e);
            }
            return { blocked, unchanged: JSON.stringify(before) === JSON.stringify(await q.commands.snapshot()), databases: (await indexedDB.databases()).map(x => x.name) };
        });
        expect(result.blocked).toMatch(/VAULT_MISSING/);
        expect(result.unchanged).toBe(true);
        expect(result.databases).not.toContain('researchhub-browser-sync-qa-vault-v1');
    });
});
