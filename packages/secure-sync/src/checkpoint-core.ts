import { digest } from '../../sync-protocol/src/browser.ts';
import { fields, hex, integer, uuid, memberOf, verifySigned, type PublicObject } from './membership-core.ts';
import { b64decode } from './binary.ts';
export function* chainSteps(previous: string, cursor: number, rows: PublicObject[]): Generator<PublicObject, void, unknown> {
    hex(previous, 32);
    integer(cursor);
    if (cursor === 0 && previous !== '0'.repeat(64))
        throw new Error('INVALID_GENESIS_CHAIN');
    if (!Array.isArray(rows) || rows.length > 100)
        throw new Error('INVALID_CHECKPOINT_PAGE');
    for (const row of rows) {
        fields(row, ['sequence', 'envelope_digest']);
        integer(row.sequence, 1);
        hex(row.envelope_digest, 32);
        if (row.sequence !== cursor + 1)
            throw new Error('CURSOR_GAP');
        yield row;
        cursor++;
    }
}
export async function extendChain(previous: string, cursor: number, rows: PublicObject[]): Promise<string> {
    let chain = previous;
    for (const row of chainSteps(previous, cursor, rows))
        chain = await digest({ previous_digest: chain, ...row });
    return chain;
}
export function validateAnchor(cp: PublicObject, bootstrap = false): void {
    if (typeof bootstrap !== 'boolean')
        throw new Error('INVALID_CHECKPOINT_KIND');
    fields(cp, (bootstrap ? 'opaque_project_id cursor chain_digest' : 'version opaque_project_id membership_epoch key_epoch cursor chain_digest creator_device_id signature').split(' '));
    integer(cp.cursor);
    uuid(cp.opaque_project_id);
    hex(cp.chain_digest, 32);
    if (cp.cursor === 0 && cp.chain_digest !== '0'.repeat(64))
        throw new Error('INVALID_GENESIS_CHAIN');
    if (!bootstrap) {
        integer(cp.version, 1, 1);
        integer(cp.key_epoch, 1);
        integer(cp.membership_epoch, 1);
        uuid(cp.creator_device_id);
        b64decode(cp.signature, 64);
    }
}
export async function verifyCheckpoint(cp: PublicObject, manifest: PublicObject): Promise<PublicObject> {
    validateAnchor(cp);
    if (cp.opaque_project_id !== manifest.opaque_project_id || cp.key_epoch !== manifest.key_epoch || cp.membership_epoch !== manifest.membership_epoch)
        throw new Error('CHECKPOINT_BINDING_MISMATCH');
    await verifySigned('Checkpoint', cp, memberOf(manifest, cp.creator_device_id).signing_public_key);
    return cp;
}
export async function verifyAdvance(anchor: PublicObject, cp: PublicObject, m: PublicObject, rows: PublicObject[], bootstrap = false): Promise<PublicObject> {
    validateAnchor(anchor, bootstrap);
    await verifyCheckpoint(cp, m);
    if (anchor.opaque_project_id !== cp.opaque_project_id)
        throw new Error('CHECKPOINT_BINDING_MISMATCH');
    if (!bootstrap && (cp.membership_epoch < anchor.membership_epoch || cp.key_epoch < anchor.key_epoch))
        throw new Error('ROLLBACK_DETECTED');
    if (cp.cursor < anchor.cursor || (cp.cursor === anchor.cursor && cp.chain_digest !== anchor.chain_digest))
        throw new Error('ROLLBACK_DETECTED');
    if (cp.cursor !== anchor.cursor + rows.length)
        throw new Error('CURSOR_GAP');
    if (await extendChain(anchor.chain_digest, anchor.cursor, rows) !== cp.chain_digest)
        throw new Error('CHAIN_DIGEST_MISMATCH');
    return cp;
}
