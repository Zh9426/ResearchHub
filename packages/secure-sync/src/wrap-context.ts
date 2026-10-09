import { canonicalBytes } from '../../sync-protocol/src/canonical-core.ts';
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
