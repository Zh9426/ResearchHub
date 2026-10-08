import { webcrypto, createPrivateKey, createPublicKey } from 'node:crypto';
import { CipherSuite, DhkemX25519HkdfSha256, HkdfSha256, Aes256Gcm } from '@hpke/core';
import { canonicalBytes } from '../../sync-protocol/src/canonical.ts';
const subtle = webcrypto.subtle;
export function bytes(value: Uint8Array): ArrayBuffer { return Uint8Array.from(value).buffer; }
function fixed(value: Uint8Array, size: number): Uint8Array {
    if (!(value instanceof Uint8Array) || value.length !== size)
        throw new Error('INVALID_KEY_OR_NONCE');
    return value;
}
const privateDer = (seed: Uint8Array, oid: string) => Buffer.concat([Buffer.from('302e020100300506032b' + oid + '04220420', 'hex'), Buffer.from(fixed(seed, 32))]);
export async function signingPublic(seed: Uint8Array): Promise<Uint8Array> { return new Uint8Array(createPublicKey(createPrivateKey({ key: privateDer(seed, '6570'), format: 'der', type: 'pkcs8' })).export({ format: 'der', type: 'spki' }).subarray(-32)); }
export async function recipientPublic(seed: Uint8Array): Promise<Uint8Array> { return new Uint8Array(createPublicKey(createPrivateKey({ key: privateDer(seed, '656e'), format: 'der', type: 'pkcs8' })).export({ format: 'der', type: 'spki' }).subarray(-32)); }
export async function sign(seed: Uint8Array, message: Uint8Array): Promise<Uint8Array> {
    const key = await subtle.importKey('pkcs8', privateDer(seed, '6570'), 'Ed25519', false, ['sign']);
    return new Uint8Array(await subtle.sign('Ed25519', key, bytes(message)));
}
export async function verify(pub: Uint8Array, sig: Uint8Array, message: Uint8Array): Promise<void> {
    const key = await subtle.importKey('raw', bytes(fixed(pub, 32)), 'Ed25519', false, ['verify']);
    if (!await subtle.verify('Ed25519', key, bytes(fixed(sig, 64)), bytes(message)))
        throw new Error('INVALID_SIGNATURE');
}
async function aes(key: Uint8Array, usage: 'encrypt' | 'decrypt') { return subtle.importKey('raw', bytes(fixed(key, 32)), 'AES-GCM', false, [usage]); }
export async function aesEncrypt(key: Uint8Array, nonce: Uint8Array, plaintext: Uint8Array, aad: Uint8Array): Promise<Uint8Array> {
    return new Uint8Array(await subtle.encrypt({ name: 'AES-GCM', iv: bytes(fixed(nonce, 12)), additionalData: bytes(aad), tagLength: 128 }, await aes(key, 'encrypt'), bytes(plaintext)));
}
export async function aesDecrypt(key: Uint8Array, nonce: Uint8Array, ciphertext: Uint8Array, aad: Uint8Array): Promise<Uint8Array> {
    try {
        return new Uint8Array(await subtle.decrypt({ name: 'AES-GCM', iv: bytes(fixed(nonce, 12)), additionalData: bytes(aad), tagLength: 128 }, await aes(key, 'decrypt'), bytes(ciphertext)));
    }
    catch {
        throw new Error('DECRYPT_FAILED');
    }
}
export interface WrapContext {
    opaque_project_id: string;
    recipient_device_id: string;
    key_epoch: number;
    membership_epoch: number;
    session_id: string;
    recipient_signing_public_key: string;
    recipient_public_key: string;
}
export function wrapContext(context: WrapContext): Uint8Array {
    const fields = 'opaque_project_id recipient_device_id key_epoch membership_epoch session_id recipient_signing_public_key recipient_public_key'.split(' ').sort();
    if (Object.keys(context).sort().join() != fields.join())
        throw new Error('INVALID_WRAP_CONTEXT');
    for (const f of ['opaque_project_id', 'recipient_device_id', 'session_id'] as const)
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(context[f]) || context[f] === '00000000-0000-0000-0000-000000000000')
            throw new Error('INVALID_WRAP_CONTEXT');
    for (const n of [context.key_epoch, context.membership_epoch])
        if (!Number.isSafeInteger(n) || n < 1)
            throw new Error('INVALID_WRAP_CONTEXT');
    for (const f of ['recipient_public_key', 'recipient_signing_public_key'] as const)
        if (!/^[0-9a-f]{64}$/.test(context[f]))
            throw new Error('INVALID_WRAP_CONTEXT');
    return canonicalBytes(context);
}
const suite = () => new CipherSuite({ kem: new DhkemX25519HkdfSha256(), kdf: new HkdfSha256(), aead: new Aes256Gcm() });
export async function wrapKey(pub: Uint8Array, key: Uint8Array, context: WrapContext): Promise<Uint8Array> {
    const info = wrapContext(context);
    if (Buffer.from(fixed(pub, 32)).toString('hex') !== context.recipient_public_key)
        throw new Error('RECIPIENT_MISMATCH');
    const hpke = suite(), recipientPublicKey = await hpke.kem.deserializePublicKey(bytes(pub));
    const sender = await hpke.createSenderContext({ recipientPublicKey, info: bytes(info) });
    const ct = await sender.seal(bytes(fixed(key, 32)));
    return new Uint8Array(Buffer.concat([Buffer.from(sender.enc), Buffer.from(ct)]));
}
export async function unwrapKey(seed: Uint8Array, wrapped: Uint8Array, context: WrapContext): Promise<Uint8Array> {
    const info = wrapContext(context);
    if (Buffer.from(await recipientPublic(seed)).toString('hex') !== context.recipient_public_key || wrapped.length !== 80)
        throw new Error('RECIPIENT_MISMATCH');
    const hpke = suite(), recipientKey = await hpke.kem.deserializePrivateKey(bytes(fixed(seed, 32)));
    try {
        const recipient = await hpke.createRecipientContext({ recipientKey, enc: bytes(wrapped.subarray(0, 32)), info: bytes(info) });
        return fixed(new Uint8Array(await recipient.open(bytes(wrapped.subarray(32)))), 32);
    }
    catch {
        throw new Error('UNWRAP_FAILED');
    }
}
export async function kwWrap(key: Uint8Array, dek: Uint8Array): Promise<Uint8Array> {
    const kek = await subtle.importKey('raw', bytes(fixed(key, 32)), 'AES-KW', false, ['wrapKey']);
    const material = await subtle.importKey('raw', bytes(fixed(dek, 32)), 'AES-GCM', true, ['encrypt']);
    return new Uint8Array(await subtle.wrapKey('raw', material, kek, 'AES-KW'));
}
export async function kwUnwrap(key: Uint8Array, wrapped: Uint8Array): Promise<Uint8Array> {
    try {
        const kek = await subtle.importKey('raw', bytes(fixed(key, 32)), 'AES-KW', false, ['unwrapKey']);
        const material = await subtle.unwrapKey('raw', bytes(wrapped), kek, 'AES-KW', 'AES-GCM', true, ['encrypt']);
        return fixed(new Uint8Array(await subtle.exportKey('raw', material)), 32);
    }
    catch {
        throw new Error('UNWRAP_FAILED');
    }
}
