import {sealWithNonce} from './envelope-core.ts';
import {SUITE,recordHeader,headerOf,validateHeader,signaturePreimage,aad,validateEnvelopeShape,decodeEnvelopeShape,type Envelope} from './envelope-shape.ts';
import {b64encode,b64decode} from './binary.ts';
import { createHash } from 'node:crypto';
import { canonicalBytes, strictLoads, digest } from '../../sync-protocol/src/canonical.ts';
import { validateTransaction, requireVersionPair } from '../../sync-protocol/src/protocol.ts';
import { aesEncrypt, aesDecrypt, sign, verify } from './crypto.ts';
import { NonceVault } from './nonce.ts';
export {SUITE,HEADER_FIELDS,headerOf,validateHeader,signaturePreimage,aad} from './envelope-shape.ts';
export type {Envelope} from './envelope-shape.ts';
export {b64encode,b64decode} from './binary.ts';
export function validateEnvelope(env:Envelope):Envelope { const ct=validateEnvelopeShape(env);if(createHash('sha256').update(ct).digest('hex')!==env.ciphertext_digest)throw Error('INVALID_ENVELOPE');return env; }
export function decodeEnvelope(raw:Uint8Array):Envelope {return validateEnvelope(decodeEnvelopeShape(raw));}
export async function verifyEnvelope(env:Envelope,pub:Uint8Array):Promise<void>{validateEnvelope(env);await verify(pub,b64decode(env.signature,64),signaturePreimage(env));}
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
    if(canonicalBytes(record).length>180*1024)throw Error('MESSAGE_TOO_LARGE');
    validateHeader(recordHeader(digest(record),options));
    return sealWithNonce(record,key,value=>sign(seed,value),vault.reserve(key,prefix),options);
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
export {openRecord,openTransaction} from './envelope-core.ts';
