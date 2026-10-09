import {validateAnchor,verifyCheckpoint,verifyAdvance,chainSteps} from './checkpoint-core.ts';
/** Independent TEST ONLY checkpoint anchors and minimal signed encrypted snapshot. */
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { canonicalBytes, digest, strictLoads } from '../../sync-protocol/src/canonical.ts';
import { fields, hex, integer, uuid, memberOf, verifySigned, verifyActiveEnvelope, type PublicObject } from './membership.ts';
import { Device, signedObject } from './keys.ts';
import { b64decode, openRecord, sealRecord } from './envelope.ts';
import { NonceVault } from './nonce.ts';
export {validateAnchor,verifyCheckpoint,verifyAdvance} from './checkpoint-core.ts';
export function extendChain(previous:string,cursor:number,rows:PublicObject[]):string {let chain=previous;for(const row of chainSteps(previous,cursor,rows))chain=digest({previous_digest:chain,...row});return chain;}
export async function signCheckpoint(m: PublicObject, creator: Device, cursor: number, chain: string): Promise<PublicObject> {
    return verifyCheckpoint(await signedObject('Checkpoint', {
        version: 1, opaque_project_id: m.opaque_project_id, membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, cursor, chain_digest: chain, creator_device_id: creator.deviceId
    }, creator.signingSeed), m);
}
export class CheckpointStore {
    path: string;
    constructor(path: string) {
        this.path = path;
        mkdirSync(dirname(path), {
            recursive: true
        });
        const db = this.connect();
        try {
            db.exec("CREATE TABLE IF NOT EXISTS anchors(project TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('BOOTSTRAP','SIGNED')),verification BLOB)");
            const columns = db.prepare('PRAGMA table_info(anchors)').all() as {name: string}[];
            if (!columns.some(column => column.name === 'kind')) throw new Error('CHECKPOINT_STORE_KIND_REQUIRED');
            if (!columns.some(column => column.name === 'verification')) throw new Error('CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED');
            db.exec('COMMIT');
        }
        finally {
            db.close();
        }
    }
    connect(): DatabaseSync {
        const db = new DatabaseSync(this.path);
        db.exec('PRAGMA busy_timeout=30000; PRAGMA synchronous=FULL; BEGIN IMMEDIATE');
        return db;
    }
    pin(project: string, cursor = 0, chain = '0'.repeat(64)): void {
        uuid(project);
        integer(cursor);
        hex(chain, 32);
        if (cursor === 0 && chain !== '0'.repeat(64))
            throw new Error('INVALID_GENESIS_CHAIN');
        const db = this.connect();
        try {
            if (db.prepare('SELECT 1 FROM anchors WHERE project=?').get(project))
                throw new Error('CHECKPOINT_ALREADY_PINNED');
            db.prepare("INSERT INTO anchors VALUES (?,?,'BOOTSTRAP',NULL)").run(project, canonicalBytes({
                opaque_project_id: project, cursor, chain_digest: chain
            }));
            db.exec('COMMIT');
        }
        finally {
            db.close();
        }
    }
    async get(project: string, db?: DatabaseSync): Promise<PublicObject> {
        if (!db) {
            const conn = this.connect();
            try {
                return await this.get(project, conn);
            }
            finally {
                conn.close();
            }
        }
        return (await this.anchor(project, db)).value;
    }
    private async anchor(project: string, db: DatabaseSync): Promise<{value: PublicObject; kind: string}> {
        const row = db.prepare('SELECT body,kind,verification FROM anchors WHERE project=?').get(project) as {body: Uint8Array; kind: string; verification: Uint8Array | null} | undefined;
        if (!row)
            throw new Error('CHECKPOINT_ANCHOR_REQUIRED');
        if (!['BOOTSTRAP', 'SIGNED'].includes(row.kind)) throw new Error('INVALID_CHECKPOINT_KIND');
        const value = strictLoads(row.body) as PublicObject;
        validateAnchor(value, row.kind === 'BOOTSTRAP');
        if (value.opaque_project_id !== project) throw new Error('CHECKPOINT_BINDING_MISMATCH');
        if (row.kind === 'BOOTSTRAP') {
            if (row.verification !== null) throw new Error('INVALID_CHECKPOINT_VERIFICATION_CONTEXT');
        } else {
            if (!row.verification) throw new Error('CHECKPOINT_VERIFICATION_CONTEXT_REQUIRED');
            const context = strictLoads(row.verification) as PublicObject;
            fields(context, 'version opaque_project_id membership_epoch key_epoch creator_device_id signing_public_key checkpoint_digest'.split(' '));
            integer(context.version, 1, 1); integer(context.membership_epoch, 1); integer(context.key_epoch, 1);
            uuid(context.opaque_project_id); uuid(context.creator_device_id);
            for (const name of ['signing_public_key', 'checkpoint_digest']) hex(context[name], 32);
            if (['opaque_project_id', 'membership_epoch', 'key_epoch', 'creator_device_id'].some(name => context[name] !== value[name])) throw new Error('CHECKPOINT_BINDING_MISMATCH');
            // Retain the creator key authenticated at commit, even after revocation.
            await verifySigned('Checkpoint', value, context.signing_public_key);
            if (context.checkpoint_digest !== digest(value)) throw new Error('CHECKPOINT_BINDING_MISMATCH');
        }
        return {value, kind: row.kind};
    }
    async advance(cp: PublicObject, m: PublicObject, rows: PublicObject[]): Promise<PublicObject> {
        const db = this.connect();
        try {
            const anchor = await this.anchor(cp.opaque_project_id, db);
            await verifyAdvance(anchor.value, cp, m, rows, anchor.kind === 'BOOTSTRAP');
            const context = {
                version: 1, opaque_project_id: cp.opaque_project_id, membership_epoch: cp.membership_epoch, key_epoch: cp.key_epoch,
                creator_device_id: cp.creator_device_id, signing_public_key: memberOf(m, cp.creator_device_id).signing_public_key,
                checkpoint_digest: digest(cp)
            };
            db.prepare("UPDATE anchors SET body=?,kind='SIGNED',verification=? WHERE project=?").run(canonicalBytes(cp), canonicalBytes(context), cp.opaque_project_id);
            db.exec('COMMIT');
            return cp;
        }
        finally {
            db.close();
        }
    }
}
export async function snapshotRecord(state: unknown, moduleHash: string, cp: PublicObject, m: PublicObject, creator: Device): Promise<PublicObject> {
    await verifyCheckpoint(cp, m);
    hex(moduleHash, 32);
    return {
        manifest: await signedObject('SnapshotManifest', {
            version: 1, opaque_project_id: m.opaque_project_id, snapshot_cursor: cp.cursor, checkpoint_digest: digest(cp), module_snapshot_hash: moduleHash, state_digest: digest(state), key_epoch: m.key_epoch, creator_device_id: creator.deviceId
        }, creator.signingSeed), state
    };
}
export async function verifySnapshotRecord(record: PublicObject, m: PublicObject, cp: PublicObject, moduleHash: string): Promise<unknown> {
    fields(record, ['manifest', 'state']);
    const inner = record.manifest;
    fields(inner, 'version opaque_project_id snapshot_cursor checkpoint_digest module_snapshot_hash state_digest key_epoch creator_device_id signature'.split(' '));
    integer(inner.version, 1, 1);
    integer(inner.snapshot_cursor);
    integer(inner.key_epoch, 1);
    await verifyCheckpoint(cp, m);
    if (inner.opaque_project_id !== m.opaque_project_id || inner.snapshot_cursor !== cp.cursor || inner.checkpoint_digest !== digest(cp) || inner.key_epoch !== m.key_epoch || inner.module_snapshot_hash !== moduleHash || inner.state_digest !== digest(record.state))
        throw new Error('SNAPSHOT_BINDING_MISMATCH');
    hex(moduleHash, 32);
    await verifySigned('SnapshotManifest', inner, memberOf(m, inner.creator_device_id).signing_public_key);
    return record.state;
}
export async function sealSnapshot(state: unknown, moduleHash: string, cp: PublicObject, m: PublicObject, creator: Device, key: Uint8Array, vault: NonceVault, message: string): Promise<PublicObject> {
    const member = memberOf(m, creator.deviceId, ['owner', 'writer']);
    return sealRecord(await snapshotRecord(state, moduleHash, cp, m, creator), key, creator.signingSeed, vault, member.nonce_prefix, {
        opaque_project_id: m.opaque_project_id, sender_device_id: creator.deviceId, membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, message_id: message, checkpoint_sequence: cp.cursor, record_type: 'snapshot'
    });
}
export async function openSnapshot(env: PublicObject, m: PublicObject, key: Uint8Array, cp: PublicObject, moduleHash: string): Promise<unknown> {
    await verifyActiveEnvelope(env, m);
    const member = memberOf(m, env.sender_device_id);
    if (env.checkpoint_sequence !== cp.cursor)
        throw new Error('SNAPSHOT_BINDING_MISMATCH');
    const record = await openRecord(env, key, hex(member.signing_public_key, 32), {
        opaque_project_id: m.opaque_project_id, sender_device_id: member.device_id, membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, nonce_prefix: member.nonce_prefix, record_type: 'snapshot'
    }) as PublicObject;
    if (record.manifest.creator_device_id !== member.device_id)
        throw new Error('SNAPSHOT_BINDING_MISMATCH');
    return verifySnapshotRecord(record, m, cp, moduleHash);
}
