import { createHash } from 'node:crypto';
import { canonicalBytes, strictLoads, digest } from '../../sync-protocol/src/canonical.ts';
import { validateTransaction, requireVersionPair } from '../../sync-protocol/src/protocol.ts';
import { aesEncrypt, aesDecrypt, sign, verify } from './crypto.ts';
import { NonceVault } from './nonce.ts';
export const SUITE = 'RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM';
export const HEADER_FIELDS = 'envelope_version crypto_suite protocol_version schema_version record_type opaque_project_id sender_device_id membership_epoch key_epoch message_id semantic_transaction_digest dependencies nonce checkpoint_sequence'.split(' ');
export type Envelope = Record<string, any>;
const text = (s: string) => new TextEncoder().encode(s), concat = (...parts: Uint8Array[]) => new Uint8Array(Buffer.concat(parts));
export const b64encode = (value: Uint8Array) => Buffer.from(value).toString('base64url');
export function b64decode(value: unknown, size?: number): Uint8Array {
    if (typeof value !== 'string' || !(/^[A-Za-z0-9_-]*$/).test(value))
        throw new Error('INVALID_ENVELOPE');
    const raw = Buffer.from(value, 'base64url');
    if (b64encode(raw) !== value || (size !== undefined && raw.length !== size))
        throw new Error('INVALID_ENVELOPE');
    return new Uint8Array(raw);
}
function uuid(value: unknown): void {
    if (typeof value !== 'string' || !(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/).test(value) || value === '00000000-0000-0000-0000-000000000000')
        throw new Error('INVALID_ENVELOPE');
}
function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): void {
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || Object.is(value, -0) || value < min || value > max)
        throw new Error('INVALID_ENVELOPE');
}
function hex(value: unknown, size: number): void {
    if (typeof value !== 'string' || !(new RegExp('^[0-9a-f]{' + size * 2 + '}$')).test(value))
        throw new Error('INVALID_ENVELOPE');
}
function fields(value: Envelope, expected: string[]): void {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== [...expected].sort().join())
        throw new Error('INVALID_ENVELOPE');
    canonicalBytes(value);
}
export const headerOf = (env: Envelope): Envelope => Object.fromEntries(HEADER_FIELDS.map(key => [key, env[key]]));
export function validateHeader(header: Envelope): void {
    fields(header, HEADER_FIELDS);
    integer(header.envelope_version, 1, 1);
    requireVersionPair(header.protocol_version, header.schema_version, header.record_type === 'transaction' ? undefined : [[1, 1]]);
    if (header.crypto_suite !== SUITE || !['transaction', 'snapshot', 'artifact_manifest'].includes(header.record_type))
        throw new Error('UNSUPPORTED_SUITE');
    for (const f of ['opaque_project_id', 'sender_device_id', 'message_id'])
        uuid(header[f]);
    for (const f of ['membership_epoch', 'key_epoch'])
        integer(header[f], 1);
    integer(header.checkpoint_sequence);
    hex(header.semantic_transaction_digest, 32);
    hex(header.nonce, 12);
    if (!Array.isArray(header.dependencies) || header.dependencies.length > 100)
        throw new Error('INVALID_ENVELOPE');
    for (const d of header.dependencies)
        uuid(d);
    if (JSON.stringify(header.dependencies) !== JSON.stringify([...new Set(header.dependencies)].sort()))
        throw new Error('INVALID_ENVELOPE');
}
export function validateEnvelope(env: Envelope): Envelope {
    fields(env, [...HEADER_FIELDS, 'ciphertext', 'ciphertext_digest', 'signature']);
    if (canonicalBytes(env).length > 256 * 1024)
        throw new Error('MESSAGE_TOO_LARGE');
    validateHeader(headerOf(env));
    const ct = b64decode(env.ciphertext);
    if (ct.length < 16)
        throw new Error('INVALID_ENVELOPE');
    hex(env.ciphertext_digest, 32);
    b64decode(env.signature, 64);
    if (createHash('sha256').update(ct).digest('hex') !== env.ciphertext_digest)
        throw new Error('INVALID_ENVELOPE');
    return env;
}
export function decodeEnvelope(raw: Uint8Array): Envelope {
    if (!(raw instanceof Uint8Array) || raw.length > 256 * 1024)
        throw new Error('MESSAGE_TOO_LARGE');
    const env = strictLoads(raw) as Envelope;
    if (!Buffer.from(raw).equals(Buffer.from(canonicalBytes(env))))
        throw new Error('INVALID_CANONICAL_ENVELOPE');
    return validateEnvelope(env);
}
export const signaturePreimage = (env: Envelope) => concat(text('ResearchHub/SecureEnvelope/v1\0'), canonicalBytes(Object.fromEntries(Object.entries(env).filter(([k]) => k !== 'signature'))));
export async function verifyEnvelope(env: Envelope, pub: Uint8Array): Promise<void> { validateEnvelope(env); await verify(pub, b64decode(env.signature, 64), signaturePreimage(env)); }
export const aad = (header: Envelope) => concat(text('ResearchHub/AEAD/v1\0'), canonicalBytes(header));
export interface Bindings {
    opaque_project_id: string;
    sender_device_id: string;
    membership_epoch: number;
    key_epoch: number;
}
export async function sealRecord(record: unknown, key: Uint8Array, seed: Uint8Array, vault: NonceVault, prefix: number, options: Bindings & {
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
    const header = { envelope_version: 1, crypto_suite: SUITE, protocol_version: options.protocol_version ?? 1, schema_version: options.schema_version ?? 1, record_type: options.record_type ?? 'snapshot', opaque_project_id: options.opaque_project_id, sender_device_id: options.sender_device_id, membership_epoch: options.membership_epoch, key_epoch: options.key_epoch, message_id: options.message_id, semantic_transaction_digest: digest(record), dependencies: options.dependencies ?? [], nonce: '00'.repeat(12), checkpoint_sequence: options.checkpoint_sequence ?? 0 };
    validateHeader(header);
    header.nonce = Buffer.from(vault.reserve(key, prefix)).toString('hex');
    const ct = await aesEncrypt(key, new Uint8Array(Buffer.from(header.nonce, 'hex')), plain, aad(header));
    const env: Envelope = { ...header, ciphertext: b64encode(ct), ciphertext_digest: createHash('sha256').update(ct).digest('hex') };
    env.signature = b64encode(await sign(seed, signaturePreimage(env)));
    return validateEnvelope(env);
}
export async function openRecord(env: Envelope, key: Uint8Array, pub: Uint8Array, bindings: Bindings & {
    nonce_prefix: number;
    record_type?: string;
}): Promise<unknown> {
    await verifyEnvelope(env, pub);
    for (const f of ['opaque_project_id', 'sender_device_id', 'membership_epoch', 'key_epoch'] as const)
        if (env[f] !== bindings[f])
            throw new Error('ENVELOPE_BINDING_MISMATCH');
    if (env.record_type !== (bindings.record_type ?? 'snapshot'))
        throw new Error('ENVELOPE_BINDING_MISMATCH');
    const nonce = Buffer.from(env.nonce, 'hex'), counter = nonce.readBigUInt64BE(4);
    if (nonce.readUInt32BE() !== bindings.nonce_prefix || counter < 1n || counter > 9007199254740991n)
        throw new Error('NONCE_BINDING_MISMATCH');
    const raw = await aesDecrypt(key, nonce, b64decode(env.ciphertext), aad(headerOf(env)));
    let value: unknown;
    try {
        value = strictLoads(raw);
    }
    catch {
        throw new Error('INVALID_PLAINTEXT');
    }
    if (!Buffer.from(raw).equals(Buffer.from(canonicalBytes(value))) || digest(value) !== env.semantic_transaction_digest)
        throw new Error('SEMANTIC_DIGEST_MISMATCH');
    return value;
}
export async function sealTransaction(tx: unknown, key: Uint8Array, seed: Uint8Array, vault: NonceVault, prefix: number, options: Bindings & {
    message_id: string;
    checkpoint_sequence?: number;
}): Promise<Envelope> {
    const value = validateTransaction(tx);
    if (value.device_id !== options.sender_device_id)
        throw new Error('DEVICE_MISMATCH');
    return sealRecord(value, key, seed, vault, prefix, { ...options, dependencies: value.dependencies, record_type: 'transaction', protocol_version: value.protocol_version, schema_version: value.schema_version });
}
export async function openTransaction(env: Envelope, key: Uint8Array, pub: Uint8Array, bindings: Bindings & {
    nonce_prefix: number;
    project_id: string;
}): Promise<unknown> {
    const tx = validateTransaction(await openRecord(env, key, pub, { ...bindings, record_type: 'transaction' }));
    if (tx.protocol_version !== env.protocol_version || tx.schema_version !== env.schema_version || tx.project_id !== bindings.project_id || tx.device_id !== env.sender_device_id || JSON.stringify(tx.dependencies) !== JSON.stringify(env.dependencies))
        throw new Error('TRANSACTION_BINDING_MISMATCH');
    return tx;
}
