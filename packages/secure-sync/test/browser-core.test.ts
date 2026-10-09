/** Node regression of the shared async core. These are NOT browser evidence. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { canonicalBytes } from '../../sync-protocol/src/canonical.ts';
import { decodeEnvelope, openTransaction, generateDevice, sign, verify, hexDecode, importProjectKey } from '../src/browser.ts';
const fixture = JSON.parse(readFileSync(new URL('../../../fixtures/sync/secure-v1/transaction-envelope.TEST_ONLY.json', import.meta.url), 'utf8'));
test('shared async decoder opens unchanged fixed complete v1 envelope', async () => { const env = await decodeEnvelope(hexDecode(fixture.envelope_canonical_hex)); const key = await importProjectKey(hexDecode(fixture.key_TEST_ONLY)); const tx = await openTransaction(env, key.key, hexDecode(fixture.signing_public_key), fixture.bindings); assert.equal(Buffer.from(canonicalBytes(tx)).toString('hex'), fixture.plaintext_canonical_hex); });
test('shared async decoder rejects noncanonical bytes and altered ciphertext digest', async () => { await assert.rejects(decodeEnvelope(new TextEncoder().encode(' ' + new TextDecoder().decode(hexDecode(fixture.envelope_canonical_hex))))); await assert.rejects(decodeEnvelope(canonicalBytes({ ...fixture.envelope, ciphertext_digest: '0'.repeat(64) })), /INVALID_ENVELOPE/); });
test('native device keys sign and verify but private export is forbidden', async () => { const d = await generateDevice(), message = new TextEncoder().encode('TEST ONLY core contract'); const sig = await sign(d.signing.privateKey, message); await verify(hexDecode(d.signingPublic), sig, message); await assert.rejects(verify(hexDecode(d.signingPublic), sig, new Uint8Array())); await assert.rejects(crypto.subtle.exportKey('pkcs8', d.signing.privateKey)); await assert.rejects(crypto.subtle.exportKey('pkcs8', d.recipient.privateKey)); });
