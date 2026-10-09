import { canonicalBytes, strictLoads, digest, validateTransaction } from '../../sync-protocol/src/browser.ts';
import { sha256, verify, aesDecrypt, aesEncrypt } from './crypto-web.ts';
import { b64encode, b64decode, hexDecode, hexEncode, equal, nonceParts } from './binary.ts';
import { SUITE, recordHeader, validateEnvelopeShape, decodeEnvelopeShape, validateHeader, headerOf, signaturePreimage, aad, type Envelope } from './envelope-shape.ts';
export * from './envelope-shape.ts';
export async function validateEnvelope(env: Envelope): Promise<Envelope> {
    const ct = validateEnvelopeShape(env);
    if (await sha256(ct) !== env.ciphertext_digest)
        throw Error('INVALID_ENVELOPE');
    return env;
}
export async function decodeEnvelope(raw: Uint8Array): Promise<Envelope> { return validateEnvelope(decodeEnvelopeShape(raw)); }
export async function verifyEnvelope(env: Envelope, pub: Uint8Array): Promise<void> { await validateEnvelope(env); await verify(pub, b64decode(env.signature, 64), signaturePreimage(env)); }
export interface Bindings {
    opaque_project_id: string;
    sender_device_id: string;
    membership_epoch: number;
    key_epoch: number;
}
export async function openRecord(env: Envelope, key: CryptoKey | Uint8Array, pub: Uint8Array, bindings: Bindings & {
    nonce_prefix: number;
    record_type?: string;
}): Promise<unknown> {
    await verifyEnvelope(env, pub);
    for (const f of ['opaque_project_id', 'sender_device_id', 'membership_epoch', 'key_epoch'] as const)
        if (env[f] !== bindings[f])
            throw new Error('ENVELOPE_BINDING_MISMATCH');
    if (env.record_type !== (bindings.record_type ?? 'snapshot'))
        throw new Error('ENVELOPE_BINDING_MISMATCH');
    const nonce = hexDecode(env.nonce), { prefix, counter } = nonceParts(nonce);
    if (prefix !== bindings.nonce_prefix || counter < 1n || counter > 9007199254740991n)
        throw new Error('NONCE_BINDING_MISMATCH');
    const raw = await aesDecrypt(key, nonce, b64decode(env.ciphertext), aad(headerOf(env)));
    let value: unknown;
    try {
        value = strictLoads(raw);
    }
    catch {
        throw new Error('INVALID_PLAINTEXT');
    }
    if (!equal(raw, canonicalBytes(value)) || await digest(value) !== env.semantic_transaction_digest)
        throw new Error('SEMANTIC_DIGEST_MISMATCH');
    return value;
}
export async function openTransaction(env: Envelope, key: CryptoKey | Uint8Array, pub: Uint8Array, bindings: Bindings & {
    nonce_prefix: number;
    project_id: string;
}): Promise<unknown> {
    const tx = validateTransaction(await openRecord(env, key, pub, { ...bindings, record_type: 'transaction' }));
    if (tx.protocol_version !== env.protocol_version || tx.schema_version !== env.schema_version || tx.project_id !== bindings.project_id || tx.device_id !== env.sender_device_id || JSON.stringify(tx.dependencies) !== JSON.stringify(env.dependencies))
        throw new Error('TRANSACTION_BINDING_MISMATCH');
    return tx;
}
export async function sealWithNonce(record: unknown, key: CryptoKey | Uint8Array, signer: (v: Uint8Array) => Promise<Uint8Array>, nonce: Uint8Array, options: Bindings & {
    message_id: string;
    dependencies?: string[];
    checkpoint_sequence?: number;
    record_type?: string;
    protocol_version?: number;
    schema_version?: number;
}): Promise<Envelope> {
    const plain = canonicalBytes(record);
    if (plain.length > 180 * 1024)
        throw new Error('MESSAGE_TOO_LARGE');
    const header = recordHeader(await digest(record), options);
    validateHeader(header);
    header.nonce = hexEncode(nonce);
    const ct = await aesEncrypt(key, hexDecode(header.nonce), plain, aad(header));
    const env: Envelope = { ...header, ciphertext: b64encode(ct), ciphertext_digest: await sha256(ct) };
    env.signature = b64encode(await signer(signaturePreimage(env)));
    return validateEnvelope(env);
}
