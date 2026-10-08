/** TEST ONLY five-minute dual possession pairing, atomic persistent receipt. */
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { canonicalBytes, digest, strictLoads } from '../../sync-protocol/src/canonical.ts';
import { b64decode, b64encode } from './envelope.ts';
import { sign, unwrapKey, wrapKey } from './crypto.ts';
import { challengeSas, fields, memberOf, preimage, verifyChallenge, verifySigned, type PublicObject } from './membership.ts';
import { Device, TrustedStore, grantContext, makeGrant, signedObject, transition } from './keys.ts';
export function confirmation(c: PublicObject): PublicObject {
    return {
        fingerprint: c.recipient.fingerprint, opaque_project_id: c.opaque_project_id, role: c.recipient.role, sas: c.sas
    };
}
export async function createChallenge(store: TrustedStore, owner: Device, recipient: PublicObject, options: {
    now: number;
    project?: string;
}): Promise<PublicObject> {
    let project = options.project;
    if (!project) {
        const db = store.connect();
        try {
            const projects = db.prepare('SELECT project FROM roots').all() as {
                project: string;
            }[];
            if (projects.length !== 1)
                throw new Error('PROJECT_SELECTION_REQUIRED');
            project = projects[0].project;
        }
        finally {
            db.close();
        }
    }
    const manifest = await store.verifiedCurrent(project);
    if (memberOf(manifest, owner.deviceId, ['owner']).signing_public_key !== owner.signingPublic)
        throw new Error('DEVICE_KEY_MISMATCH');
    const session = randomUUID(), response = randomBytes(32), context = grantContext(manifest, recipient, session);
    let challenge: PublicObject = {
        version: 1, session_id: session, opaque_project_id: project, manifest_digest: digest(manifest), membership_epoch: manifest.membership_epoch, key_epoch: manifest.key_epoch, authority_device_id: owner.deviceId, recipient, issued_at: options.now, expires_at: options.now + 300, wrapped_challenge: b64encode(await wrapKey(new Uint8Array(Buffer.from(recipient.recipient_public_key, 'hex')), response, context))
    };
    challenge.sas = challengeSas(challenge);
    challenge = await signedObject('PairingChallenge', challenge, owner.signingSeed);
    await verifyChallenge(challenge, manifest, options.now);
    const db = store.connect();
    try {
        if (digest(await store.verifiedCurrent(project, db)) !== digest(manifest))
            throw new Error('MEMBERSHIP_CAS_MISMATCH');
        db.prepare('INSERT INTO challenges(session,body,response_digest) VALUES (?,?,?)').run(session, canonicalBytes(challenge), createHash('sha256').update(response).digest('hex'));
        db.exec('COMMIT');
    }
    finally {
        db.close();
    }
    return challenge;
}
export async function answerChallenge(c: PublicObject, pinned: PublicObject, device: Device, options: {
    confirmation: PublicObject;
    now: number;
}): Promise<PublicObject> {
    await verifyChallenge(c, pinned, options.now);
    if (digest(options.confirmation) !== digest(confirmation(c)))
        throw new Error('PAIRING_CONFIRMATION_MISMATCH');
    const r = c.recipient;
    if (r.device_id !== device.deviceId || r.signing_public_key !== device.signingPublic || r.recipient_public_key !== device.recipientPublic)
        throw new Error('RECIPIENT_MISMATCH');
    const response = await unwrapKey(device.recipientSeed, b64decode(c.wrapped_challenge, 80), grantContext(pinned, r, c.session_id));
    const proof: PublicObject = {
        challenge_digest: digest(c), challenge_response: Buffer.from(response).toString('hex'), confirmation: options.confirmation
    };
    proof.signature = b64encode(await sign(device.signingSeed, preimage('PairingProof', proof)));
    return proof;
}
export async function consume(store: TrustedStore, owner: Device, c: PublicObject, proof: PublicObject, key: Uint8Array, options: {
    now: number;
    crashPoint?: string;
}): Promise<PublicObject> {
    const db = store.connect();
    let failure: unknown, result: PublicObject | undefined;
    try {
        const row = db.prepare('SELECT body,response_digest,attempts,used FROM challenges WHERE session=?').get(c.session_id) as {
            body: Uint8Array;
            response_digest: string;
            attempts: number;
            used: number;
        } | undefined;
        if (!row || !Buffer.from(row.body).equals(Buffer.from(canonicalBytes(c))))
            throw new Error('PAIRING_SCOPE_MISMATCH');
        if (row.used)
            throw new Error('PAIRING_USED');
        if (row.attempts >= 5)
            throw new Error('PAIRING_ATTEMPTS_EXCEEDED');
        const manifest = await store.verifiedCurrent(c.opaque_project_id, db);
        db.prepare('UPDATE challenges SET attempts=attempts+1 WHERE session=?').run(c.session_id);
        try {
            await verifyChallenge(c, manifest, options.now);
            fields(proof, 'challenge_digest challenge_response confirmation signature'.split(' '));
            if (proof.challenge_digest !== digest(c) || digest(proof.confirmation) !== digest(confirmation(c)) || typeof proof.challenge_response !== 'string' || !/^[0-9a-f]{64}$/.test(proof.challenge_response) || createHash('sha256').update(Buffer.from(proof.challenge_response, 'hex')).digest('hex') !== row.response_digest)
                throw new Error('PAIRING_PROOF_INVALID');
            await verifySigned('PairingProof', proof, c.recipient.signing_public_key);
            const next = await transition(manifest, owner, {
                add: c.recipient, now: options.now
            }), grant = await makeGrant(next, owner, c.recipient.device_id, c.session_id, key);
            result = {
                challenge_digest: digest(c), manifest: next, grant
            };
        }
        catch (e) {
            failure = e;
        }
        if (!failure) {
            await store.accept(result!.manifest, db);
            db.prepare('UPDATE challenges SET used=1,receipt=? WHERE session=?').run(canonicalBytes(result!), c.session_id);
        }
        if (options.crashPoint === 'before_commit')
            throw new Error('SYNTHETIC_CRASH_BEFORE_COMMIT');
        db.exec('COMMIT');
    }
    finally {
        db.close();
    }
    if (failure)
        throw failure;
    if (options.crashPoint === 'after_commit')
        throw new Error('SYNTHETIC_CRASH_AFTER_COMMIT');
    return result!;
}
export async function retryReceipt(store: TrustedStore, c: PublicObject, recipient: string): Promise<PublicObject> {
    const db = store.connect();
    try {
        const row = db.prepare('SELECT body,used,receipt FROM challenges WHERE session=?').get(c.session_id) as {
            body: Uint8Array;
            used: number;
            receipt: Uint8Array;
        } | undefined;
        if (!row || !row.used || recipient !== c.recipient.device_id || !Buffer.from(row.body).equals(Buffer.from(canonicalBytes(c))))
            throw new Error('PAIRING_RETRY_SCOPE_MISMATCH');
        const current = await store.verifiedCurrent(c.opaque_project_id, db), member = memberOf(current, recipient);
        if (digest(member) !== digest(c.recipient))
            throw new Error('PAIRING_RETRY_SCOPE_MISMATCH');
        const receipt = strictLoads(row.receipt) as PublicObject;
        if (current.key_epoch !== receipt.manifest.key_epoch)
            throw new Error('PAIRING_RETRY_STALE_EPOCH');
        return receipt;
    }
    finally {
        db.close();
    }
}
