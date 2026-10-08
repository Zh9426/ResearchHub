/** 1 MiB bounded synthetic artifact prototype, no production storage integration. */
import { randomBytes, createHash } from 'node:crypto';
import { canonicalBytes, digest } from '../../sync-protocol/src/canonical.ts';
import { aesEncrypt, aesDecrypt, kwWrap, kwUnwrap } from './crypto.ts';
import { b64encode, b64decode, openRecord, sealRecord } from './envelope.ts';
import { fields, integer, hex, uuid, memberOf, verifySigned, verifyActiveEnvelope, type PublicObject } from './membership.ts';
import { Device, signedObject } from './keys.ts';
import { NonceVault } from './nonce.ts';
export const MAX_CHUNK = 65536, MAX_ARTIFACT = 1048576;
const CF = 'opaque_project_id opaque_locator key_epoch index total size manifest_identity nonce ciphertext'.split(' '), META = ['filename', 'category', 'run_title'];
export interface StagingSink {
    begin(identity: string): boolean;
    write(index: number, value: Uint8Array): void;
    commit(): void;
    abort(): void;
}
export class TestOnlyMemoryStagingSink implements StagingSink {
    identity?: string;
    ready = false;
    data: Uint8Array = new Uint8Array();
    writes = 0;
    begin(id: string): boolean {
        if (this.ready) {
            if (id !== this.identity)
                throw new Error('ARTIFACT_IDENTITY_COLLISION');
            return false;
        }
        this.identity = id;
        this.data = new Uint8Array();
        return true;
    }
    write(_index: number, value: Uint8Array): void {
        this.data = new Uint8Array(Buffer.concat([this.data, value]));
        this.writes++;
    }
    commit(): void {
        this.ready = true;
    }
    abort(): void {
        this.data = new Uint8Array();
        this.ready = false;
    }
}
export function chunkAad(c: PublicObject): Uint8Array {
    return new Uint8Array(Buffer.concat([Buffer.from('ResearchHub/ArtifactChunk/v1\0'), Buffer.from(canonicalBytes(Object.fromEntries(CF.filter(f => !['nonce', 'ciphertext'].includes(f)).map(f => [f, c[f]]))))]));
}
export function validateChunkOrder(chunks: PublicObject[], total: number): void {
    if (!Array.isArray(chunks) || chunks.length !== total || chunks.some((c, i) => c.index !== i))
        throw new Error('ARTIFACT_CHUNK_ORDER');
}
function validateMetadata(meta: PublicObject): void {
    fields(meta, META);
    if (Object.values(meta).some(v => typeof v !== 'string' || [...v].length > 1024))
        throw new Error('INVALID_ARTIFACT_METADATA');
}
export async function sealArtifact(parts: Iterable<Uint8Array>, meta: PublicObject, m: PublicObject, creator: Device, projectKey: Uint8Array, vault: NonceVault, locator: string): Promise<PublicObject> {
    uuid(locator);
    validateMetadata(meta);
    const member = memberOf(m, creator.deviceId, ['owner', 'writer']), bounded: Uint8Array[] = [], sha = createHash('sha256');
    let size = 0;
    for (const part of parts) {
        if (!(part instanceof Uint8Array) || part.length < 1 || part.length > MAX_CHUNK)
            throw new Error('INVALID_ARTIFACT_CHUNK_SIZE');
        size += part.length;
        if (size > MAX_ARTIFACT || bounded.length >= 16)
            throw new Error('ARTIFACT_TOO_LARGE');
        bounded.push(Uint8Array.from(part));
        sha.update(part);
    }
    if (!bounded.length)
        throw new Error('EMPTY_ARTIFACT');
    const dek = randomBytes(32);
    vault.registerNew(dek, member.nonce_prefix);
    const inner = await signedObject('ArtifactManifest', {
        version: 1, opaque_project_id: m.opaque_project_id, opaque_locator: locator, key_epoch: m.key_epoch, creator_device_id: creator.deviceId, total_size: size, total_chunks: bounded.length, plaintext_digest: sha.digest('hex'), chunk_sizes: bounded.map(p => p.length), metadata: meta, wrapped_dek: b64encode(await kwWrap(projectKey, dek)), nonce_prefix: member.nonce_prefix
    }, creator.signingSeed), identity = digest(inner), chunks: PublicObject[] = [];
    for (let index = 0; index < bounded.length; index++) {
        const part = bounded[index], chunk: PublicObject = {
            opaque_project_id: m.opaque_project_id, opaque_locator: locator, key_epoch: m.key_epoch, index, total: bounded.length, size: part.length, manifest_identity: identity
        }, nonce = vault.reserve(dek, member.nonce_prefix);
        chunk.nonce = Buffer.from(nonce).toString('hex');
        chunk.ciphertext = b64encode(await aesEncrypt(dek, nonce, part, chunkAad(chunk)));
        chunks.push(chunk);
    }
    const env = await sealRecord(inner, projectKey, creator.signingSeed, vault, member.nonce_prefix, {
        opaque_project_id: m.opaque_project_id, sender_device_id: creator.deviceId, membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, message_id: locator, record_type: 'artifact_manifest'
    });
    return {
        manifest_envelope: env, chunks
    };
}
export async function openArtifact(bundle: PublicObject, m: PublicObject, projectKey: Uint8Array, sink: StagingSink): Promise<PublicObject> {
    fields(bundle, ['manifest_envelope', 'chunks']);
    const env = bundle.manifest_envelope;
    await verifyActiveEnvelope(env, m);
    const member = memberOf(m, env.sender_device_id), inner = await openRecord(env, projectKey, hex(member.signing_public_key, 32), {
        opaque_project_id: m.opaque_project_id, sender_device_id: member.device_id, membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, nonce_prefix: member.nonce_prefix, record_type: 'artifact_manifest'
    }) as PublicObject;
    fields(inner, 'version opaque_project_id opaque_locator key_epoch creator_device_id total_size total_chunks plaintext_digest chunk_sizes metadata wrapped_dek nonce_prefix signature'.split(' '));
    integer(inner.version, 1, 1);
    integer(inner.key_epoch, 1);
    integer(inner.nonce_prefix, 0, 4294967295);
    uuid(inner.opaque_project_id);
    uuid(inner.opaque_locator);
    uuid(inner.creator_device_id);
    integer(inner.total_size, 1, MAX_ARTIFACT);
    integer(inner.total_chunks, 1, 16);
    hex(inner.plaintext_digest, 32);
    validateMetadata(inner.metadata);
    if (inner.opaque_project_id !== m.opaque_project_id || inner.key_epoch !== m.key_epoch || inner.creator_device_id !== member.device_id || inner.nonce_prefix !== member.nonce_prefix || inner.opaque_locator !== env.message_id || !Array.isArray(inner.chunk_sizes) || inner.chunk_sizes.length !== inner.total_chunks)
        throw new Error('ARTIFACT_BINDING_MISMATCH');
    inner.chunk_sizes.forEach((s: number) => integer(s, 1, MAX_CHUNK));
    if (inner.chunk_sizes.reduce((a: number, b: number) => a + b, 0) !== inner.total_size)
        throw new Error('ARTIFACT_SIZE_MISMATCH');
    await verifySigned('ArtifactManifest', inner, member.signing_public_key);
    const dek = await kwUnwrap(projectKey, b64decode(inner.wrapped_dek, 40)), identity = digest(inner), fresh = sink.begin(digest(bundle));
    try {
        validateChunkOrder(bundle.chunks, inner.total_chunks);
        const sha = createHash('sha256'), nonces = new Set<string>();
        let total = 0;
        for (const c of bundle.chunks) {
            fields(c, CF);
            uuid(c.opaque_project_id);
            uuid(c.opaque_locator);
            integer(c.key_epoch, 1);
            integer(c.index, 0, 15);
            integer(c.total, 1, 16);
            integer(c.size, 1, MAX_CHUNK);
            hex(c.manifest_identity, 32);
            if (c.opaque_project_id !== inner.opaque_project_id || c.opaque_locator !== inner.opaque_locator || c.key_epoch !== inner.key_epoch || c.manifest_identity !== identity || c.total !== inner.total_chunks || c.size !== inner.chunk_sizes[c.index])
                throw new Error('ARTIFACT_BINDING_MISMATCH');
            const nonce = Buffer.from(hex(c.nonce, 12)), counter = nonce.readBigUInt64BE(4);
            if (nonce.readUInt32BE() !== inner.nonce_prefix || counter < 1n || counter > 9007199254740991n || nonces.has(c.nonce))
                throw new Error('NONCE_BINDING_MISMATCH');
            nonces.add(c.nonce);
            const ct = b64decode(c.ciphertext);
            if (ct.length !== c.size + 16)
                throw new Error('ARTIFACT_SIZE_MISMATCH');
            const part = await aesDecrypt(dek, nonce, ct, chunkAad(c));
            total += part.length;
            sha.update(part);
            if (fresh)
                sink.write(c.index, part);
        }
        if (total !== inner.total_size || sha.digest('hex') !== inner.plaintext_digest)
            throw new Error('ARTIFACT_DIGEST_MISMATCH');
        if (fresh)
            sink.commit();
    }
    catch (e) {
        if (fresh)
            sink.abort();
        throw e;
    }
    return inner.metadata;
}
