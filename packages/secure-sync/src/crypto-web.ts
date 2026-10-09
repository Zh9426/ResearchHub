import { CipherSuite, DhkemX25519HkdfSha256, HkdfSha256, Aes256Gcm } from '@hpke/core';
import { bytes, hexEncode, concat } from './binary.ts';
import { wrapContext, type WrapContext } from './wrap-context.ts';
export type DeviceKeys = {
    deviceId: string;
    signing: CryptoKeyPair;
    recipient: CryptoKeyPair;
    signingPublic: string;
    recipientPublic: string;
};
export const sha256 = async (v: Uint8Array) => hexEncode(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes(v))));
function fixed(v: Uint8Array, n: number) {
    if (!(v instanceof Uint8Array) || v.length !== n)
        throw Error('INVALID_KEY_OR_NONCE');
    return v;
}
export async function generateDevice(deviceId = crypto.randomUUID()): Promise<DeviceKeys> {
    const signing = await crypto.subtle.generateKey('Ed25519', false, ['sign', 'verify']) as CryptoKeyPair;
    const recipient = await crypto.subtle.generateKey('X25519', false, ['deriveBits']) as CryptoKeyPair;
    return { deviceId, signing, recipient, signingPublic: hexEncode(new Uint8Array(await crypto.subtle.exportKey('raw', signing.publicKey))), recipientPublic: hexEncode(new Uint8Array(await crypto.subtle.exportKey('raw', recipient.publicKey))) };
}
export async function importProjectKey(raw: Uint8Array): Promise<{
    key: CryptoKey;
    fingerprint: string;
}> { fixed(raw, 32); const fingerprint = await sha256(raw); return { fingerprint, key: await crypto.subtle.importKey('raw', bytes(raw), 'AES-GCM', false, ['encrypt', 'decrypt']) }; }
export async function sign(key: CryptoKey, message: Uint8Array): Promise<Uint8Array> { return new Uint8Array(await crypto.subtle.sign('Ed25519', key, bytes(message))); }
export async function verify(pub: Uint8Array, sig: Uint8Array, message: Uint8Array): Promise<void> {
    const key = await crypto.subtle.importKey('raw', bytes(fixed(pub, 32)), 'Ed25519', false, ['verify']);
    if (!await crypto.subtle.verify('Ed25519', key, bytes(fixed(sig, 64)), bytes(message)))
        throw Error('INVALID_SIGNATURE');
}
async function aesKey(key: CryptoKey | Uint8Array) { return key instanceof Uint8Array ? (await importProjectKey(key)).key : key; }
export async function aesEncrypt(key: CryptoKey | Uint8Array, nonce: Uint8Array, plain: Uint8Array, aad: Uint8Array): Promise<Uint8Array> { return new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: bytes(fixed(nonce, 12)), additionalData: bytes(aad), tagLength: 128 }, await aesKey(key), bytes(plain))); }
export async function aesDecrypt(key: CryptoKey | Uint8Array, nonce: Uint8Array, ct: Uint8Array, aad: Uint8Array): Promise<Uint8Array> {
    try {
        return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes(fixed(nonce, 12)), additionalData: bytes(aad), tagLength: 128 }, await aesKey(key), bytes(ct)));
    }
    catch {
        throw Error('DECRYPT_FAILED');
    }
}
const suite = () => new CipherSuite({ kem: new DhkemX25519HkdfSha256(), kdf: new HkdfSha256(), aead: new Aes256Gcm() });
export async function wrapKey(pub: Uint8Array, key: Uint8Array, context: WrapContext): Promise<Uint8Array> {
    const info = wrapContext(context);
    if (hexEncode(fixed(pub, 32)) !== context.recipient_public_key)
        throw Error('RECIPIENT_MISMATCH');
    const hpke = suite();
    const sender = await hpke.createSenderContext({ recipientPublicKey: await hpke.kem.deserializePublicKey(bytes(pub)), info: bytes(info) });
    return concat(new Uint8Array(sender.enc), new Uint8Array(await sender.seal(bytes(fixed(key, 32)))));
}
/** Pass the COMPLETE pair: deriving a public key from a nonextractable private key is forbidden. */
export async function unwrapKey(pair: CryptoKeyPair, wrapped: Uint8Array, context: WrapContext): Promise<Uint8Array> {
    const info = wrapContext(context);
    const pub = hexEncode(new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey)));
    if (pub !== context.recipient_public_key || wrapped.length !== 80)
        throw Error('RECIPIENT_MISMATCH');
    try {
        const recipient = await suite().createRecipientContext({ recipientKey: pair, enc: bytes(wrapped.subarray(0, 32)), info: bytes(info) });
        return fixed(new Uint8Array(await recipient.open(bytes(wrapped.subarray(32)))), 32);
    }
    catch {
        throw Error('UNWRAP_FAILED');
    }
}
