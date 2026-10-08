/** All fixed keys are PUBLIC TEST ONLY. Runtime keys are generated in memory. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { canonicalBytes } from '../../sync-protocol/src/canonical.ts';
import { revision, transactionDigest } from '../../sync-protocol/src/protocol.ts';
import { aesEncrypt, aesDecrypt, sign, verify, signingPublic, recipientPublic, wrapKey, unwrapKey, kwWrap, kwUnwrap } from '../src/crypto.ts';
import { NonceVault } from '../src/nonce.ts';
import { sealRecord, openRecord, openTransaction, sealTransaction, aad, headerOf, signaturePreimage } from '../src/envelope.ts';
import * as wire from '../src/envelope.ts';
const key = Uint8Array.from({ length: 32 }, (_, i) => i), seed = Uint8Array.from({ length: 32 }, (_, i) => i + 32);
const id = '11111111-1111-4111-8111-111111111111', device = '22222222-2222-4222-8222-222222222222';
test('standard primitives reject changed authentication context', async () => {
    const msg = new TextEncoder().encode('TEST ONLY'), aad = new TextEncoder().encode('bound'), nonce = new Uint8Array(12);
    const ct = await aesEncrypt(key, nonce, msg, aad);
    assert.deepEqual(await aesDecrypt(key, nonce, ct, aad), msg);
    await assert.rejects(aesDecrypt(key, nonce, ct, new Uint8Array()));
    const sig = await sign(seed, msg);
    await verify(await signingPublic(seed), sig, msg);
    await assert.rejects(verify(await signingPublic(seed), sig, aad));
    const pub = await recipientPublic(seed);
    const context = { opaque_project_id: id, recipient_device_id: device, key_epoch: 1, membership_epoch: 1, session_id: id, recipient_signing_public_key: Buffer.from(await signingPublic(seed)).toString('hex'), recipient_public_key: Buffer.from(pub).toString('hex') };
    const wrapped = await wrapKey(pub, key, context);
    assert.deepEqual(await unwrapKey(seed, wrapped, context), key);
    await assert.rejects(unwrapKey(key, wrapped, context));
    await assert.rejects(unwrapKey(seed, wrapped, { ...context, key_epoch: 2 }));
    assert.deepEqual(await kwUnwrap(key, await kwWrap(key, seed)), seed);
});
test('envelope uses committed nonces and fails all altered fields', async () => {
    const path = mkdtempSync('../../storage/runtime/s2-node-') + '/nonce.sqlite';
    const vault = new NonceVault(path);
    vault.registerNew(key, 7);
    const bindings = { opaque_project_id: id, sender_device_id: device, membership_epoch: 1, key_epoch: 1 };
    const env = await sealRecord({ synthetic: 'TEST ONLY' }, key, seed, vault, 7, { ...bindings, message_id: id });
    assert.deepEqual(JSON.parse(JSON.stringify(await openRecord(env, key, await signingPublic(seed), { ...bindings, nonce_prefix: 7 }))), { synthetic: 'TEST ONLY' });
    for (const field of Object.keys(env)) {
        const bad = { ...env, [field]: field === 'dependencies' ? [id] : typeof env[field] === 'number' ? env[field] + 1 : String(env[field]) + 'A' };
        await assert.rejects(openRecord(bad, key, await signingPublic(seed), { ...bindings, nonce_prefix: 7 }));
    }
});
test('strict wire decoder rejects duplicate and noncanonical bytes', () => {
    assert.equal(typeof (wire as any).decodeEnvelope, 'function', 'strict decoder must exist');
    assert.throws(() => (wire as any).decodeEnvelope(new TextEncoder().encode(' '.repeat(262145))));
});
const transactionFixture = () => JSON.parse(readFileSync(new URL('../../../fixtures/sync/secure-v1/transaction-envelope.TEST_ONLY.json', import.meta.url), 'utf8'));
test('fixed canonical transaction and complete envelope verify independently in Node', async () => {
    const fixture = transactionFixture(), raw = new Uint8Array(Buffer.from(fixture.envelope_canonical_hex, 'hex'));
    assert.equal(createHash('sha256').update(raw).digest('hex'), fixture.envelope_sha256);
    const env = wire.decodeEnvelope(raw);
    assert.equal(Buffer.from(canonicalBytes(env)).toString('hex'), fixture.envelope_canonical_hex);
    assert.deepEqual(JSON.parse(JSON.stringify(env)), fixture.envelope);
    assert.equal(Buffer.from(aad(headerOf(env))).toString('hex'), fixture.aad_hex);
    const key = new Uint8Array(Buffer.from(fixture.key_TEST_ONLY, 'hex')), pub = new Uint8Array(Buffer.from(fixture.signing_public_key, 'hex'));
    const tx = await openTransaction(env, key, pub, fixture.bindings) as any;
    assert.equal(Buffer.from(canonicalBytes(tx)).toString('hex'), fixture.plaintext_canonical_hex);
    assert.equal(transactionDigest(tx), fixture.semantic_transaction_digest);
    assert.deepEqual(tx.changes.map(revision), fixture.semantic_revision_digests);
    assert.equal(Buffer.from(await unwrapKey(new Uint8Array(Buffer.from(fixture.recipient_seed_TEST_ONLY, 'hex')), new Uint8Array(Buffer.from(fixture.wrapped_key_hex, 'hex')), fixture.wrap_context)).toString('hex'), fixture.key_TEST_ONLY);
    const vault = new NonceVault(mkdtempSync('../../storage/runtime/s2-node-fixed-') + '/nonce.sqlite');
    vault.registerNew(key, fixture.bindings.nonce_prefix);
    const { project_id, nonce_prefix, ...bindings } = fixture.bindings;
    const sealed = await sealTransaction(tx, key, new Uint8Array(Buffer.from(fixture.signing_seed_TEST_ONLY, 'hex')), vault, nonce_prefix, { ...bindings, message_id: env.message_id });
    assert.equal(Buffer.from(canonicalBytes(sealed)).toString('hex'), fixture.envelope_canonical_hex);
});
test('Node strict decoder rejects duplicates, noncanonical order, unsafe integers and valid UUID scope substitution', async () => {
    const fixture = transactionFixture(), raw = Buffer.from(fixture.envelope_canonical_hex, 'hex'), env = fixture.envelope;
    for (const bad of [Buffer.concat([Buffer.from(' '), raw]), Buffer.concat([Buffer.from([239, 187, 191]), raw]), Buffer.from(raw.toString().replace('{', '{"nonce":"00",')), Buffer.from(raw.toString().replace('"key_epoch":1', '"key_epoch":9007199254740992')), Buffer.from(raw.toString().replace('"key_epoch":1', '"key_epoch":1.0')), Buffer.from(raw.toString().replace('"checkpoint_sequence":0', '"checkpoint_sequence":-0')), Buffer.from(raw.toString().replace(env.nonce, '0000001A0000000000000001'))])
        assert.throws(() => wire.decodeEnvelope(bad));
    const reordered = Object.fromEntries(Object.entries(env).reverse());
    assert.throws(() => wire.decodeEnvelope(new TextEncoder().encode(JSON.stringify(reordered))));
    const key = new Uint8Array(Buffer.from(fixture.key_TEST_ONLY, 'hex')), pub = new Uint8Array(Buffer.from(fixture.signing_public_key, 'hex'));
    for (const field of ['opaque_project_id', 'sender_device_id', 'message_id'])
        await assert.rejects(openTransaction({ ...env, [field]: '66666666-6666-4666-8666-666666666666' }, key, pub, fixture.bindings));
    for (const [field, value] of Object.entries({ opaque_project_id: '33333333-3333-4333-8333-333333333333', sender_device_id: '33333333-3333-4333-8333-333333333333', membership_epoch: 2, key_epoch: 2, nonce_prefix: 20, project_id: '33333333-3333-4333-8333-333333333333' }))
        await assert.rejects(openTransaction(env, key, pub, { ...fixture.bindings, [field]: value }));
});
test('authenticated malformed plaintext exposes only stable error code', async () => {
    const fixture = transactionFixture(), env = { ...fixture.envelope }, key = new Uint8Array(Buffer.from(fixture.key_TEST_ONLY, 'hex'));
    const token = '1.123456789123456789';
    const ct = await aesEncrypt(key, new Uint8Array(Buffer.from(env.nonce, 'hex')), new TextEncoder().encode('{"synthetic":' + token + '}'), aad(headerOf(env)));
    env.ciphertext = wire.b64encode(ct);
    env.ciphertext_digest = createHash('sha256').update(ct).digest('hex');
    env.signature = wire.b64encode(await sign(new Uint8Array(Buffer.from(fixture.signing_seed_TEST_ONLY, 'hex')), signaturePreimage(env)));
    await assert.rejects(openRecord(env, key, new Uint8Array(Buffer.from(fixture.signing_public_key, 'hex')), { ...fixture.bindings, record_type: 'transaction' }), error => error instanceof Error && error.message === 'INVALID_PLAINTEXT' && !error.message.includes(token));
});
