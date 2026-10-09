import { canonicalBytes, strictLoads } from '../../sync-protocol/src/canonical-core.ts';
import { requireVersionPair } from '../../sync-protocol/src/protocol-core.ts';
import { b64decode, equal, concat, text } from './binary.ts';
export const SUITE = 'RH-v1/AES256GCM/Ed25519/HPKE-X25519-HKDFSHA256-AES256GCM';
export const HEADER_FIELDS = 'envelope_version crypto_suite protocol_version schema_version record_type opaque_project_id sender_device_id membership_epoch key_epoch message_id semantic_transaction_digest dependencies nonce checkpoint_sequence'.split(' ');
export type Envelope = Record<string, any>;
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
export function validateEnvelopeShape(env: Envelope): Uint8Array {
    fields(env, [...HEADER_FIELDS, 'ciphertext', 'ciphertext_digest', 'signature']);
    if (canonicalBytes(env).length > 256 * 1024)
        throw Error('MESSAGE_TOO_LARGE');
    validateHeader(headerOf(env));
    const ct = b64decode(env.ciphertext);
    if (ct.length < 16)
        throw Error('INVALID_ENVELOPE');
    hex(env.ciphertext_digest, 32);
    b64decode(env.signature, 64);
    return ct;
}
export function decodeEnvelopeShape(raw: Uint8Array): Envelope {
    if (!(raw instanceof Uint8Array) || raw.length > 256 * 1024)
        throw Error('MESSAGE_TOO_LARGE');
    const env = strictLoads(raw) as Envelope;
    if (!equal(raw, canonicalBytes(env)))
        throw Error('INVALID_CANONICAL_ENVELOPE');
    validateEnvelopeShape(env);
    return env;
}
export const signaturePreimage = (env: Envelope) => concat(text('ResearchHub/SecureEnvelope/v1\0'), canonicalBytes(Object.fromEntries(Object.entries(env).filter(([k]) => k !== 'signature'))));
export const aad = (header: Envelope) => concat(text('ResearchHub/AEAD/v1\0'), canonicalBytes(header));
export function recordHeader(semanticDigest: string, options: Record<string, any>): Envelope { return { envelope_version: 1, crypto_suite: SUITE, protocol_version: options.protocol_version ?? 1, schema_version: options.schema_version ?? 1, record_type: options.record_type ?? 'snapshot', opaque_project_id: options.opaque_project_id, sender_device_id: options.sender_device_id, membership_epoch: options.membership_epoch, key_epoch: options.key_epoch, message_id: options.message_id, semantic_transaction_digest: semanticDigest, dependencies: options.dependencies ?? [], nonce: '00'.repeat(12), checkpoint_sequence: options.checkpoint_sequence ?? 0 }; }
