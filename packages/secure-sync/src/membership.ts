/** Public-only independently implemented lifecycle verifier. */
import { canonicalBytes, digest } from '../../sync-protocol/src/canonical.ts';
import { verify } from './crypto.ts';
import { b64decode, validateEnvelope, verifyEnvelope, type Envelope } from './envelope.ts';
export type PublicObject = Record<string, any>;
export const ZERO = '0'.repeat(64);
const MF = 'device_id signing_public_key recipient_public_key fingerprint role status nonce_prefix granted_at revoked_at'.split(' ');
export function fields(value: PublicObject, expected: string[]): void {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== [...expected].sort().join())
        throw new Error('INVALID_SIGNED_OBJECT');
    canonicalBytes(value);
}
export function integer(v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): void {
    if (typeof v !== 'number' || !Number.isSafeInteger(v) || Object.is(v, -0) || v < min || v > max)
        throw new Error('INVALID_SIGNED_OBJECT');
}
export function hex(v: unknown, size: number): Uint8Array {
    if (typeof v !== 'string' || !(new RegExp('^[0-9a-f]{' + size * 2 + '}$')).test(v))
        throw new Error('INVALID_SIGNED_OBJECT');
    return new Uint8Array(Buffer.from(v, 'hex'));
}
export function uuid(v: unknown): void {
    if (typeof v !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v) || v === '00000000-0000-0000-0000-000000000000')
        throw new Error('INVALID_SIGNED_OBJECT');
}
export function preimage(kind: string, value: PublicObject): Uint8Array {
    return new Uint8Array(Buffer.concat([Buffer.from('ResearchHub/' + kind + '/v1\0'), Buffer.from(canonicalBytes(Object.fromEntries(Object.entries(value).filter(([k]) => k !== 'signature'))))]));
}
export async function verifySigned(kind: string, value: PublicObject, pub: string): Promise<void> {
    await verify(hex(pub, 32), b64decode(value.signature, 64), preimage(kind, value));
}
export function fingerprint(signing: string, recipient: string): string {
    hex(signing, 32);
    hex(recipient, 32);
    return digest({
        signing_public_key: signing, recipient_public_key: recipient
    });
}
export function validateMember(m: PublicObject): void {
    fields(m, MF);
    uuid(m.device_id);
    if (m.fingerprint !== fingerprint(m.signing_public_key, m.recipient_public_key))
        throw new Error('FINGERPRINT_MISMATCH');
    if (!['owner', 'writer', 'reader'].includes(m.role) || !['PENDING', 'ACTIVE', 'REVOKED'].includes(m.status))
        throw new Error('INVALID_MEMBERSHIP');
    integer(m.nonce_prefix, 0, 4294967295);
    integer(m.granted_at);
    if (m.status === 'REVOKED')
        integer(m.revoked_at, m.granted_at);
    else if (m.revoked_at !== null)
        throw new Error('INVALID_MEMBERSHIP');
}
export function validateManifest(m: PublicObject): void {
    fields(m, 'version opaque_project_id membership_epoch key_epoch previous_digest operation authority_device_id recovery_device_id recovery_signing_public_key recovery_recipient_public_key members signature'.split(' '));
    integer(m.version, 1, 1);
    uuid(m.opaque_project_id);
    uuid(m.authority_device_id);
    integer(m.membership_epoch, 1);
    integer(m.key_epoch, 1);
    hex(m.previous_digest, 32);
    hex(m.recovery_signing_public_key, 32);
    hex(m.recovery_recipient_public_key, 32);
    uuid(m.recovery_device_id);
    b64decode(m.signature, 64);
    if (!['bootstrap', 'grant', 'revoke', 'recovery'].includes(m.operation) || !Array.isArray(m.members) || m.members.length < 1 || m.members.length > 1024)
        throw new Error('INVALID_MEMBERSHIP');
    m.members.forEach(validateMember);
    if (new Set(m.members.map((v: PublicObject) => v.device_id)).size !== m.members.length || new Set(m.members.map((v: PublicObject) => v.nonce_prefix)).size !== m.members.length)
        throw new Error('PREFIX_OR_DEVICE_COLLISION');
    if (!m.members.some((v: PublicObject) => v.status === 'ACTIVE' && v.role === 'owner'))
        throw new Error('NO_ACTIVE_OWNER');
}
export function memberOf(m: PublicObject, id: string, roles?: string[]): PublicObject {
    const member = m.members.find((v: PublicObject) => v.device_id === id);
    if (!member)
        throw new Error('UNKNOWN_DEVICE');
    if (member.status === 'REVOKED')
        throw new Error('REVOKED_DEVICE');
    if (member.status !== 'ACTIVE' || (roles && !roles.includes(member.role)))
        throw new Error('UNAUTHORIZED_DEVICE');
    return member;
}
export async function verifyBootstrap(m: PublicObject, owner: string, recovery: string): Promise<PublicObject> {
    validateManifest(m);
    const a = memberOf(m, m.authority_device_id, ['owner']);
    if (m.operation !== 'bootstrap' || m.previous_digest !== ZERO || m.membership_epoch !== 1 || m.key_epoch !== 1 || m.members.length !== 1 || a.signing_public_key !== owner || m.recovery_signing_public_key !== recovery)
        throw new Error('UNTRUSTED_BOOTSTRAP');
    await verifySigned('Membership', m, owner);
    return m;
}
export async function verifyTransition(previous: PublicObject, candidate: PublicObject, recovery: string): Promise<PublicObject> {
    validateManifest(previous);
    validateManifest(candidate);
    if (candidate.membership_epoch === previous.membership_epoch) {
        if (digest(candidate) === digest(previous))
            return previous;
        throw new Error('MEMBERSHIP_FORK');
    }
    if (candidate.opaque_project_id !== previous.opaque_project_id || candidate.previous_digest !== digest(previous) || candidate.membership_epoch !== previous.membership_epoch + 1)
        throw new Error('MEMBERSHIP_CAS_MISMATCH');
    const op = candidate.operation;
    if (!['grant', 'revoke', 'recovery'].includes(op) || candidate.key_epoch !== previous.key_epoch + (['revoke', 'recovery'].includes(op) ? 1 : 0))
        throw new Error('EPOCH_TRANSITION_INVALID');
    if (previous.recovery_signing_public_key !== recovery || candidate.recovery_signing_public_key !== recovery || candidate.recovery_device_id !== previous.recovery_device_id || candidate.recovery_recipient_public_key !== previous.recovery_recipient_public_key)
        throw new Error('UNTRUSTED_RECOVERY_ROOT');
    await verifySigned('Membership', candidate, op === 'recovery' ? recovery : memberOf(previous, candidate.authority_device_id, ['owner']).signing_public_key);
    const old = new Map<string, PublicObject>(previous.members.map((m: PublicObject) => [m.device_id, m])), next = new Map<string, PublicObject>(candidate.members.map((m: PublicObject) => [m.device_id, m]));
    const changed: [
        PublicObject,
        PublicObject
    ][] = [], added = candidate.members.filter((m: PublicObject) => !old.has(m.device_id));
    for (const [id, m] of old) {
        const n = next.get(id);
        if (!n)
            throw new Error('MEMBERSHIP_HISTORY_REMOVED');
        for (const f of MF.filter(f => !['status', 'revoked_at'].includes(f)))
            if (m[f] !== n[f])
                throw new Error('MEMBERSHIP_IDENTITY_CHANGED');
        if (m.status === 'REVOKED' && digest(m) !== digest(n))
            throw new Error('REVOKED_DEVICE');
        if (digest(m) !== digest(n))
            changed.push([m, n]);
    }
    if (added.length && Math.min(...added.map((m: PublicObject) => m.nonce_prefix)) <= Math.max(...previous.members.map((m: PublicObject) => m.nonce_prefix)))
        throw new Error('PREFIX_HISTORY_REUSED');
    if (op === 'grant' && (added.length + changed.length !== 1 || added.some((m: PublicObject) => !['PENDING', 'ACTIVE'].includes(m.status)) || changed.some(([m, n]) => m.status !== 'PENDING' || n.status !== 'ACTIVE')))
        throw new Error('INVALID_GRANT_TRANSITION');
    if (op === 'revoke' && (added.length || !changed.length || changed.some(([m, n]) => !['PENDING', 'ACTIVE'].includes(m.status) || n.status !== 'REVOKED')))
        throw new Error('INVALID_REVOKE_TRANSITION');
    if (op === 'recovery' && (added.length !== 1 || added[0].status !== 'ACTIVE' || added[0].role !== 'owner' || candidate.authority_device_id !== added[0].device_id || [...old.keys()].some(id => next.get(id)!.status !== 'REVOKED')))
        throw new Error('INVALID_RECOVERY_TRANSITION');
    return candidate;
}
export function validateContext(c: PublicObject): void {
    fields(c, 'opaque_project_id recipient_device_id key_epoch membership_epoch session_id recipient_signing_public_key recipient_public_key'.split(' '));
    ['opaque_project_id', 'recipient_device_id', 'session_id'].forEach(f => uuid(c[f]));
    ['key_epoch', 'membership_epoch'].forEach(f => integer(c[f], 1));
    ['recipient_signing_public_key', 'recipient_public_key'].forEach(f => hex(c[f], 32));
}
export async function verifyGrant(g: PublicObject, m: PublicObject): Promise<PublicObject> {
    fields(g, 'version authority_device_id context role manifest_digest wrapped_key signature'.split(' '));
    integer(g.version, 1, 1);
    validateContext(g.context);
    const c = g.context, target = memberOf(m, c.recipient_device_id);
    if (g.manifest_digest !== digest(m) || c.opaque_project_id !== m.opaque_project_id || c.key_epoch !== m.key_epoch || c.membership_epoch !== m.membership_epoch || c.recipient_signing_public_key !== target.signing_public_key || c.recipient_public_key !== target.recipient_public_key || g.role !== target.role)
        throw new Error('GRANT_BINDING_MISMATCH');
    const authority = memberOf(m, g.authority_device_id, ['owner']);
    b64decode(g.wrapped_key, 80);
    await verifySigned('ProjectGrant', g, authority.signing_public_key);
    return g;
}
export function challengeSas(c: PublicObject): string {
    return digest(Object.fromEntries(Object.entries(c).filter(([k]) => !['signature', 'sas'].includes(k)))).slice(0, 12);
}
export async function verifyChallenge(c: PublicObject, m: PublicObject, now: number): Promise<void> {
    fields(c, 'version session_id opaque_project_id manifest_digest membership_epoch key_epoch authority_device_id recipient issued_at expires_at wrapped_challenge sas signature'.split(' '));
    integer(c.version, 1, 1);
    integer(c.membership_epoch, 1);
    integer(c.key_epoch, 1);
    uuid(c.session_id);
    validateMember(c.recipient);
    integer(c.issued_at);
    integer(c.expires_at);
    integer(now);
    if (c.expires_at !== c.issued_at + 300 || now < c.issued_at || now >= c.expires_at)
        throw new Error('PAIRING_EXPIRED');
    if (c.recipient.status !== 'ACTIVE' || c.sas !== challengeSas(c) || c.manifest_digest !== digest(m) || c.opaque_project_id !== m.opaque_project_id || c.key_epoch !== m.key_epoch || c.membership_epoch !== m.membership_epoch)
        throw new Error('PAIRING_SCOPE_MISMATCH');
    b64decode(c.wrapped_challenge, 80);
    await verifySigned('PairingChallenge', c, memberOf(m, c.authority_device_id, ['owner']).signing_public_key);
}
export async function verifyActiveEnvelope(env: Envelope, m: PublicObject, mutation = true): Promise<void> {
    validateEnvelope(env);
    if (env.opaque_project_id !== m.opaque_project_id || env.membership_epoch !== m.membership_epoch || env.key_epoch !== m.key_epoch)
        throw new Error('STALE_MEMBERSHIP_OR_KEY_EPOCH');
    const member = memberOf(m, env.sender_device_id, mutation ? ['owner', 'writer'] : undefined);
    await verifyEnvelope(env, hex(member.signing_public_key, 32));
    const nonce = Buffer.from(env.nonce, 'hex'), counter = nonce.readBigUInt64BE(4);
    if (nonce.readUInt32BE() !== member.nonce_prefix || counter < 1n || counter > 9007199254740991n)
        throw new Error('NONCE_BINDING_MISMATCH');
}
export async function verifyHistoricalEnvelope(env: Envelope, history: PublicObject, current: PublicObject): Promise<PublicObject> {
    validateEnvelope(env);
    if (history.opaque_project_id !== current.opaque_project_id || history.membership_epoch >= current.membership_epoch || history.key_epoch > current.key_epoch)
        throw new Error('UNPINNED_MEMBERSHIP_HISTORY');
    await verifyActiveEnvelope(env, history);
    return {
        status: 'QUARANTINED', reason: 'HISTORICAL_EPOCH', envelope_digest: digest(env)
    };
}
