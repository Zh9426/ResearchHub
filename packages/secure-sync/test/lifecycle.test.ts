/** Runtime keys generated in memory; PUBLIC TEST ONLY fixed inputs only in interop. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync } from 'node:fs';
import { randomBytes, randomUUID } from 'node:crypto';
import { NonceVault } from '../src/nonce.ts';
import { canonicalBytes, digest, strictLoads } from '../../sync-protocol/src/canonical.ts';
import { DatabaseSync } from 'node:sqlite';
async function modules() {
    assert.ok(existsSync(new URL('../src/keys.ts', import.meta.url)), 'trusted lifecycle not implemented');
    return {
        k: await import('../src/keys.ts'), p: await import('../src/pairing.ts'), c: await import('../src/checkpoint.ts'), a: await import('../src/artifacts.ts')
    };
}

test('Node committed Kit restart restores latest cp and recovery commits atomically', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-kit-persist-') + '/trusted.sqlite', store = new k.TrustedStore(path);
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], cp1 = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await kit.updateAnchor(manifest, cp0, store);
    await kit.updateAnchor(manifest, cp1, store, rows);
    assert.equal(typeof (k.RecoveryKit as any).restoreFromTrustedStore, 'function', 'committed public Kit metadata restore API required');
    const restore = (store: InstanceType<typeof k.TrustedStore>) => k.RecoveryKit.restoreFromTrustedStore(kit.signingSeed, kit.recipientSeed, kit.deviceId, manifest.opaque_project_id, store);
    const cpStore = new c.CheckpointStore(path + '.checkpoint');
    cpStore.pin(manifest.opaque_project_id);
    await cpStore.advance(cp0, manifest, []); await cpStore.advance(cp1, manifest, rows);
    assert.equal(digest(await new c.CheckpointStore(path + '.checkpoint').get(manifest.opaque_project_id)), digest(cp1));
    const reopened = new k.TrustedStore(path), loaded = await restore(reopened), key = randomBytes(32), backup = await k.makeRecoveryBackup(manifest, owner, kit, key);
    assert.notEqual(loaded, kit);
    assert.deepEqual(loaded.checkpointAnchor, cp1);
    assert.deepEqual(Buffer.from(await k.openRecoveryBackup(backup, reopened, loaded)), key);
    await assert.rejects(loaded.updateAnchor(manifest, cp0, reopened), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const before = JSON.stringify(loaded), db = new DatabaseSync(path), beforeRows = db.prepare('SELECT * FROM kit_anchors').all();
    db.exec("CREATE TRIGGER fail_anchor BEFORE INSERT ON kit_anchors BEGIN SELECT RAISE(ABORT,'SYNTHETIC_ANCHOR_WRITE_FAILURE'); END");
    db.close();
    await assert.rejects(k.recover(reopened, loaded, await k.Device.generate()));
    assert.equal(JSON.stringify(loaded), before);
    assert.deepEqual(canonicalBytes(reopened.current(manifest.opaque_project_id)), canonicalBytes(manifest));
    const check = new DatabaseSync(path);
    assert.deepEqual(check.prepare('SELECT * FROM kit_anchors').all(), beforeRows);
    check.exec('DROP TRIGGER fail_anchor'); check.close();
    const recovered = await k.recover(reopened, loaded, await k.Device.generate()), again = await restore(new k.TrustedStore(path));
    assert.equal(again.checkpointAnchor!.cursor, 1);
    assert.equal(again.checkpointAnchor!.key_epoch, 2);
    assert.equal(again.manifestAnchor, (await import('../../sync-protocol/src/canonical.ts')).digest(recovered));
});

test('Node recovery rejects post-signature failure before committing manifest', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-kit-atomic-') + '/trusted.sqlite');
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    await kit.updateAnchor(manifest, await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), store);
    const invalidOwner = await k.Device.generate();
    invalidOwner.signingPublic = owner.signingPublic; // mismatch seed creates bad new-owner checkpoint
    const before = JSON.stringify(kit);
    await assert.rejects(k.recover(store, kit, invalidOwner));
    assert.deepEqual(canonicalBytes(store.current(manifest.opaque_project_id)), canonicalBytes(manifest));
    assert.equal(JSON.stringify(kit), before);
});

test('Node persistent Kit metadata rejects loss, corruption, rollback and wrong identity', async () => {
    const { k, c } = await modules();
    for (const mutation of ['missing', 'partial', 'signature', 'old_checkpoint', 'wrong_root', 'wrong_recipient', 'wrong_id', 'foreign_project', 'history_root', 'missing_history', 'revision_gap', 'epoch_bool', 'tail_loss', 'complete_old_cp']) {
        const owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-kit-corrupt-') + '/trusted.sqlite', store = new k.TrustedStore(path);
        await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
        const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], cp1 = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
        await kit.updateAnchor(manifest, cp0, store); await kit.updateAnchor(manifest, cp1, store, rows);
        let s = kit.signingSeed, r = kit.recipientSeed, id = kit.deviceId, project = manifest.opaque_project_id;
        const db = new DatabaseSync(path);
        if (mutation === 'missing') db.exec('DELETE FROM kit_anchors');
        else if (mutation === 'missing_history') db.exec('DELETE FROM manifests');
        else if (mutation === 'revision_gap') db.exec('DELETE FROM kit_anchors WHERE revision=1');
        else if (mutation === 'tail_loss') db.exec('DELETE FROM kit_anchors WHERE revision=2');
        else if (mutation === 'wrong_root') s = randomBytes(32);
        else if (mutation === 'wrong_recipient') r = randomBytes(32);
        else if (mutation === 'wrong_id') id = randomUUID();
        else if (mutation === 'foreign_project') project = randomUUID();
        else if (mutation === 'history_root') db.prepare('UPDATE roots SET owner=?').run((await k.Device.generate()).signingPublic);
        else {
            const row = db.prepare('SELECT revision,body FROM kit_anchors ORDER BY revision DESC LIMIT 1').get() as {revision: number; body: Uint8Array};
            const record = strictLoads(row.body) as Record<string, any>;
            if (mutation === 'partial') delete record.checkpoint_digest;
            else if (mutation === 'epoch_bool') record.key_epoch = true;
            else if (mutation === 'signature') { record.checkpoint.signature = 'A'.repeat(86); record.checkpoint_digest = digest(record.checkpoint); }
            else { record.checkpoint = cp0; record.checkpoint_digest = digest(cp0); if (mutation === 'complete_old_cp') record.rows = []; }
            db.prepare('UPDATE kit_anchors SET body=? WHERE revision=?').run(canonicalBytes(record), row.revision);
        }
        db.close();
        await assert.rejects(k.RecoveryKit.restoreFromTrustedStore(s, r, id, project, new k.TrustedStore(path)), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    }
});

test('Node journal and head failures leave both public tables and Kit memory unchanged', async () => {
    const { k, c } = await modules();
    for (const operation of ['update', 'recover']) for (const phase of ['journal_before', 'head_before', 'head_after']) {
        const owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-kit-fault-') + '/trusted.sqlite', store = new k.TrustedStore(path);
        await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
        const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], cp1 = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
        await kit.updateAnchor(manifest, cp0, store); await kit.updateAnchor(manifest, cp1, store, rows);
        const db = new DatabaseSync(path), journal = db.prepare('SELECT * FROM kit_anchors').all(), head = db.prepare('SELECT * FROM kit_anchor_heads').all(), before = JSON.stringify(kit);
        const [timing, action, table] = ({journal_before: ['BEFORE', 'INSERT', 'kit_anchors'], head_before: ['BEFORE', 'INSERT', 'kit_anchor_heads'], head_after: ['AFTER', 'UPDATE', 'kit_anchor_heads']} as Record<string, string[]>)[phase];
        db.exec(`CREATE TRIGGER fail_anchor ${timing} ${action} ON ${table} BEGIN SELECT RAISE(ABORT,'SYNTHETIC_ANCHOR_WRITE_FAILURE'); END`);
        db.close();
        if (operation === 'recover') {
            const chain = [await k.transition(manifest, owner, {add: (await k.Device.generate()).member('reader', 1)})];
            await assert.rejects(k.recover(store, kit, await k.Device.generate(), chain));
        } else {
            const nextRows = [{sequence: 2, envelope_digest: 'b'.repeat(64)}], cp2 = await c.signCheckpoint(manifest, owner, 2, c.extendChain(cp1.chain_digest, 1, nextRows));
            await assert.rejects(kit.updateAnchor(manifest, cp2, store, nextRows));
        }
        assert.equal(JSON.stringify(kit), before);
        assert.equal(digest(store.current(manifest.opaque_project_id)), digest(manifest));
        const check = new DatabaseSync(path);
        assert.deepEqual(check.prepare('SELECT * FROM kit_anchors').all(), journal);
        assert.deepEqual(check.prepare('SELECT * FROM kit_anchor_heads').all(), head);
        for (const row of journal) {
            const body = Buffer.from(row.body as Uint8Array);
            assert.equal(body.includes(Buffer.from(kit.signingSeed)), false);
            assert.equal(body.includes(Buffer.from(kit.recipientSeed)), false);
            assert.equal(body.includes(Buffer.from(Buffer.from(kit.signingSeed).toString('hex'))), false);
        }
        check.close();
        const loaded = await k.RecoveryKit.restoreFromTrustedStore(kit.signingSeed, kit.recipientSeed, kit.deviceId, manifest.opaque_project_id, new k.TrustedStore(path));
        assert.equal(digest(loaded.checkpointAnchor), digest(cp1));
        assert.equal(loaded.manifestAnchor, digest(manifest));
    }
});

test('Node initial Kit anchor rejects unvalidated rows before persistence', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-kit-row-schema-') + '/trusted.sqlite');
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64));
    await assert.rejects(kit.updateAnchor(manifest, cp0, store, [{SYNTHETIC_UNVALIDATED: 'qa'}]), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    assert.equal(kit.manifestAnchor, undefined);
});

test('Node SQL columns and complete signed history cannot revive revoked writer', async () => {
    const { k, c } = await modules(), wire = await import('../src/envelope.ts');
    for (const mutation of ['epoch', 'digest', 'project', 'duplicate_bootstrap', 'signature']) {
        const owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m1 = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-history-integrity-') + '/trusted.sqlite', store = new k.TrustedStore(path);
        await store.bootstrap(m1, owner.signingPublic, kit.signingPublic);
        const m2 = await k.transition(m1, owner, {add: b.member('writer', 1)}); await store.accept(m2);
        const m3 = await k.transition(m2, owner, {revoke: b.deviceId}); await store.accept(m3);
        await store.accept(m3); // exact retry must not append a duplicate
        await kit.updateAnchor(m3, await c.signCheckpoint(m3, owner, 0, '0'.repeat(64)), store);
        const key = randomBytes(32), nonce = new NonceVault(path + '.nonce'); nonce.registerNew(key, 1);
        const env = await wire.sealRecord({SYNTHETIC: 'writer'}, key, b.signingSeed, nonce, 1, {opaque_project_id: m1.opaque_project_id, sender_device_id: b.deviceId, membership_epoch: 2, key_epoch: 1, message_id: randomUUID()});
        assert.equal((await k.classifyEnvelope(store, env)).status, 'QUARANTINED');
        const db = new DatabaseSync(path);
        assert.equal((db.prepare('SELECT COUNT(*) AS n FROM manifests').get() as {n: number}).n, 3);
        if (mutation === 'duplicate_bootstrap') db.prepare('INSERT INTO manifests VALUES (?,?,?,?)').run(m1.opaque_project_id, 'e'.repeat(64), 4, canonicalBytes(m1));
        else if (mutation === 'signature') {
            const bad = {...m3, signature: 'A'.repeat(86)};
            db.prepare('UPDATE manifests SET digest=?,body=? WHERE epoch=3').run(digest(bad), canonicalBytes(bad));
        } else db.prepare(`UPDATE manifests SET ${mutation}=? WHERE epoch=3`).run(({epoch: 0, digest: 'f'.repeat(64), project: randomUUID()} as Record<string, string | number>)[mutation]);
        db.close();
        const reopened = new k.TrustedStore(path);
        if (mutation !== 'signature') {
            assert.throws(() => reopened.current(m1.opaque_project_id));
            assert.throws(() => reopened.history(m1.opaque_project_id, 1));
        }
        await assert.rejects(reopened.verifiedCurrent(m1.opaque_project_id));
        await assert.rejects(k.classifyEnvelope(reopened, env));
        await assert.rejects(reopened.accept(m3));
        await assert.rejects(k.RecoveryKit.restoreFromTrustedStore(kit.signingSeed, kit.recipientSeed, kit.deviceId, m1.opaque_project_id, reopened));
    }
});

test('Node signed checkpoint cannot roll either epoch back at same or growing cursor', async () => {
    const { k, c } = await modules();
    for (const growing of [false, true]) {
        const owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m1 = await k.bootstrap(randomUUID(), owner, kit), m2 = await k.transition(m1, owner, {add: b.member('writer', 1)}), m3 = await k.transition(m2, owner, {revoke: b.deviceId}), path = mkdtempSync('../../storage/runtime/s2-cp-epochs-') + '/cp.sqlite';
        const rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], chain = c.extendChain('0'.repeat(64), 0, rows), latest = await c.signCheckpoint(m3, owner, 1, chain), store = new c.CheckpointStore(path);
        store.pin(m1.opaque_project_id); await store.advance(latest, m3, rows);
        const extra = growing ? [{sequence: 2, envelope_digest: 'b'.repeat(64)}] : [], old = await c.signCheckpoint(m2, owner, 1 + extra.length, c.extendChain(chain, 1, extra));
        await assert.rejects(c.verifyAdvance(latest, old, m2, extra));
        await assert.rejects(new c.CheckpointStore(path).advance(old, m2, extra));
        assert.equal(digest(await store.get(m1.opaque_project_id)), digest(latest));
        await store.advance(latest, m3, []);
    }
});

test('Node SIGNED checkpoint storage cannot degrade to missing-field bootstrap', async () => {
    const { k, c } = await modules();
    for (const mutation of ['drop_epoch', 'drop_signature', 'three_fields', 'bool_epoch']) {
        const owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m = await k.bootstrap(randomUUID(), owner, kit), cp = await c.signCheckpoint(m, owner, 0, '0'.repeat(64)), path = mkdtempSync('../../storage/runtime/s2-cp-kind-') + '/cp.sqlite', store = new c.CheckpointStore(path);
        store.pin(m.opaque_project_id); await store.advance(cp, m, []);
        let bad = structuredClone(cp);
        if (mutation === 'drop_epoch') delete bad.key_epoch;
        else if (mutation === 'drop_signature') delete bad.signature;
        else if (mutation === 'bool_epoch') bad.membership_epoch = true;
        else bad = {opaque_project_id: cp.opaque_project_id, cursor: cp.cursor, chain_digest: cp.chain_digest};
        await assert.rejects(c.verifyAdvance(bad, cp, m, []));
        const db = new DatabaseSync(path); db.prepare('UPDATE anchors SET body=?').run(canonicalBytes(bad)); db.close();
        await assert.rejects(new c.CheckpointStore(path).advance(cp, m, []));
    }
});

test('Node public checkpoint helper requires explicit bootstrap and checks both epoch bounds', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m = await k.bootstrap(randomUUID(), owner, kit), cp = await c.signCheckpoint(m, owner, 0, '0'.repeat(64));
    for (const epoch of ['membership_epoch', 'key_epoch']) {
        const anchor = await k.signedObject('Checkpoint', {...cp, [epoch]: 2}, owner.signingSeed);
        await assert.rejects(c.verifyAdvance(anchor, cp, m, []), /ROLLBACK_DETECTED/);
    }
    const initial = {opaque_project_id: cp.opaque_project_id, cursor: cp.cursor, chain_digest: cp.chain_digest};
    await assert.rejects(c.verifyAdvance(initial, cp, m, []));
    assert.equal(digest(await c.verifyAdvance(initial, cp, m, [], true)), digest(cp));
    const path = mkdtempSync('../../storage/runtime/s2-cp-legacy-') + '/cp.sqlite', db = new DatabaseSync(path);
    db.exec('CREATE TABLE anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL)'); db.close();
    assert.throws(() => new c.CheckpointStore(path), /CHECKPOINT_STORE_KIND_REQUIRED/);
    const store = new k.TrustedStore(path + '.membership');
    await store.bootstrap(m, owner.signingPublic, kit.signingPublic);
    const rows = new DatabaseSync(store.path);
    rows.prepare('INSERT INTO manifests VALUES (?,?,?,?)').run(m.opaque_project_id, 'e'.repeat(64), 2, canonicalBytes(m)); rows.close();
    await assert.rejects(store.verifiedCurrent(m.opaque_project_id));
});

for (const mutation of ['signature_bit', 'cursor_zero']) for (const operation of ['get', 'advance', 'kit']) test(`Node saved signed cp ${mutation} rejects ${operation} and prevents overwrite`, async () => {
    const { k, c } = await modules(), wire = await import('../src/envelope.ts'), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-cp-sig-') + '/cp.sqlite', store = new c.CheckpointStore(path);
    store.pin(m.opaque_project_id);
    const rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], cp1 = await c.signCheckpoint(m, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await store.advance(cp1, m, rows);
    const bad = structuredClone(cp1), extra = mutation === 'signature_bit' ? [{sequence: 2, envelope_digest: 'b'.repeat(64)}] : [];
    if (mutation === 'signature_bit') { const signature = wire.b64decode(bad.signature, 64); signature[0] ^= 1; bad.signature = wire.b64encode(signature); }
    else { bad.cursor = 0; bad.chain_digest = '0'.repeat(64); }
    await assert.rejects(c.verifyCheckpoint(bad, m));
    const next = await c.signCheckpoint(m, owner, mutation === 'signature_bit' ? 2 : 0, mutation === 'signature_bit' ? c.extendChain(cp1.chain_digest, 1, extra) : '0'.repeat(64)), db = new DatabaseSync(path);
    db.prepare('UPDATE anchors SET body=?').run(canonicalBytes(bad));
    const before = db.prepare('SELECT * FROM anchors').all(); db.close();
    const reopened = new c.CheckpointStore(path), trusted = new k.TrustedStore(path + '.trusted');
    await trusted.bootstrap(m, owner.signingPublic, kit.signingPublic);
    if (operation === 'get') await assert.rejects(async () => await reopened.get(m.opaque_project_id));
    else if (operation === 'advance') await assert.rejects(reopened.advance(next, m, extra));
    else await assert.rejects(kit.updateAnchor(m, cp1, trusted, [], reopened));
    assert.equal(kit.manifestAnchor, undefined);
    const check = new DatabaseSync(path); assert.deepEqual(check.prepare('SELECT * FROM anchors').all(), before); check.close();
});

test('Node signed cp missing or corrupt verification context cannot be repaired by advance', async () => {
    const { k, c } = await modules();
    for (const mutation of ['missing', 'partial', 'extra', 'wrong_pub', 'wrong_epoch', 'wrong_digest', 'digest_recomputed']) {
        const owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m = await k.bootstrap(randomUUID(), owner, kit), cp = await c.signCheckpoint(m, owner, 0, '0'.repeat(64)), path = mkdtempSync('../../storage/runtime/s2-cp-context-') + '/cp.sqlite', store = new c.CheckpointStore(path);
        store.pin(m.opaque_project_id); await store.advance(cp, m, []);
        const db = new DatabaseSync(path), context = strictLoads((db.prepare('SELECT verification FROM anchors').get() as {verification: Uint8Array}).verification) as Record<string, any>;
        if (mutation === 'partial') delete context.signing_public_key;
        else if (mutation === 'extra') context.extra = 'SYNTHETIC';
        else if (mutation === 'wrong_pub') context.signing_public_key = (await k.Device.generate()).signingPublic;
        else if (mutation === 'wrong_epoch') context.membership_epoch++;
        else if (mutation === 'wrong_digest') context.checkpoint_digest = 'e'.repeat(64);
        else if (mutation === 'digest_recomputed') {
            const bad = {...cp, signature: 'A'.repeat(86)};
            context.checkpoint_digest = digest(bad); db.prepare('UPDATE anchors SET body=?').run(canonicalBytes(bad));
        }
        db.prepare('UPDATE anchors SET verification=?').run(mutation === 'missing' ? null : canonicalBytes(context));
        const before = db.prepare('SELECT * FROM anchors').all(); db.close();
        await assert.rejects(new c.CheckpointStore(path).get(m.opaque_project_id));
        await assert.rejects(new c.CheckpointStore(path).advance(cp, m, []));
        const check = new DatabaseSync(path); assert.deepEqual(check.prepare('SELECT * FROM anchors').all(), before); check.close();
    }
});

test('Node old checkpoint author may be revoked while historical signature remains trusted', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), m1 = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-cp-historical-') + '/cp.sqlite', trusted = new k.TrustedStore(path + '.trusted');
    await trusted.bootstrap(m1, owner.signingPublic, kit.signingPublic);
    const m2 = await k.transition(m1, owner, {add: b.member('writer', 1)}); await trusted.accept(m2);
    const rows = [{sequence: 1, envelope_digest: 'a'.repeat(64)}], cp1 = await c.signCheckpoint(m2, b, 1, c.extendChain('0'.repeat(64), 0, rows)), store = new c.CheckpointStore(path);
    store.pin(m1.opaque_project_id); await store.advance(cp1, m2, rows);
    const m3 = await k.transition(m2, owner, {revoke: b.deviceId}); await trusted.accept(m3);
    const reopened = new c.CheckpointStore(path);
    assert.equal(digest(await reopened.get(m1.opaque_project_id)), digest(cp1));
    const extra = [{sequence: 2, envelope_digest: 'b'.repeat(64)}], cp2 = await c.signCheckpoint(m3, owner, 2, c.extendChain(cp1.chain_digest, 1, extra));
    await reopened.advance(cp2, m3, extra);
    await kit.updateAnchor(m3, cp2, trusted, [], reopened);
    assert.equal(digest(kit.checkpointAnchor), digest(cp2));
    const legacyPath = path + '.legacy', db = new DatabaseSync(legacyPath);
    db.exec('CREATE TABLE anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL)'); db.close();
    assert.throws(() => new c.CheckpointStore(legacyPath), /CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED/);
});

for (const operation of ['challenge', 'consume', 'receipt']) test(`Node invalid signed history has no pairing ${operation} effects`, async () => {
    const { k, p } = await modules();
        const owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), initial = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-pair-history-') + '/trusted.sqlite', store = new k.TrustedStore(path);
        await store.bootstrap(initial, owner.signingPublic, kit.signingPublic);
        const challenge = await p.createChallenge(store, owner, b.member('writer', 1), {now: 100}), proof = await p.answerChallenge(challenge, initial, b, {confirmation: p.confirmation(challenge), now: 101}), key = randomBytes(32);
        if (operation === 'receipt') await p.consume(store, owner, challenge, proof, key, {now: 102});
        const current = store.current(initial.opaque_project_id), bad = {...current, signature: 'A'.repeat(86)}, db = new DatabaseSync(path);
        db.prepare('UPDATE manifests SET digest=?,body=? WHERE epoch=?').run(digest(bad), canonicalBytes(bad), current.membership_epoch);
        const before = db.prepare('SELECT * FROM challenges').all(); db.close();
        if (operation === 'challenge') await assert.rejects(p.createChallenge(store, owner, (await k.Device.generate()).member('reader', 2), {now: 103}));
        else if (operation === 'consume') await assert.rejects(p.consume(store, owner, challenge, proof, key, {now: 103}));
        else await assert.rejects(async () => await p.retryReceipt(store, challenge, b.deviceId));
        const reopened = new DatabaseSync(path);
        assert.deepEqual(reopened.prepare('SELECT * FROM challenges').all(), before);
        reopened.close();
});
test('Node pinned lifecycle, dual pairing and immutable receipt restart', async () => {
    const { k, p } = await modules(), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate();
    const manifest = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-life-node-') + '/trusted.sqlite';
    const store = new k.TrustedStore(path);
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const challenge = await p.createChallenge(store, owner, b.member('reader', 1), {
        now: 100
    }), proof = await p.answerChallenge(challenge, manifest, b, {
        confirmation: p.confirmation(challenge), now: 101
    }), key = randomBytes(32);
    const receipt = await p.consume(store, owner, challenge, proof, key, {
        now: 102
    });
    assert.deepEqual(Buffer.from(await k.openGrant(receipt.grant, receipt.manifest, b)), key);
    await assert.rejects(p.consume(store, owner, challenge, proof, key, {
        now: 102
    }), /PAIRING_USED/);
    assert.deepEqual(canonicalBytes(await p.retryReceipt(new k.TrustedStore(path), challenge, b.deviceId)), canonicalBytes(receipt));
    const revoked = await k.transition(receipt.manifest, owner, {
        revoke: b.deviceId
    });
    await store.accept(revoked);
    await assert.rejects(p.retryReceipt(store, challenge, b.deviceId), /REVOKED_DEVICE/);
    await assert.rejects(k.openGrant(receipt.grant, revoked, b));
});
test('Node checkpoint monotonic persistence and signed encrypted snapshot', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit);
    const path = mkdtempSync('../../storage/runtime/s2-check-node-'), anchor = new c.CheckpointStore(path + '/checkpoint.sqlite');
    anchor.pin(manifest.opaque_project_id);
    const rows = [{
            sequence: 1, envelope_digest: 'a'.repeat(64)
        }], cp = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await anchor.advance(cp, manifest, rows);
    assert.equal((await new c.CheckpointStore(anchor.path).get(manifest.opaque_project_id)).cursor, 1);
    await assert.rejects(anchor.advance(await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), manifest, []), /ROLLBACK_DETECTED/);
    const key = randomBytes(32), vault = new NonceVault(path + '/nonce.sqlite');
    vault.registerNew(key, 0);
    const env = await c.sealSnapshot({
        SYNTHETIC: 'snapshot'
    }, 'a'.repeat(64), cp, manifest, owner, key, vault, randomUUID());
    assert.deepEqual(canonicalBytes(await c.openSnapshot(env, manifest, key, cp, 'a'.repeat(64))), canonicalBytes({
        SYNTHETIC: 'snapshot'
    }));
    await assert.rejects(c.openSnapshot(env, manifest, key, cp, 'b'.repeat(64)));
});
test('Node artifact stream bound, corruption, staging and zero-write exact retry', async () => {
    const { k, a } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), key = randomBytes(32);
    const vault = new NonceVault(mkdtempSync('../../storage/runtime/s2-art-node-') + '/nonce.sqlite');
    vault.registerNew(key, 0);
    const bundle = await a.sealArtifact([Buffer.alloc(65536, 1), Buffer.alloc(100, 2)], {
        filename: 'SYNTHETIC_SECRET_FILENAME_MAT', category: 'qa', run_title: 'qa'
    }, manifest, owner, key, vault, randomUUID());
    assert.equal(JSON.stringify(bundle).includes('SYNTHETIC_SECRET_FILENAME_MAT'), false);
    const sink = new a.TestOnlyMemoryStagingSink();
    await a.openArtifact(bundle, manifest, key, sink);
    assert.equal(sink.data.length, 65636);
    const writes = sink.writes;
    await a.openArtifact(bundle, manifest, key, sink);
    assert.equal(sink.writes, writes);
    for (const kind of ['order', 'missing', 'tag']) {
        const bad = structuredClone(bundle);
        if (kind === 'order')
            bad.chunks.reverse();
        else if (kind === 'missing')
            bad.chunks.pop();
        else {
            const raw = Buffer.from(bad.chunks[1].ciphertext, 'base64url');
            raw[0] ^= 1;
            bad.chunks[1].ciphertext = raw.toString('base64url');
        }
        const staging = new a.TestOnlyMemoryStagingSink();
        await assert.rejects(a.openArtifact(bad, manifest, key, staging));
        assert.equal(staging.ready, false);
        assert.equal(staging.data.length, 0);
    }
});
test('Node stable QA UUID, PENDING denial and fresh-key revocation', async () => {
    const { k } = await modules();
    assert.equal(typeof (k as any).TestOnlyFileDeviceKeyStore, 'function', 'persistent QA device store required');
    assert.equal(typeof (k as any).revokeAndRotate, 'function', 'fresh-key revocation required');
    const path = mkdtempSync('../../storage/runtime/s2-key-node-'), first = await new k.TestOnlyFileDeviceKeyStore(path + '/device.sqlite').loadOrCreate(), second = await new k.TestOnlyFileDeviceKeyStore(path + '/device.sqlite').loadOrCreate();
    assert.equal(first.deviceId, second.deviceId);
    assert.equal(first.signingPublic, second.signingPublic);
    assert.notDeepEqual(first.signingSeed, first.recipientSeed);
    assert.equal(JSON.stringify(first).includes(Buffer.from(first.signingSeed).toString('hex')), false);
    const kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), first, kit), b = await k.Device.generate(), store = new k.TrustedStore(path + '/trusted.sqlite');
    await store.bootstrap(manifest, first.signingPublic, kit.signingPublic);
    const pending = await k.transition(manifest, first, {
        add: b.member('writer', 1, 'PENDING')
    });
    await store.accept(pending);
    await assert.rejects(k.makeGrant(pending, first, b.deviceId, randomUUID(), randomBytes(32)), /UNAUTHORIZED_DEVICE/);
    const active = await k.transition(pending, first, {
        activate: b.deviceId
    });
    await store.accept(active);
    const vault = new k.TestOnlyKeyVault(), old = vault.create(manifest.opaque_project_id, 1), rotation = await k.revokeAndRotate(store, vault, first, b.deviceId);
    assert.notDeepEqual(rotation.key, old);
    assert.deepEqual(Object.keys(rotation.grants), [first.deviceId]);
    assert.equal(JSON.stringify(rotation).includes('"key":'), false, 'rotation result must redact raw key');
});
test('Node kit unwrap requires latest trusted anchor and recover rotates new owner', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), b = await k.Device.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), key = randomBytes(32), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-recover-node-') + '/trusted.sqlite');
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const backup = await k.makeRecoveryBackup(manifest, owner, kit, key);
    await assert.rejects(k.openRecoveryBackup(backup, store, kit), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    await kit.updateAnchor(manifest, await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), store);
    assert.deepEqual(Buffer.from(await k.openRecoveryBackup(backup, store, kit)), key);
    const recovered = await k.recover(store, kit, b);
    assert.equal(recovered.members[0].status, 'REVOKED');
    assert.equal(recovered.members[1].role, 'owner');
    assert.equal(recovered.key_epoch, 2);
    await assert.rejects(k.recover(store, undefined, owner), /E2E_DATA_UNRECOVERABLE/);
});
test('Node pairing expiry, attempts and exception crash boundaries persist', async () => {
    const { k, p } = await modules();
    for (const fault of ['before_commit', 'after_commit', 'write_error', 'attempts']) {
        const owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), initial = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-pair-boundary-') + '/trusted.sqlite', store = new k.TrustedStore(path);
        await store.bootstrap(initial, owner.signingPublic, kit.signingPublic);
        const challenge = await p.createChallenge(store, owner, b.member('writer', 1), {
            now: 100
        });
        await assert.rejects(p.answerChallenge(challenge, initial, b, {
            confirmation: p.confirmation(challenge), now: 400
        }), /PAIRING_EXPIRED/);
        const proof = await p.answerChallenge(challenge, initial, b, {
            confirmation: p.confirmation(challenge), now: 101
        }), key = randomBytes(32);
        if (fault === 'attempts') {
            const bad = {
                ...proof, challenge_response: '0'.repeat(64)
            };
            for (let i = 0; i < 5; i++)
                await assert.rejects(p.consume(store, owner, challenge, bad, key, {
                    now: 102
                }));
            await assert.rejects(p.consume(new k.TrustedStore(path), owner, challenge, proof, key, {
                now: 102
            }), /PAIRING_ATTEMPTS_EXCEEDED/);
        }
        else if (fault === 'write_error') {
            const accept = store.accept.bind(store);
            store.accept = async (candidate, db) => {
                await accept(candidate, db);
                throw new Error('SYNTHETIC_PERSISTENCE_FAILURE');
            };
            await assert.rejects(p.consume(store, owner, challenge, proof, key, {
                now: 102
            }), /SYNTHETIC_PERSISTENCE_FAILURE/);
            assert.deepEqual(canonicalBytes(store.current(initial.opaque_project_id)), canonicalBytes(initial));
        }
        else {
            await assert.rejects(p.consume(store, owner, challenge, proof, key, {
                now: 102, crashPoint: fault
            }), /SYNTHETIC_CRASH/);
            const restarted = new k.TrustedStore(path);
            if (fault === 'before_commit') {
                assert.equal(restarted.current(initial.opaque_project_id).membership_epoch, 1);
                await p.consume(restarted, owner, challenge, proof, key, {
                    now: 102
                });
            }
            else
                assert.equal((await p.retryReceipt(restarted, challenge, b.deviceId)).manifest.membership_epoch, 2);
        }
    }
});
test('Node prior authority, strict signed checkpoint epochs and every grant field reject', async () => {
    const { k, c } = await modules(), m = await import('../src/membership.ts'), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), initial = await k.bootstrap(randomUUID(), owner, kit), next = await k.transition(initial, owner, {
        add: b.member('writer', 1)
    });
    const attack = structuredClone(next);
    attack.authority_device_id = b.deviceId;
    attack.members[1].role = 'owner';
    await assert.rejects(m.verifyTransition(initial, await k.signedManifest(attack, b.signingSeed), kit.signingPublic));
    const cp = await c.signCheckpoint(initial, owner, 0, '0'.repeat(64));
    for (const field of ['key_epoch', 'membership_epoch']) {
        const bad = {
            ...cp, [field]: true
        };
        await assert.rejects(c.verifyCheckpoint(await k.signedObject('Checkpoint', bad, owner.signingSeed), initial));
    }
    const grant = await k.makeGrant(next, owner, b.deviceId, randomUUID(), randomBytes(32));
    for (const field of Object.keys(grant)) {
        const bad = structuredClone(grant);
        bad[field] = field === 'context' ? {
            ...bad.context, key_epoch: 99
        } : typeof bad[field] === 'number' ? bad[field] + 1 : String(bad[field]) + 'A';
        await assert.rejects(k.openGrant(bad, next, b));
    }
    assert.throws(() => new k.TestOnlyFileDeviceKeyStore('../../fixtures/secret.sqlite'), /QA_VAULT_PATH_REQUIRED/);
});
test('Node recovery requires checkpoint, trusted local history and monotone combined anchor', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-kit-anchors-') + '/trusted.sqlite');
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const untrusted = new k.RecoveryKit(kit.signingSeed, kit.recipientSeed, kit.signingPublic, kit.recipientPublic);
    untrusted.deviceId = kit.deviceId;
    untrusted.manifestAnchor = (await import('../../sync-protocol/src/canonical.ts')).digest(manifest);
    untrusted.project = manifest.opaque_project_id;
    await assert.rejects(k.recover(store, untrusted, b), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const backup = await k.makeRecoveryBackup(manifest, owner, kit, randomBytes(32));
    await assert.rejects(k.openRecoveryBackup(backup, store, untrusted), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64));
    const anchoredKit = kit;
    await anchoredKit.updateAnchor(manifest, cp0, store);
    for (const mutation of ['project', 'epoch', 'cursor', 'chain', 'signature']) {
        const bad = structuredClone(cp0);
        if (mutation === 'project')
            bad.opaque_project_id = randomUUID();
        else if (mutation === 'epoch')
            bad.key_epoch++;
        else if (mutation === 'cursor')
            bad.cursor = true;
        else if (mutation === 'chain')
            bad.chain_digest = 'bad';
        else
            bad.signature = 'A'.repeat(86);
        anchoredKit.checkpointAnchor = mutation === 'signature' ? bad : await k.signedObject('Checkpoint', bad, owner.signingSeed);
        await assert.rejects(k.recover(store, anchoredKit, b), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    }
    const fresh = await k.RecoveryKit.generate();
    // Restore the exact retained anchor; imported seeds alone are not bootstrap.
    anchoredKit.checkpointAnchor = structuredClone(cp0);
    const trustedKit = anchoredKit;
    await assert.rejects(trustedKit.updateAnchor(manifest, cp0), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    await trustedKit.updateAnchor(manifest, cp0, store);
    const rows = [{
            sequence: 1, envelope_digest: 'a'.repeat(64)
        }], cp1 = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await trustedKit.updateAnchor(manifest, cp1, store, rows);
    await assert.rejects(trustedKit.updateAnchor(manifest, cp0, store), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    assert.equal(trustedKit.checkpointAnchor!.cursor, 1);
    const freshManifest = await k.bootstrap(randomUUID(), owner, fresh);
    await store.bootstrap(freshManifest, owner.signingPublic, fresh.signingPublic);
    const freshCp1 = await c.signCheckpoint(freshManifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await assert.rejects(fresh.updateAnchor(freshManifest, freshCp1, store), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const localCheckpoints = new c.CheckpointStore(mkdtempSync('../../storage/runtime/s2-kit-local-cp-') + '/checkpoint.sqlite');
    localCheckpoints.pin(freshManifest.opaque_project_id);
    await localCheckpoints.advance(freshCp1, freshManifest, rows);
    await fresh.updateAnchor(freshManifest, freshCp1, store, [], localCheckpoints);
    assert.equal(fresh.checkpointAnchor!.cursor, 1);
    assert.notEqual(fresh.signingPublic, kit.signingPublic);
});
test('Node every genesis chain entry point rejects nonzero root', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit);
    assert.throws(() => c.extendChain('a'.repeat(64), 0, []));
    const bad = await k.signedObject('Checkpoint', {
        version: 1, opaque_project_id: manifest.opaque_project_id, membership_epoch: 1, key_epoch: 1, cursor: 0, chain_digest: 'a'.repeat(64), creator_device_id: owner.deviceId
    }, owner.signingSeed);
    await assert.rejects(c.verifyCheckpoint(bad, manifest));
    assert.throws(() => new c.CheckpointStore(mkdtempSync('../../storage/runtime/s2-genesis-') + '/checkpoint.sqlite').pin(manifest.opaque_project_id, 0, 'a'.repeat(64)));
});
test('Node valid inner/outer/chunk auth still rejects boolean artifact inner integers', async () => {
    const { k, a } = await modules(), { digest } = await import('../../sync-protocol/src/canonical.ts'), wire = await import('../src/envelope.ts'), crypto = await import('../src/crypto.ts');
    const owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), key = randomBytes(32), vault = new NonceVault(mkdtempSync('../../storage/runtime/s2-art-schema-') + '/nonce.sqlite');
    vault.registerNew(key, 0);
    const parts = [Buffer.from('SYNTHETIC_A'), Buffer.from('SYNTHETIC_B')], locator = randomUUID(), bundle = await a.sealArtifact(parts, {
        filename: 'qa', category: 'qa', run_title: 'qa'
    }, manifest, owner, key, vault, locator), bindings = {
        opaque_project_id: manifest.opaque_project_id, sender_device_id: owner.deviceId, membership_epoch: 1, key_epoch: 1
    };
    const inner = await wire.openRecord(bundle.manifest_envelope, key, new Uint8Array(Buffer.from(owner.signingPublic, 'hex')), {
        ...bindings, nonce_prefix: 0, record_type: 'artifact_manifest'
    }) as Record<string, any>, dek = await crypto.kwUnwrap(key, wire.b64decode(inner.wrapped_dek));
    for (const [field, value] of [['key_epoch', true], ['nonce_prefix', false]] as const) {
        const bad = structuredClone(bundle), modified = await k.signedObject('ArtifactManifest', {
            ...inner, [field]: value
        }, owner.signingSeed);
        for (let index = 0; index < parts.length; index++) {
            const chunk = bad.chunks[index], nonce = vault.reserve(dek, 0);
            chunk.manifest_identity = digest(modified);
            chunk.nonce = Buffer.from(nonce).toString('hex');
            chunk.ciphertext = wire.b64encode(await crypto.aesEncrypt(dek, nonce, parts[index], a.chunkAad(chunk)));
        }
        bad.manifest_envelope = await wire.sealRecord(modified, key, owner.signingSeed, vault, 0, {
            ...bindings, message_id: locator, record_type: 'artifact_manifest'
        });
        const sink = new a.TestOnlyMemoryStagingSink();
        await assert.rejects(a.openArtifact(bad, manifest, key, sink));
        assert.equal(sink.ready, false);
    }
});
test('Node erased anchors and imported old seeds cannot regain genesis freshness', async () => {
    const { k, c } = await modules(), owner = await k.Device.generate(), kit = await k.RecoveryKit.generate(), manifest = await k.bootstrap(randomUUID(), owner, kit), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-kit-reset-') + '/trusted.sqlite');
    await store.bootstrap(manifest, owner.signingPublic, kit.signingPublic);
    const cp0 = await c.signCheckpoint(manifest, owner, 0, '0'.repeat(64)), rows = [{
            sequence: 1, envelope_digest: 'a'.repeat(64)
        }], cp1 = await c.signCheckpoint(manifest, owner, 1, c.extendChain('0'.repeat(64), 0, rows));
    await kit.updateAnchor(manifest, cp0, store);
    await kit.updateAnchor(manifest, cp1, store, rows);
    kit.manifestAnchor = undefined;
    kit.checkpointAnchor = undefined;
    await assert.rejects(kit.updateAnchor(manifest, cp0, store), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const imported = new k.RecoveryKit(kit.signingSeed, kit.recipientSeed, kit.signingPublic, kit.recipientPublic);
    imported.deviceId = kit.deviceId;
    await assert.rejects(imported.updateAnchor(manifest, cp0, store), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    const local = new c.CheckpointStore(mkdtempSync('../../storage/runtime/s2-import-cp-') + '/checkpoint.sqlite');
    local.pin(manifest.opaque_project_id);
    await local.advance(cp0, manifest, []);
    await assert.rejects(imported.updateAnchor(manifest, cp0, store, [], local), /RECOVERY_FRESHNESS_UNVERIFIABLE/);
    assert.throws(() => k.RecoveryKit.fromPublicTestVectors(kit.signingSeed, kit.recipientSeed, kit.signingPublic, kit.recipientPublic), /PUBLIC_TEST_ONLY_VECTOR_REQUIRED/);
});
test('Node foreign valid recovery chain cannot change either project or kit', async () => {
    const { k, c } = await modules(), { digest } = await import('../../sync-protocol/src/canonical.ts');
    for (const withOwn of [false, true]) {
        const aOwner = await k.Device.generate(), bOwner = await k.Device.generate(), aKit = await k.RecoveryKit.generate(), bKit = await k.RecoveryKit.generate(), a = await k.bootstrap(randomUUID(), aOwner, aKit), b = await k.bootstrap(randomUUID(), bOwner, bKit), store = new k.TrustedStore(mkdtempSync('../../storage/runtime/s2-kit-project-') + '/trusted.sqlite');
        await store.bootstrap(a, aOwner.signingPublic, aKit.signingPublic);
        await store.bootstrap(b, bOwner.signingPublic, bKit.signingPublic);
        await aKit.updateAnchor(a, await c.signCheckpoint(a, aOwner, 0, '0'.repeat(64)), store);
        const own = await k.transition(a, aOwner, {
            add: (await k.Device.generate()).member('reader', 1)
        }), foreign = await k.transition(b, bOwner, {
            add: (await k.Device.generate()).member('writer', 1)
        }), before = aKit.manifestAnchor + ':' + digest(aKit.checkpointAnchor);
        await assert.rejects(k.recover(store, aKit, await k.Device.generate(), withOwn ? [own, foreign] : [foreign]));
        assert.equal(digest(store.current(a.opaque_project_id)), digest(a));
        assert.equal(digest(store.current(b.opaque_project_id)), digest(b));
        assert.equal(aKit.manifestAnchor + ':' + digest(aKit.checkpointAnchor), before);
    }
});

test('Node PENDING pairing exact activation and crash receipts', async () => {
    const { k, p } = await modules();
    for (const fault of [undefined, 'before_commit', 'after_commit']) {
        const owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), old = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-pending-') + '/trusted.sqlite';
        let store = new k.TrustedStore(path);
        await store.bootstrap(old, owner.signingPublic, kit.signingPublic);
        const pending = await k.transition(old, owner, {add: b.member('writer', 7, 'PENDING')});
        await store.accept(pending);
        const recipient = {...pending.members[1], status: 'ACTIVE'}, challenge = await p.createChallenge(store, owner, recipient, {now: 100}), proof = await p.answerChallenge(challenge, pending, b, {confirmation: p.confirmation(challenge), now: 101}), key = randomBytes(32);
        let receipt;
        if (fault) {
            await assert.rejects(p.consume(store, owner, challenge, proof, key, {now: 102, crashPoint: fault}), /SYNTHETIC_CRASH/);
            store = new k.TrustedStore(path);
            if (fault === 'before_commit') {
                assert.equal(digest(store.current(old.opaque_project_id)), digest(pending));
                const db = new DatabaseSync(path), row = db.prepare('SELECT attempts,used,receipt FROM challenges').get(); db.close();
                assert.deepEqual({...row}, {attempts: 0, used: 0, receipt: null});
                receipt = await p.consume(store, owner, challenge, proof, key, {now: 102});
            } else receipt = await p.retryReceipt(store, challenge, b.deviceId);
        } else receipt = await p.consume(store, owner, challenge, proof, key, {now: 102});
        assert.equal(digest(receipt.manifest.members), digest([pending.members[0], recipient]));
        assert.equal(receipt.manifest.membership_epoch, pending.membership_epoch + 1);
        assert.equal(receipt.manifest.key_epoch, pending.key_epoch);
        assert.ok(Buffer.from(await k.openGrant(receipt.grant, receipt.manifest, b)).equals(key));
        assert.equal(digest(await p.retryReceipt(new k.TrustedStore(path), challenge, b.deviceId)), digest(receipt));
        await assert.rejects(p.consume(store, owner, challenge, proof, key, {now: 102}), /PAIRING_USED/);
    }
});
for (const change of ['ACTIVE', 'REVOKED', 'role', 'nonce_prefix', 'signing_public_key', 'recipient_public_key', 'granted_at']) test(`Node PENDING pairing rejects ${change} identity replacement`, async () => {
    const {k, p} = await modules(), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), old = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-pending-negative-') + '/trusted.sqlite', store = new k.TrustedStore(path);
    await store.bootstrap(old, owner.signingPublic, kit.signingPublic);
    let pending = await k.transition(old, owner, {add: b.member('writer', 7, ['ACTIVE', 'REVOKED'].includes(change) ? 'ACTIVE' : 'PENDING')});
    await store.accept(pending);
    if (change === 'REVOKED') {pending = await k.transition(pending, owner, {revoke: b.deviceId}); await store.accept(pending);}
    let answerer = b;
    if (['signing_public_key', 'recipient_public_key'].includes(change)) {
        const other = await k.Device.generate(), signing = change === 'signing_public_key';
        answerer = new k.Device(b.deviceId, signing ? other.signingSeed : b.signingSeed, signing ? b.recipientSeed : other.recipientSeed, signing ? other.signingPublic : b.signingPublic, signing ? b.recipientPublic : other.recipientPublic);
    }
    const recipient = answerer.member('writer', 7);
    if (change === 'role') recipient.role = 'reader';
    if (change === 'nonce_prefix') recipient.nonce_prefix = 8;
    if (change === 'granted_at') recipient.granted_at = 1;
    const challenge = await p.createChallenge(store, owner, recipient, {now: 100}), proof = await p.answerChallenge(challenge, pending, answerer, {confirmation: p.confirmation(challenge), now: 101});
    await assert.rejects(p.consume(store, owner, challenge, proof, randomBytes(32), {now: 102}), /PAIRING_SCOPE_MISMATCH/);
    assert.equal(digest(store.current(old.opaque_project_id)), digest(pending));
    const db = new DatabaseSync(path), row = db.prepare('SELECT attempts,used,receipt FROM challenges').get(); db.close();
    assert.deepEqual({...row}, {attempts: 1, used: 0, receipt: null});
});
for (const target of ['AFTER INSERT ON manifests', 'AFTER UPDATE OF receipt ON challenges']) test(`Node PENDING pairing SQL rollback ${target}`, async () => {
    const {k, p} = await modules(), owner = await k.Device.generate(), b = await k.Device.generate(), kit = await k.RecoveryKit.generate(), old = await k.bootstrap(randomUUID(), owner, kit), path = mkdtempSync('../../storage/runtime/s2-pending-sql-') + '/trusted.sqlite';
    let store = new k.TrustedStore(path);
    await store.bootstrap(old, owner.signingPublic, kit.signingPublic);
    const pending = await k.transition(old, owner, {add: b.member('writer', 7, 'PENDING')}); await store.accept(pending);
    const challenge = await p.createChallenge(store, owner, {...pending.members[1], status: 'ACTIVE'}, {now: 100}), proof = await p.answerChallenge(challenge, pending, b, {confirmation: p.confirmation(challenge), now: 101}), key = randomBytes(32);
    const db = new DatabaseSync(path); db.exec(`CREATE TRIGGER fail_pending ${target} BEGIN SELECT RAISE(ABORT, 'SYNTHETIC_WRITE'); END`); db.close();
    await assert.rejects(p.consume(store, owner, challenge, proof, key, {now: 102}), /SYNTHETIC_WRITE/);
    store = new k.TrustedStore(path);
    assert.equal(digest(store.current(old.opaque_project_id)), digest(pending));
    const check = new DatabaseSync(path), row = check.prepare('SELECT attempts,used,receipt FROM challenges').get();
    assert.deepEqual({...row}, {attempts: 0, used: 0, receipt: null}); check.exec('DROP TRIGGER fail_pending'); check.close();
    const receipt = await p.consume(store, owner, challenge, proof, key, {now: 102});
    assert.equal(digest(await p.retryReceipt(store, challenge, b.deviceId)), digest(receipt));
});
