/** Synthetic test subprocess boundary: results contain cryptograms, never private keys. */
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { canonicalBytes } from '../../sync-protocol/src/canonical.ts';
import { revision, transactionDigest } from '../../sync-protocol/src/protocol.ts';
import { aesEncrypt, aesDecrypt, sign, verify, signingPublic, recipientPublic, wrapKey, unwrapKey, kwWrap, kwUnwrap } from '../src/crypto.ts';
import { sealRecord, openRecord, decodeEnvelope, openTransaction, sealTransaction } from '../src/envelope.ts';
import { NonceVault } from '../src/nonce.ts';
const input = JSON.parse(readFileSync(0, 'utf8')), raw = (h: string) => new Uint8Array(Buffer.from(h, 'hex')), hex = (b: Uint8Array) => Buffer.from(b).toString('hex');
if (input.mode === 'reserve') {
    const vault = new NonceVault(input.path), nonces: string[] = [];
    if (input.crash === 'after_witness') {
        const original = vault.append.bind(vault);
        vault.append = (id, counter) => { original(id, counter); process.exit(77); };
    }
    for (let i = 0; i < input.count; i++) {
        const n = vault.reserve(raw(input.key), input.prefix);
        if (input.crash === 'after_commit')
            process.exit(77);
        nonces.push(hex(n));
    }
    process.stdout.write(JSON.stringify(nonces));
}
else if (input.mode === 'verify') {
    await verify(raw(input.signing_public), raw(input.signature), raw(input.message));
    const plaintext = await aesDecrypt(raw(input.key), raw(input.nonce), raw(input.ciphertext), raw(input.aad));
    const unwrapped = await unwrapKey(raw(input.seed), raw(input.wrapped), input.context);
    const dek = await kwUnwrap(raw(input.key), raw(input.kw));
    process.stdout.write(JSON.stringify({ plaintext: hex(plaintext), unwrapped_matches: hex(unwrapped) === input.key, dek_matches: hex(dek) === input.seed }));
}
else if (input.mode === 'generate') {
    const key = raw(input.key), seed = raw(input.seed), message = raw(input.message), aad = raw(input.aad), nonce = raw(input.nonce);
    process.stdout.write(JSON.stringify({ ciphertext: hex(await aesEncrypt(key, nonce, message, aad)), signature: hex(await sign(seed, message)), signing_public: hex(await signingPublic(seed)), recipient_public: hex(await recipientPublic(seed)), wrapped: hex(await wrapKey(await recipientPublic(seed), key, input.context)), kw: hex(await kwWrap(key, seed)) }));
}
else if (input.mode === 'open') {
    const record = await openRecord(input.envelope, raw(input.key), raw(input.public_key), input.bindings);
    process.stdout.write(JSON.stringify(record));
}
else if (input.mode === 'seal') {
    const vault = new NonceVault(input.path);
    vault.registerNew(raw(input.key), input.prefix);
    process.stdout.write(JSON.stringify(await sealRecord(input.record, raw(input.key), raw(input.seed), vault, input.prefix, input.bindings)));
}
else if (input.mode === 'transaction_fixture') {
    const envelopeBytes = raw(input.envelope_canonical_hex);
    const envelope = decodeEnvelope(envelopeBytes);
    const tx = await openTransaction(envelope, raw(input.key_TEST_ONLY), raw(input.signing_public_key), input.bindings) as any;
    const unwrapped = await unwrapKey(raw(input.recipient_seed_TEST_ONLY), raw(input.wrapped_key_hex), input.wrap_context);
    process.stdout.write(JSON.stringify({ envelope_sha256: createHash('sha256').update(envelopeBytes).digest('hex'), plaintext_canonical_hex: hex(canonicalBytes(tx)), semantic_transaction_digest: transactionDigest(tx), semantic_revision_digests: tx.changes.map(revision), wrapped_key_matches: hex(unwrapped) === input.key_TEST_ONLY, verified: true }));
}
else if (input.mode === 'transaction_seal') {
    const tx = JSON.parse(Buffer.from(input.plaintext_canonical_hex, 'hex').toString('utf8'));
    const vault = new NonceVault(input.path);
    vault.registerNew(raw(input.key_TEST_ONLY), input.bindings.nonce_prefix);
    const { project_id, nonce_prefix, ...bindings } = input.bindings;
    const envelope = await sealTransaction(tx, raw(input.key_TEST_ONLY), raw(input.signing_seed_TEST_ONLY), vault, nonce_prefix, { ...bindings, message_id: input.envelope.message_id });
    process.stdout.write(JSON.stringify({ envelope_canonical_hex: hex(canonicalBytes(envelope)), envelope_sha256: createHash('sha256').update(canonicalBytes(envelope)).digest('hex') }));
}
else
    throw new Error('TEST_ONLY_UNKNOWN_MODE');
