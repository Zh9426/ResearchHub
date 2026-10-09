/** Independent security IDB. Crypto is always outside short read/write transactions.
 * Whole-profile rollback of all trusted state cannot be detected here. Production remains blocked. */
import { canonicalBytes, digest, validateTransaction } from '../../sync-protocol/src/browser.ts';
import { generateDevice, importProjectKey, unwrapKey, sign, sha256, type DeviceKeys } from './crypto-web.ts';
import { verifyBootstrap, verifyTransition, verifyGrant, memberOf, verifyActiveEnvelope, type PublicObject } from './membership-core.ts';
import { sealWithNonce, decodeEnvelope, verifyEnvelope, openTransaction as openTransactionCore, type Envelope } from './envelope-core.ts';
import { bytes, b64decode, hexEncode, hexDecode, equal, nonceParts } from './binary.ts';
export type Trust = {
    id: string;
    ownerRoot: string;
    recoveryRoot: string;
    chain: PublicObject[];
    headDigest: string;
    membershipEpoch: number;
    keyEpoch: number;
};
export type SealIdentity = {
    prepareId: string;
    operationId: string;
    transactionId: string;
    messageId: string;
    semanticDigest: string;
    projectId: string;
    opaqueProjectId: string;
    deviceId: string;
    keyFingerprint: string;
    prefix: number;
    membershipEpoch: number;
    keyEpoch: number;
    headDigest: string;
};
export type Preparation = {
    id: string;
    identity: SealIdentity;
    token: string;
    nonce: string;
    sealed: Uint8Array | null;
    sealedDigest: string | null;
};
type KeyRow = {
    id: string;
    key: CryptoKey;
    fingerprint: string;
    prefix: number;
    ledgerId: string;
};
type Ledger = {
    id: string;
    fingerprint: string;
    prefix: number;
    counter: number;
};
const stores = ['meta', 'devices', 'keys', 'ledgers', 'mirrors', 'preparations', 'trust'];
const identityText = (v: unknown) => new TextDecoder().decode(canonicalBytes(v));
const request = <T>(r: IDBRequest<T>) => new Promise<T>((ok, no) => { r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
async function openExisting(name: string): Promise<IDBDatabase> {
    return new Promise((ok, no) => {
        const r = indexedDB.open(name);
        r.onupgradeneeded = () => { r.transaction!.abort(); no(Error('VAULT_MISSING')); };
        r.onsuccess = () => {
            const db = r.result;
            if (stores.some(s => !db.objectStoreNames.contains(s)) || !db.transaction('meta').objectStore('meta').indexNames.contains('reservationNonce')) {
                db.close();
                no(Error('VAULT_CORRUPT'));
            }
            else
                ok(db);
        };
        r.onerror = () => no(Error('VAULT_MISSING_OR_CORRUPT'));
    });
}
async function short<T>(db: IDBDatabase, names: string[], mode: IDBTransactionMode, work: (tx: IDBTransaction) => Promise<T>): Promise<T> {
    const tx = db.transaction(names, mode);
    let value: T;
    let failure: unknown;
    const completed = new Promise<T>((ok, no) => { tx.oncomplete = () => ok(value); tx.onabort = () => no(failure ?? tx.error ?? Error('VAULT_ABORTED')); tx.onerror = () => { }; });
    try {
        value = await work(tx);
    }
    catch (e) {
        failure = e;
        try {
            tx.abort();
        }
        catch { }
    }
    return completed;
}
const get = <T>(tx: IDBTransaction, store: string, id: string) => request(tx.objectStore(store).get(id)) as Promise<T | undefined>;
const put = (tx: IDBTransaction, store: string, value: unknown) => request(tx.objectStore(store).put(value));
function deviceShape(d: DeviceKeys | undefined): asserts d is DeviceKeys {
    if (!d || d.signing.privateKey.extractable || d.recipient.privateKey.extractable || d.signing.privateKey.algorithm.name !== 'Ed25519' || d.recipient.privateKey.algorithm.name !== 'X25519' || d.signing.privateKey.usages.join() !== 'sign' || d.recipient.privateKey.usages.join() !== 'deriveBits')
        throw Error('DEVICE_KEY_CORRUPT');
}
function keyShape(k: KeyRow | undefined): asserts k is KeyRow {
    if (!k || !k.key || k.key.extractable || k.key.algorithm.name !== 'AES-GCM' || (k.key.algorithm as AesKeyAlgorithm).length !== 256 || k.key.usages.slice().sort().join() !== 'decrypt,encrypt' || !/^[0-9a-f]{64}$/.test(k.fingerprint))
        throw Error('PROJECT_KEY_MISSING_OR_CORRUPT');
}
function ledgerShape(k: KeyRow, l: Ledger | undefined, m: Ledger | undefined) {
    if (!l || !m || identityText(l) !== identityText(m) || l.id !== k.ledgerId || l.fingerprint !== k.fingerprint || l.prefix !== k.prefix || !Number.isSafeInteger(l.counter) || l.counter < 0 || l.counter > Number.MAX_SAFE_INTEGER)
        throw Error('NONCE_LEDGER_MISSING_OR_CORRUPT');
}
async function preparationMarker(tx: IDBTransaction, p: Preparation): Promise<void> {
    if ((p.sealed === null) !== (p.sealedDigest === null) || (p.sealed !== null && (!(p.sealed instanceof Uint8Array) || typeof p.sealedDigest !== 'string' || !/^[0-9a-f]{64}$/.test(p.sealedDigest))))
        throw Error('PREPARATION_MISSING_OR_CORRUPT');
    const marker = await get(tx, 'meta', `prepare:${p.id}`);
    if (identityText(marker ?? null) !== identityText({ id: `prepare:${p.id}`, identity: p.identity, token: p.token, nonce: p.nonce, nonceLedgerId: `${p.identity.keyFingerprint}:${p.identity.prefix}`, sealed: p.sealed !== null, sealedDigest: p.sealedDigest }))
        throw Error('PREPARATION_MISSING_OR_CORRUPT');
}
/** One reverse compound-index cursor plus one preparation read: O(log n), no full scan.
 * A counter below a retained nonce is corruption, never repaired or incremented here. */
async function nonceHighWater(tx: IDBTransaction, k: KeyRow, ledger: Ledger): Promise<void> {
    const cursor = await request(tx.objectStore('meta').index('reservationNonce').openCursor(IDBKeyRange.bound([k.ledgerId, ''], [k.ledgerId, 'f'.repeat(24)]), 'prev'));
    if (!cursor) {
        if (ledger.counter !== 0)
            throw Error('NONCE_COUNTER_ROLLBACK');
        return;
    }
    const marker = cursor.value;
    if (typeof marker.id !== 'string' || !marker.id.startsWith('prepare:') || typeof marker.nonce !== 'string' || !/^[0-9a-f]{24}$/.test(marker.nonce))
        throw Error('PREPARATION_MISSING_OR_CORRUPT');
    const p = await get<Preparation>(tx, 'preparations', marker.id.slice(8));
    if (!p)
        throw Error('PREPARATION_MISSING_OR_CORRUPT');
    await preparationMarker(tx, p);
    const { prefix, counter } = nonceParts(hexDecode(marker.nonce));
    if (prefix !== k.prefix || counter < 1n || counter > BigInt(Number.MAX_SAFE_INTEGER))
        throw Error('PREPARATION_MISSING_OR_CORRUPT');
    if (BigInt(ledger.counter) < counter)
        throw Error('NONCE_COUNTER_ROLLBACK');
}
async function keyAuthorization(tx: IDBTransaction, k: KeyRow): Promise<void> {
    const authorization = await get(tx, 'meta', `authorization:${k.id}`), tombstone = await get(tx, 'meta', `key:${k.ledgerId}`);
    if (identityText(authorization ?? null) !== identityText({ id: `authorization:${k.id}`, fingerprint: k.fingerprint, prefix: k.prefix }) || identityText(tombstone ?? null) !== identityText({ id: `key:${k.ledgerId}`, fingerprint: k.fingerprint, prefix: k.prefix }))
        throw Error('NONCE_AUTHORIZATION_MISSING_OR_CORRUPT');
}
async function verifiedTrust(t: Trust | undefined): Promise<Trust> {
    if (!t || !Array.isArray(t.chain) || !t.chain.length)
        throw Error('TRUST_NOT_VERIFIED');
    let m = await verifyBootstrap(t.chain[0], t.ownerRoot, t.recoveryRoot);
    for (const next of t.chain.slice(1))
        m = await verifyTransition(m, next, t.recoveryRoot);
    if (m.opaque_project_id !== t.id || m.membership_epoch !== t.membershipEpoch || m.key_epoch !== t.keyEpoch || await digest(m) !== t.headDigest)
        throw Error('TRUST_HEAD_MISMATCH');
    return t;
}
function authorize(t: Trust, i: SealIdentity, d: DeviceKeys) {
    const m = t.chain.at(-1)!;
    const member = memberOf(m, i.deviceId, ['owner', 'writer']);
    if (t.id !== i.opaqueProjectId || t.headDigest !== i.headDigest || t.membershipEpoch !== i.membershipEpoch || t.keyEpoch !== i.keyEpoch)
        throw Error('STALE_MEMBERSHIP_OR_KEY_EPOCH');
    if (d.deviceId !== i.deviceId || d.signingPublic !== member.signing_public_key || d.recipientPublic !== member.recipient_public_key || member.nonce_prefix !== i.prefix)
        throw Error('DEVICE_KEY_MISMATCH');
}
export class BrowserVault {
    readonly name: string;
    readonly vaultId: string;
    constructor(name: string, vaultId: string) { this.name = name; this.vaultId = vaultId; }
    /** Caller must first durably reserve this fresh vaultId in the separate business DB.
     * A missing existing vault is never repaired by this API. */
    static async createFresh(name: string, vaultId: string): Promise<BrowserVault> {
        if ((await indexedDB.databases()).some(d => d.name === name))
            throw Error('VAULT_ALREADY_EXISTS');
        const d = await generateDevice();
        const db = await new Promise<IDBDatabase>((ok, no) => {
            const r = indexedDB.open(name, 1);
            let created = false;
            r.onupgradeneeded = () => {
                created = true;
                for (const s of stores)
                    r.result.createObjectStore(s, { keyPath: 'id' });
                r.transaction!.objectStore('meta').createIndex('reservationNonce', ['nonceLedgerId', 'nonce'], { unique: true });
            };
            r.onsuccess = () => {
                if (!created) {
                    r.result.close();
                    no(Error('VAULT_ALREADY_EXISTS'));
                }
                else
                    ok(r.result);
            };
            r.onerror = () => no(r.error);
        });
        try {
            await short(db, ['meta', 'devices'], 'readwrite', async (tx) => { await put(tx, 'meta', { id: 'identity', vaultId, version: 1 }); await put(tx, 'devices', { ...d, id: 'device' }); });
        }
        finally {
            db.close();
        }
        return new BrowserVault(name, vaultId);
    }
    private async db() {
        const db = await openExisting(this.name);
        try {
            await short(db, ['meta'], 'readonly', async (tx) => {
                const m = await get<any>(tx, 'meta', 'identity');
                if (m?.vaultId !== this.vaultId || m.version !== 1)
                    throw Error('VAULT_IDENTITY_MISMATCH');
            });
            return db;
        }
        catch (e) {
            db.close();
            throw e;
        }
    }
    private async tx<T>(names: string[], mode: IDBTransactionMode, work: (tx: IDBTransaction) => Promise<T>): Promise<T> {
        const db = await this.db();
        try {
            return await short(db, names, mode, work);
        }
        finally {
            db.close();
        }
    }
    async device(): Promise<DeviceKeys> { const d = await this.tx(['devices'], 'readonly', tx => get<DeviceKeys>(tx, 'devices', 'device')); deviceShape(d); return d; }
    async trust(project: string): Promise<Trust> { return verifiedTrust(await this.tx(['trust'], 'readonly', tx => get<Trust>(tx, 'trust', project))); }
    /** Pin roots come from an independently confirmed owner channel, never a Relay response alone. */
    async pin(ownerRoot: string, recoveryRoot: string, chain: PublicObject[]): Promise<Trust> {
        if (!chain.length)
            throw Error('TRUST_NOT_VERIFIED');
        const m = chain.at(-1)!;
        const candidate = await verifiedTrust({ id: m.opaque_project_id, ownerRoot, recoveryRoot, chain: structuredClone(chain), headDigest: await digest(m), membershipEpoch: m.membership_epoch, keyEpoch: m.key_epoch });
        const prior = await this.tx(['trust'], 'readonly', tx => get<Trust>(tx, 'trust', candidate.id));
        if (prior) {
            await verifiedTrust(prior);
            if (prior.ownerRoot !== ownerRoot || prior.recoveryRoot !== recoveryRoot)
                throw Error('PIN_ROOT_MISMATCH');
            if (candidate.membershipEpoch < prior.membershipEpoch || candidate.chain.length < prior.chain.length)
                throw Error('ROLLBACK_DETECTED');
            for (let n = 0; n < prior.chain.length; n++)
                if (await digest(prior.chain[n]) !== await digest(candidate.chain[n]))
                    throw Error('MEMBERSHIP_FORK');
        }
        return this.tx(['trust'], 'readwrite', async (tx) => {
            const current = await get<Trust>(tx, 'trust', candidate.id);
            if (identityText(current ?? null) !== identityText(prior ?? null))
                throw Error('MEMBERSHIP_CAS_MISMATCH');
            await put(tx, 'trust', candidate);
            return candidate;
        });
    }
    async acceptGrant(grant: PublicObject): Promise<string> {
        const t = await this.trust(grant.context.opaque_project_id), d = await this.device(), m = t.chain.at(-1)!;
        await verifyGrant(grant, m);
        if (grant.context.recipient_device_id !== d.deviceId || grant.context.recipient_signing_public_key !== d.signingPublic || grant.context.recipient_public_key !== d.recipientPublic)
            throw Error('RECIPIENT_MISMATCH');
        // Raw key exists only transiently in this scope; JS makes no reliable zeroization guarantee.
        const raw = await unwrapKey(d.recipient, b64decode(grant.wrapped_key, 80), grant.context), material = await importProjectKey(raw);
        const prefix = memberOf(m, d.deviceId).nonce_prefix;
        const row: KeyRow = { id: `${t.id}:${t.keyEpoch}`, key: material.key, fingerprint: material.fingerprint, prefix, ledgerId: `${material.fingerprint}:${prefix}` };
        return this.tx(['keys', 'ledgers', 'mirrors', 'trust', 'meta', 'preparations'], 'readwrite', async (tx) => {
            if (identityText(await get(tx, 'trust', t.id)) !== identityText(t))
                throw Error('MEMBERSHIP_CAS_MISMATCH');
            const authorization = await get<any>(tx, 'meta', `authorization:${row.id}`);
            const tombstone = await get<any>(tx, 'meta', `key:${row.ledgerId}`), old = await get<KeyRow>(tx, 'keys', row.id), l = await get<Ledger>(tx, 'ledgers', row.ledgerId), mirror = await get<Ledger>(tx, 'mirrors', row.ledgerId);
            if (authorization && (authorization.fingerprint !== row.fingerprint || authorization.prefix !== row.prefix))
                throw Error('PROJECT_KEY_IDENTITY_COLLISION');
            if (authorization && !old)
                throw Error('PROJECT_KEY_MISSING_OR_CORRUPT');
            if (old && !authorization)
                throw Error('PROJECT_KEY_MISSING_OR_CORRUPT');
            if (tombstone && identityText(tombstone) !== identityText({ id: `key:${row.ledgerId}`, fingerprint: row.fingerprint, prefix: row.prefix }))
                throw Error('NONCE_AUTHORIZATION_MISSING_OR_CORRUPT');
            if (old)
                await keyAuthorization(tx, old);
            if (tombstone || old || l || mirror) {
                if (!tombstone || !l || !mirror)
                    throw Error('NONCE_LEDGER_MISSING_OR_CORRUPT');
                ledgerShape(row, l, mirror);
                await nonceHighWater(tx, row, l!);
                if (old) {
                    keyShape(old);
                    if (old.fingerprint !== row.fingerprint || old.prefix !== row.prefix)
                        throw Error('PROJECT_KEY_IDENTITY_COLLISION');
                }
            }
            else {
                const ledger = { id: row.ledgerId, fingerprint: row.fingerprint, prefix, counter: 0 };
                await put(tx, 'ledgers', ledger);
                await put(tx, 'mirrors', ledger);
                await put(tx, 'meta', { id: `key:${row.ledgerId}`, fingerprint: row.fingerprint, prefix });
            }
            // Re-import can attach the same key to a new epoch but never reset its nonce ledger.
            await put(tx, 'keys', row);
            await put(tx, 'meta', { id: `authorization:${row.id}`, fingerprint: row.fingerprint, prefix });
            return row.fingerprint;
        });
    }
    private async projectKey(project: string, epoch: number): Promise<KeyRow> { return this.tx(['keys', 'ledgers', 'mirrors', 'meta', 'preparations'], 'readonly', async (tx) => { const k = await get<KeyRow>(tx, 'keys', `${project}:${epoch}`); keyShape(k); await keyAuthorization(tx, k); ledgerShape(k, await get(tx, 'ledgers', k.ledgerId), await get(tx, 'mirrors', k.ledgerId)); await nonceHighWater(tx, k, (await get<Ledger>(tx, 'ledgers', k.ledgerId))!); return k; }); }
    async keyInfo(project: string, epoch: number): Promise<{
        fingerprint: string;
        prefix: number;
    }> { const k = await this.projectKey(project, epoch); return { fingerprint: k.fingerprint, prefix: k.prefix }; }
    async reserve(identity: SealIdentity): Promise<Preparation> {
        const i = structuredClone(identity), t = await this.trust(i.opaqueProjectId), d = await this.device();
        authorize(t, i, d);
        if (i.prepareId !== i.operationId || !i.prepareId || !/^[0-9a-f]{64}$/.test(i.semanticDigest) || !/^[0-9a-f]{64}$/.test(i.keyFingerprint))
            throw Error('INVALID_PREPARATION');
        const token = crypto.randomUUID();
        return this.tx(['trust', 'keys', 'ledgers', 'mirrors', 'preparations', 'meta'], 'readwrite', async (tx) => {
            if (identityText(await get(tx, 'trust', t.id)) !== identityText(t))
                throw Error('MEMBERSHIP_CAS_MISMATCH');
            const key = await get<KeyRow>(tx, 'keys', `${i.opaqueProjectId}:${i.keyEpoch}`);
            keyShape(key);
            await keyAuthorization(tx, key);
            if (key.fingerprint !== i.keyFingerprint || key.prefix !== i.prefix)
                throw Error('PROJECT_KEY_IDENTITY_COLLISION');
            const ledger = await get<Ledger>(tx, 'ledgers', key.ledgerId), mirror = await get<Ledger>(tx, 'mirrors', key.ledgerId);
            ledgerShape(key, ledger, mirror);
            await nonceHighWater(tx, key, ledger!);
            const old = await get<Preparation>(tx, 'preparations', i.prepareId);
            const marker = await get(tx, 'meta', `prepare:${i.prepareId}`);
            if (!old && marker)
                throw Error('PREPARATION_MISSING_OR_CORRUPT');
            if (old) {
                await preparationMarker(tx, old);
                if (identityText(old.identity) !== identityText(i))
                    throw Error('IDENTITY_COLLISION');
                if (old.sealed)
                    return old;
            }
            if (ledger!.counter === Number.MAX_SAFE_INTEGER)
                throw Error('NONCE_EXHAUSTED');
            const counter = ledger!.counter + 1, next = { ...ledger!, counter };
            const nonce = new Uint8Array(12), v = new DataView(nonce.buffer);
            v.setUint32(0, i.prefix);
            v.setBigUint64(4, BigInt(counter));
            const p: Preparation = { id: i.prepareId, identity: i, token, nonce: hexEncode(nonce), sealed: null, sealedDigest: null };
            await put(tx, 'ledgers', next);
            await put(tx, 'mirrors', next);
            await put(tx, 'meta', { id: `prepare:${p.id}`, identity: p.identity, token: p.token, nonce: p.nonce, nonceLedgerId: `${p.identity.keyFingerprint}:${p.identity.prefix}`, sealed: p.sealed !== null, sealedDigest: p.sealedDigest });
            await put(tx, 'preparations', p);
            return p;
        });
    }
    async preparation(id: string): Promise<Preparation> {
        const p = await this.tx(['preparations', 'meta'], 'readonly', async (tx) => {
            const p = await get<Preparation>(tx, 'preparations', id);
            if (p)
                await preparationMarker(tx, p);
            return p;
        });
        if (!p)
            throw Error('PREPARATION_MISSING');
        if (p.sealed && await sha256(p.sealed) !== p.sealedDigest)
            throw Error('SEALED_CORRUPT');
        return p;
    }
    async seal(preparation: Preparation, transaction: unknown): Promise<Preparation> {
        const p = structuredClone(preparation), i = p.identity, txValue = validateTransaction(transaction);
        if (txValue.transaction_id !== i.transactionId || txValue.project_id !== i.projectId || txValue.device_id !== i.deviceId || await digest(txValue) !== i.semanticDigest)
            throw Error('TRANSACTION_BINDING_MISMATCH');
        const current = await this.preparation(p.id);
        if (identityText(current.identity) !== identityText(i))
            throw Error('IDENTITY_COLLISION');
        if (current.sealed) {
            await this.ready(current.id, current.sealed);
            return current;
        }
        if (current.token !== p.token || current.nonce !== p.nonce)
            throw Error('STALE_PREPARATION_TOKEN');
        const t = await this.trust(i.opaqueProjectId), d = await this.device();
        authorize(t, i, d);
        const key = await this.projectKey(i.opaqueProjectId, i.keyEpoch);
        keyShape(key);
        if (key.fingerprint !== i.keyFingerprint || key.prefix !== i.prefix)
            throw Error('PROJECT_KEY_IDENTITY_COLLISION');
        const env = await sealWithNonce(txValue, key.key, v => sign(d.signing.privateKey, v), hexDecode(p.nonce), { opaque_project_id: i.opaqueProjectId, sender_device_id: i.deviceId, membership_epoch: i.membershipEpoch, key_epoch: i.keyEpoch, message_id: i.messageId, record_type: 'transaction', protocol_version: txValue.protocol_version, schema_version: txValue.schema_version, dependencies: txValue.dependencies });
        const raw = canonicalBytes(env), sealedDigest = await sha256(raw);
        return this.tx(['preparations', 'trust', 'keys', 'ledgers', 'mirrors', 'meta'], 'readwrite', async (tx) => {
            const now = await get<Preparation>(tx, 'preparations', p.id);
            if (!now || identityText(now.identity) !== identityText(i))
                throw Error('IDENTITY_COLLISION');
            await preparationMarker(tx, now);
            if (identityText(await get(tx, 'trust', t.id)) !== identityText(t))
                throw Error('MEMBERSHIP_CAS_MISMATCH');
            const k = await get<KeyRow>(tx, 'keys', key.id);
            keyShape(k);
            await keyAuthorization(tx, k);
            if (k.fingerprint !== key.fingerprint)
                throw Error('PROJECT_KEY_IDENTITY_COLLISION');
            ledgerShape(k, await get(tx, 'ledgers', k.ledgerId), await get(tx, 'mirrors', k.ledgerId));
            await nonceHighWater(tx, k, (await get<Ledger>(tx, 'ledgers', k.ledgerId))!);
            if (now.sealed) {
                if (!equal(now.sealed, raw) || now.sealedDigest !== sealedDigest)
                    throw Error('IDENTITY_COLLISION');
                return now;
            }
            if (now.token !== p.token || now.nonce !== p.nonce)
                throw Error('STALE_PREPARATION_TOKEN');
            const committed = { ...now, sealed: raw, sealedDigest };
            await put(tx, 'meta', { id: `prepare:${now.id}`, identity: now.identity, token: now.token, nonce: now.nonce, nonceLedgerId: `${now.identity.keyFingerprint}:${now.identity.prefix}`, sealed: true, sealedDigest });
            await put(tx, 'preparations', committed);
            return committed;
        });
    }
    async openTransaction(env: Envelope, projectId: string): Promise<unknown> { const t = await this.trust(env.opaque_project_id); await verifyActiveEnvelope(env, t.chain.at(-1)!); const member = memberOf(t.chain.at(-1)!, env.sender_device_id); const key = await this.projectKey(t.id, t.keyEpoch); keyShape(key); return openTransactionCore(env, key.key, hexDecode(member.signing_public_key), { opaque_project_id: t.id, sender_device_id: member.device_id, membership_epoch: t.membershipEpoch, key_epoch: t.keyEpoch, nonce_prefix: member.nonce_prefix, project_id: projectId }); }
    /** Read-only send gate: callers send exactly these already durable bytes. */
    async ready(id: string, ready: Uint8Array, expectedIdentity?: SealIdentity): Promise<Uint8Array> {
        const p = await this.preparation(id);
        if (!p.sealed || !equal(p.sealed, ready))
            throw Error('IDENTITY_COLLISION');
        if (expectedIdentity && identityText(expectedIdentity) !== identityText(p.identity))
            throw Error('IDENTITY_COLLISION');
        const t = await this.trust(p.identity.opaqueProjectId), d = await this.device();
        authorize(t, p.identity, d);
        await this.keyInfo(t.id, t.keyEpoch);
        const env = await decodeEnvelope(p.sealed);
        await verifyEnvelope(env, hexDecode(d.signingPublic));
        const i = p.identity;
        if (env.message_id !== i.messageId || env.opaque_project_id !== i.opaqueProjectId || env.sender_device_id !== i.deviceId || env.membership_epoch !== i.membershipEpoch || env.key_epoch !== i.keyEpoch || env.semantic_transaction_digest !== i.semanticDigest || env.nonce !== p.nonce || env.record_type !== 'transaction')
            throw Error('ENVELOPE_BINDING_MISMATCH');
        return this.tx(['trust', 'keys', 'ledgers', 'mirrors', 'meta', 'preparations'], 'readonly', async (tx) => {
            if (identityText(await get(tx, 'trust', t.id)) !== identityText(t))
                throw Error('MEMBERSHIP_CAS_MISMATCH');
            const k = await get<KeyRow>(tx, 'keys', `${t.id}:${t.keyEpoch}`);
            keyShape(k);
            await keyAuthorization(tx, k);
            ledgerShape(k, await get(tx, 'ledgers', k.ledgerId), await get(tx, 'mirrors', k.ledgerId));
            await nonceHighWater(tx, k, (await get<Ledger>(tx, 'ledgers', k.ledgerId))!);
            const current = await get<Preparation>(tx, 'preparations', id);
            if (current)
                await preparationMarker(tx, current);
            if (!current?.sealed || identityText({ ...current, sealed: null }) !== identityText({ ...p, sealed: null }) || !equal(current.sealed, p.sealed!))
                throw Error('IDENTITY_COLLISION');
            return Uint8Array.from(current.sealed);
        });
    }
}
