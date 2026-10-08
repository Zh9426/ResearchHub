/** Trusted client TEST ONLY: in-memory secrets; SQLite contains public state only. */
import { randomBytes, randomUUID } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { existsSync, mkdirSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { canonicalBytes, digest, strictLoads } from '../../sync-protocol/src/canonical.ts';
import { recipientPublic, signingPublic, sign, wrapKey, unwrapKey, type WrapContext } from './crypto.ts';
import { b64encode, b64decode, validateEnvelope } from './envelope.ts';
import { ZERO, fingerprint, preimage, memberOf, verifyBootstrap, verifyTransition, verifyGrant, fields, validateContext, validateManifest, verifySigned, verifyActiveEnvelope, verifyHistoricalEnvelope, integer, type PublicObject } from './membership.ts';
export class Device {
    deviceId: string;
    signingPublic: string;
    recipientPublic: string;
    #signingSeed: Uint8Array;
    #recipientSeed: Uint8Array;
    constructor(id: string, signing: Uint8Array, recipient: Uint8Array, signingPub: string, recipientPub: string) {
        this.deviceId = id;
        this.#signingSeed = signing;
        this.#recipientSeed = recipient;
        this.signingPublic = signingPub;
        this.recipientPublic = recipientPub;
    }
    get signingSeed(): Uint8Array {
        return this.#signingSeed;
    }
    get recipientSeed(): Uint8Array {
        return this.#recipientSeed;
    }
    static async generate(): Promise<Device> {
        const s = randomBytes(32), r = randomBytes(32);
        return new Device(randomUUID(), s, r, Buffer.from(await signingPublic(s)).toString('hex'), Buffer.from(await recipientPublic(r)).toString('hex'));
    }
    member(role: string, prefix: number, status = 'ACTIVE', now = 0): PublicObject {
        return {
            device_id: this.deviceId, signing_public_key: this.signingPublic, recipient_public_key: this.recipientPublic, fingerprint: fingerprint(this.signingPublic, this.recipientPublic), role, status, nonce_prefix: prefix, granted_at: now, revoked_at: null
        };
    }
}
export interface DeviceKeyStore {
    loadOrCreate(): Promise<Device>;
}
export class TestOnlyMemoryDeviceKeyStore implements DeviceKeyStore {
    #device: Promise<Device>;
    constructor() {
        this.#device = Device.generate();
    }
    loadOrCreate(): Promise<Device> {
        return this.#device;
    }
}
/** UNPROTECTED TEST ONLY file secret store; ignored runtime/temporary paths only. */
export class TestOnlyFileDeviceKeyStore implements DeviceKeyStore {
    path: string;
    constructor(path: string) {
        let nearest = resolve(path);
        while (!existsSync(nearest))
            nearest = dirname(nearest);
        const physical = resolve(realpathSync(nearest), relative(nearest, resolve(path))), runtime = fileURLToPath(new URL('../../../storage/runtime/', import.meta.url));
        const within = (root: string) => {
            const rel = relative(realpathSync(root), physical);
            return !isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + (process.platform === 'win32' ? '\\' : '/'));
        };
        if (![runtime, tmpdir()].some(root => existsSync(root) && within(root)))
            throw new Error('QA_VAULT_PATH_REQUIRED');
        this.path = physical;
        mkdirSync(dirname(physical), {
            recursive: true
        });
    }
    async loadOrCreate(): Promise<Device> {
        const db = new DatabaseSync(this.path);
        try {
            db.exec('PRAGMA busy_timeout=30000; PRAGMA synchronous=FULL; BEGIN IMMEDIATE; CREATE TABLE IF NOT EXISTS qa_device(singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL,signing BLOB NOT NULL,recipient BLOB NOT NULL)');
            const row = db.prepare('SELECT id,signing,recipient FROM qa_device WHERE singleton=1').get() as {
                id: string;
                signing: Uint8Array;
                recipient: Uint8Array;
            } | undefined;
            if (row) {
                db.exec('COMMIT');
                return new Device(row.id, row.signing, row.recipient, Buffer.from(await signingPublic(row.signing)).toString('hex'), Buffer.from(await recipientPublic(row.recipient)).toString('hex'));
            }
            const device = await Device.generate();
            db.prepare('INSERT INTO qa_device VALUES (1,?,?,?)').run(device.deviceId, device.signingSeed, device.recipientSeed);
            db.exec('COMMIT');
            return device;
        }
        finally {
            db.close();
        }
    }
}
export interface KeyVault {
    create(project: string, epoch: number): Uint8Array;
    get(project: string, epoch: number): Uint8Array;
}
export class TestOnlyKeyVault implements KeyVault {
    #keys = new Map<string, Uint8Array>();
    create(project: string, epoch: number): Uint8Array {
        const id = project + ':' + epoch;
        if (this.#keys.has(id))
            throw new Error('KEY_EPOCH_ALREADY_EXISTS');
        const key = randomBytes(32);
        this.#keys.set(id, key);
        return key;
    }
    get(project: string, epoch: number): Uint8Array {
        const key = this.#keys.get(project + ':' + epoch);
        if (!key)
            throw new Error('UNKNOWN_KEY_EPOCH');
        return key;
    }
}
export class RecoveryKit {
    #signingSeed: Uint8Array;
    #recipientSeed: Uint8Array;
    signingPublic: string;
    recipientPublic: string;
    deviceId: string = randomUUID();
    manifestAnchor?: string;
    project?: string;
    checkpointAnchor?: PublicObject;
    #checkpointDigest?: string;
    #bootstrapAllowed = false;
    constructor(s: Uint8Array, r: Uint8Array, pub: string, recipientPub: string) {
        this.#signingSeed = s;
        this.#recipientSeed = r;
        this.signingPublic = pub;
        this.recipientPublic = recipientPub;
    }
    get signingSeed(): Uint8Array {
        return this.#signingSeed;
    }
    get recipientSeed(): Uint8Array {
        return this.#recipientSeed;
    }
    static async generate(): Promise<RecoveryKit> {
        const s = randomBytes(32), r = randomBytes(32);
        const kit = new RecoveryKit(s, r, Buffer.from(await signingPublic(s)).toString('hex'), Buffer.from(await recipientPublic(r)).toString('hex'));
        kit.#bootstrapAllowed = true;
        return kit;
    }
    static fromPublicTestVectors(s: Uint8Array, r: Uint8Array, pub: string, recipientPub: string): RecoveryKit {
        if (s.length !== 32 || r.length !== 32 || s.some((v, i) => v !== 128 + i) || r.some((v, i) => v !== 160 + i))
            throw new Error('PUBLIC_TEST_ONLY_VECTOR_REQUIRED');
        const kit = new RecoveryKit(s, r, pub, recipientPub);
        kit.#bootstrapAllowed = true;
        return kit;
    }
    static async restoreFromTrustedStore(s: Uint8Array, r: Uint8Array, deviceId: string, project: string, store: TrustedStore): Promise<RecoveryKit> {
        const kit = new RecoveryKit(s, r, Buffer.from(await signingPublic(s)).toString('hex'), Buffer.from(await recipientPublic(r)).toString('hex'));
        kit.deviceId = deviceId;
        const db = store.connect();
        try {
            const record = await store.kitAnchor(kit, project, db);
            if (!record) throw new Error('MISSING_TRUSTED_METADATA');
            kit.installAnchor(record);
            await kit.verifyAnchor(store, true, db);
            return kit;
        } catch {
            throw new Error('RECOVERY_FRESHNESS_UNVERIFIABLE');
        } finally { db.close(); }
    }
    /** Internal transaction handoff: install only after a successful COMMIT. */
    installAnchor(record: PublicObject): void {
        this.manifestAnchor = record.manifest_digest;
        this.project = record.project;
        this.checkpointAnchor = structuredClone(record.checkpoint);
        this.#checkpointDigest = record.checkpoint_digest;
        this.#bootstrapAllowed = false;
    }
    async updateAnchor(m: PublicObject, cp?: PublicObject, store?: TrustedStore, rows: PublicObject[] = [], checkpointStore?: {
        get(project: string): PublicObject | Promise<PublicObject>;
    }): Promise<void> {
        try {
            if (!store || !cp)
                throw new Error('MISSING_TRUSTED_ANCHOR');
            const db = store.connect();
            let record: PublicObject;
            try {
                record = await this.stageAnchor(m, cp, store, rows, checkpointStore, db);
                db.exec('COMMIT');
            } finally { db.close(); }
            this.installAnchor(record);
        } catch { throw new Error('RECOVERY_FRESHNESS_UNVERIFIABLE'); }
    }
    /** Stage PUBLIC metadata in the caller's transaction without changing memory. */
    async stageAnchor(m: PublicObject, cp: PublicObject, store: TrustedStore, rows: PublicObject[], checkpointStore: {get(project: string): PublicObject | Promise<PublicObject>} | undefined, db: DatabaseSync): Promise<PublicObject> {
        const { verifyAdvance, verifyCheckpoint } = await import('./checkpoint.ts');
        try {
            const current = await store.verifiedCurrent(m.opaque_project_id, db);
            if (digest(current) !== digest(m) || current.recovery_signing_public_key !== this.signingPublic || current.recovery_recipient_public_key !== this.recipientPublic || current.recovery_device_id !== this.deviceId)
                throw new Error('UNTRUSTED_RECOVERY_ROOT');
            await verifyCheckpoint(cp, current);
            const committed = await store.kitAnchor(this, current.opaque_project_id, db);
            if (this.#checkpointDigest === undefined && this.manifestAnchor === undefined) {
                if (!this.#bootstrapAllowed || committed)
                    throw new Error('IMPORTED_KIT_MISSING_TRUSTED_METADATA');
                if (!Array.isArray(rows) || rows.length)
                    throw new Error('INITIAL_ANCHOR_ROWS_MUST_BE_EMPTY');
                if (cp.cursor !== 0 && (!checkpointStore || digest(await checkpointStore.get(current.opaque_project_id)) !== digest(cp)))
                    throw new Error('UNTRUSTED_INITIAL_CHECKPOINT');
            }
            else {
                await this.verifyAnchor(store, false, db);
                if (this.project !== current.opaque_project_id)
                    throw new Error('ANCHOR_PROJECT_MISMATCH');
                await verifyAdvance(this.checkpointAnchor!, cp, current, rows);
            }
            const record = {
                version: 1, revision: committed ? committed.revision + 1 : 1,
                previous_digest: committed ? digest(committed) : ZERO,
                device_id: this.deviceId, signing_public_key: this.signingPublic,
                recipient_public_key: this.recipientPublic, project: current.opaque_project_id,
                manifest_digest: digest(current), membership_epoch: current.membership_epoch,
                key_epoch: current.key_epoch, checkpoint_digest: digest(cp), checkpoint: structuredClone(cp), rows: structuredClone(rows)
            };
            store.saveKitAnchor(record, db);
            return record;
        }
        catch {
            throw new Error('RECOVERY_FRESHNESS_UNVERIFIABLE');
        }
    }
    async verifyAnchor(store: TrustedStore, requireCurrent = true, db?: DatabaseSync): Promise<PublicObject> {
        const { verifyCheckpoint } = await import('./checkpoint.ts');
        try {
            if (!this.manifestAnchor || !this.project || !this.checkpointAnchor || !this.#checkpointDigest)
                throw new Error('MISSING_TRUSTED_ANCHOR');
            if (!db) {
                const connection = store.connect();
                try { return await this.verifyAnchor(store, requireCurrent, connection); }
                finally { connection.close(); }
            }
            const current = await store.verifiedCurrent(this.project, db), anchored = store.history(this.project, this.checkpointAnchor.membership_epoch, db), committed = await store.kitAnchor(this, this.project, db);
            if (!committed || committed.manifest_digest !== this.manifestAnchor || committed.checkpoint_digest !== this.#checkpointDigest || digest(anchored) !== this.manifestAnchor || digest(this.checkpointAnchor) !== this.#checkpointDigest || (requireCurrent && digest(current) !== this.manifestAnchor))
                throw new Error('ANCHOR_MISMATCH');
            if (anchored.recovery_signing_public_key !== this.signingPublic || anchored.recovery_recipient_public_key !== this.recipientPublic || anchored.recovery_device_id !== this.deviceId)
                throw new Error('UNTRUSTED_RECOVERY_ROOT');
            await verifyCheckpoint(this.checkpointAnchor, anchored);
            return current;
        }
        catch {
            throw new Error('RECOVERY_FRESHNESS_UNVERIFIABLE');
        }
    }
}
export async function signedObject(kind: string, value: PublicObject, seed: Uint8Array): Promise<PublicObject> {
    const result = structuredClone(value);
    delete result.signature;
    result.signature = b64encode(await sign(seed, preimage(kind, result)));
    return result;
}
export async function signedManifest(value: PublicObject, seed: Uint8Array): Promise<PublicObject> {
    return signedObject('Membership', value, seed);
}
export async function bootstrap(project: string, owner: Device, kit: RecoveryKit): Promise<PublicObject> {
    return verifyBootstrap(await signedManifest({
        version: 1, opaque_project_id: project, membership_epoch: 1, key_epoch: 1, previous_digest: ZERO, operation: 'bootstrap', authority_device_id: owner.deviceId, recovery_device_id: kit.deviceId, recovery_signing_public_key: kit.signingPublic, recovery_recipient_public_key: kit.recipientPublic, members: [owner.member('owner', 0)]
    }, owner.signingSeed), owner.signingPublic, kit.signingPublic);
}
export async function transition(previous: PublicObject, owner: Device, options: {
    add?: PublicObject;
    revoke?: string;
    activate?: string;
    now?: number;
}): Promise<PublicObject> {
    const { add, revoke, activate, now = 0 } = options;
    if ([add, revoke, activate].filter(v => v !== undefined).length !== 1)
        throw new Error('INVALID_TRANSITION_REQUEST');
    if (memberOf(previous, owner.deviceId, ['owner']).signing_public_key !== owner.signingPublic)
        throw new Error('DEVICE_KEY_MISMATCH');
    const value = structuredClone(previous);
    Object.assign(value, {
        previous_digest: digest(previous), membership_epoch: previous.membership_epoch + 1, authority_device_id: owner.deviceId, operation: revoke ? 'revoke' : 'grant'
    });
    if (add)
        value.members.push(structuredClone(add));
    else if (activate) {
        const target = value.members.find((m: PublicObject) => m.device_id === activate);
        if (!target || target.status !== 'PENDING')
            throw new Error('UNAUTHORIZED_DEVICE');
        target.status = 'ACTIVE';
    }
    else {
        const target = memberOf(previous, revoke!);
        value.key_epoch++;
        value.members.find((m: PublicObject) => m.device_id === target.device_id).status = 'REVOKED';
        value.members.find((m: PublicObject) => m.device_id === target.device_id).revoked_at = Math.max(now, target.granted_at);
    }
    return verifyTransition(previous, await signedManifest(value, owner.signingSeed), previous.recovery_signing_public_key);
}
export function grantContext(m: PublicObject, recipient: PublicObject, session: string): WrapContext {
    return {
        opaque_project_id: m.opaque_project_id, recipient_device_id: recipient.device_id, key_epoch: m.key_epoch, membership_epoch: m.membership_epoch, session_id: session, recipient_signing_public_key: recipient.signing_public_key, recipient_public_key: recipient.recipient_public_key
    };
}
export async function makeGrant(m: PublicObject, owner: Device, recipient: string, session: string, key: Uint8Array): Promise<PublicObject> {
    const target = memberOf(m, recipient);
    if (memberOf(m, owner.deviceId, ['owner']).signing_public_key !== owner.signingPublic)
        throw new Error('DEVICE_KEY_MISMATCH');
    const context = grantContext(m, target, session), wrapped = await wrapKey(new Uint8Array(Buffer.from(target.recipient_public_key, 'hex')), key, context);
    return verifyGrant(await signedObject('ProjectGrant', {
        version: 1, authority_device_id: owner.deviceId, context, role: target.role, manifest_digest: digest(m), wrapped_key: b64encode(wrapped)
    }, owner.signingSeed), m);
}
export async function openGrant(g: PublicObject, m: PublicObject, device: Device): Promise<Uint8Array> {
    await verifyGrant(g, m);
    const c = g.context;
    if (c.recipient_device_id !== device.deviceId || c.recipient_signing_public_key !== device.signingPublic || c.recipient_public_key !== device.recipientPublic)
        throw new Error('RECIPIENT_MISMATCH');
    return unwrapKey(device.recipientSeed, b64decode(g.wrapped_key, 80), c);
}
export class TrustedStore {
    path: string;
    constructor(path: string) {
        this.path = path;
        mkdirSync(dirname(path), {
            recursive: true
        });
        const db = this.connect();
        try {
            db.exec('CREATE TABLE IF NOT EXISTS kit_anchors(kit_id TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL,body BLOB NOT NULL,PRIMARY KEY(kit_id,project,revision))');
            db.exec('CREATE TABLE IF NOT EXISTS kit_anchor_heads(kit_id TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(kit_id,project))');
            db.exec('CREATE TABLE IF NOT EXISTS roots(project TEXT PRIMARY KEY, owner TEXT NOT NULL, recovery TEXT NOT NULL); CREATE TABLE IF NOT EXISTS manifests(project TEXT NOT NULL,digest TEXT PRIMARY KEY,epoch INTEGER NOT NULL,body BLOB NOT NULL,UNIQUE(project,epoch)); CREATE TABLE IF NOT EXISTS challenges(session TEXT PRIMARY KEY,body BLOB NOT NULL,response_digest TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,used INTEGER NOT NULL DEFAULT 0,receipt BLOB)');
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
    current(project: string, db?: DatabaseSync): PublicObject {
        if (!db) {
            const connection = this.connect();
            try {
                return this.current(project, connection);
            }
            finally {
                connection.close();
            }
        }
        return this.storedHistory(project, db).at(-1)!;
    }
    /** Synchronous structural read only; authority paths use verifiedCurrent. */
    private storedHistory(project: string, db: DatabaseSync): PublicObject[] {
        const rows = db.prepare('SELECT project,digest,epoch,body FROM manifests ORDER BY project,epoch').all() as {project: string; digest: string; epoch: number; body: Uint8Array}[];
        const histories = new Map<string, PublicObject[]>();
        for (const row of rows) {
            const m = strictLoads(row.body) as PublicObject;
            validateManifest(m);
            const history = histories.get(row.project) ?? [];
            if (row.project !== m.opaque_project_id || row.digest !== digest(m) || row.epoch !== m.membership_epoch || row.epoch !== history.length + 1 || m.previous_digest !== (history.length ? digest(history.at(-1)) : ZERO))
                throw new Error('MEMBERSHIP_STORAGE_INTEGRITY');
            history.push(m); histories.set(row.project, history);
        }
        const history = histories.get(project);
        if (!history?.length || !db.prepare('SELECT 1 FROM roots WHERE project=?').get(project)) throw new Error('UNTRUSTED_PROJECT');
        return history;
    }
    save(db: DatabaseSync, m: PublicObject): void {
        db.prepare('INSERT INTO manifests VALUES (?,?,?,?)').run(m.opaque_project_id, digest(m), m.membership_epoch, canonicalBytes(m));
    }
    async bootstrap(m: PublicObject, owner: string, recovery: string): Promise<void> {
        await verifyBootstrap(m, owner, recovery);
        const db = this.connect();
        try {
            if (db.prepare('SELECT 1 FROM roots WHERE project=?').get(m.opaque_project_id))
                throw new Error('BOOTSTRAP_ALREADY_PINNED');
            db.prepare('INSERT INTO roots VALUES (?,?,?)').run(m.opaque_project_id, owner, recovery);
            this.save(db, m);
            db.exec('COMMIT');
        }
        finally {
            db.close();
        }
    }
    async accept(candidate: PublicObject, db?: DatabaseSync): Promise<PublicObject> {
        if (!db) {
            const connection = this.connect();
            try {
                const result = await this.accept(candidate, connection);
                connection.exec('COMMIT');
                return result;
            }
            finally {
                connection.close();
            }
        }
        const previous = await this.verifiedCurrent(candidate.opaque_project_id, db), root = db.prepare('SELECT recovery FROM roots WHERE project=?').get(candidate.opaque_project_id) as {
            recovery: string;
        };
        await verifyTransition(previous, candidate, root.recovery);
        if (digest(previous) !== digest(candidate))
            this.save(db, candidate);
        return candidate;
    }
    history(project: string, epoch: number, db?: DatabaseSync): PublicObject {
        if (!db) {
            const connection = this.connect();
            try { return this.history(project, epoch, connection); }
            finally { connection.close(); }
        }
        integer(epoch, 1);
        const history = this.storedHistory(project, db);
        if (epoch > history.length) throw new Error('UNPINNED_MEMBERSHIP_HISTORY');
        return history[epoch - 1];
    }
    async verifiedCurrent(project: string, db?: DatabaseSync): Promise<PublicObject> {
        if (!db) {
            const connection = this.connect();
            try { return await this.verifiedCurrent(project, connection); }
            finally { connection.close(); }
        }
            const roots = db.prepare('SELECT owner,recovery FROM roots WHERE project=?').get(project) as {
                owner: string;
                recovery: string;
            } | undefined;
            const history = this.storedHistory(project, db);
            if (!roots)
                throw new Error('UNTRUSTED_PROJECT');
            let previous = history[0];
            await verifyBootstrap(previous, roots.owner, roots.recovery);
            if (previous.opaque_project_id !== project) throw new Error('UNTRUSTED_PROJECT');
            for (const manifest of history.slice(1))
                previous = await verifyTransition(previous, manifest, roots.recovery);
            return previous;
    }
    async kitAnchor(kit: RecoveryKit, project: string, db: DatabaseSync): Promise<PublicObject | undefined> {
        const { verifyAdvance, verifyCheckpoint } = await import('./checkpoint.ts');
        await this.verifiedCurrent(project, db);
        const rows = db.prepare('SELECT revision,body FROM kit_anchors WHERE kit_id=? AND project=? ORDER BY revision').all(kit.deviceId, project) as {revision: number; body: Uint8Array}[];
        const head = db.prepare('SELECT revision,digest FROM kit_anchor_heads WHERE kit_id=? AND project=?').get(kit.deviceId, project) as {revision: number; digest: string} | undefined;
        let previous: PublicObject | undefined;
        for (let index = 0; index < rows.length; index++) {
            const row = rows[index], record = strictLoads(row.body) as PublicObject;
            fields(record, 'version revision previous_digest device_id signing_public_key recipient_public_key project manifest_digest membership_epoch key_epoch checkpoint_digest checkpoint rows'.split(' '));
            integer(record.version, 1, 1); integer(record.revision, 1);
            integer(record.membership_epoch, 1); integer(record.key_epoch, 1);
            if (row.revision !== index + 1 || record.revision !== index + 1 || record.previous_digest !== (previous ? digest(previous) : ZERO) || record.device_id !== kit.deviceId || record.project !== project || record.signing_public_key !== kit.signingPublic || record.recipient_public_key !== kit.recipientPublic)
                throw new Error('KIT_METADATA_BINDING_MISMATCH');
            const m = this.history(project, record.membership_epoch, db);
            if (digest(m) !== record.manifest_digest || m.key_epoch !== record.key_epoch || m.recovery_device_id !== kit.deviceId || m.recovery_signing_public_key !== kit.signingPublic || m.recovery_recipient_public_key !== kit.recipientPublic || digest(record.checkpoint) !== record.checkpoint_digest)
                throw new Error('KIT_METADATA_BINDING_MISMATCH');
            await verifyCheckpoint(record.checkpoint, m);
            if (!Array.isArray(record.rows)) throw new Error('INVALID_CHECKPOINT_PAGE');
            if (!previous && record.rows.length) throw new Error('INITIAL_ANCHOR_ROWS_MUST_BE_EMPTY');
            if (previous) {
                if (record.membership_epoch < previous.membership_epoch || record.key_epoch < previous.key_epoch) throw new Error('ROLLBACK_DETECTED');
                await verifyAdvance(previous.checkpoint, record.checkpoint, m, record.rows);
            }
            previous = record;
        }
        if ((!head !== !previous) || (previous && (head!.revision !== previous.revision || head!.digest !== digest(previous))))
            throw new Error('KIT_METADATA_HEAD_MISMATCH');
        return previous;
    }
    saveKitAnchor(record: PublicObject, db: DatabaseSync): void {
        db.prepare('INSERT INTO kit_anchors VALUES (?,?,?,?)').run(record.device_id, record.project, record.revision, canonicalBytes(record));
        db.prepare('INSERT INTO kit_anchor_heads VALUES (?,?,?,?) ON CONFLICT(kit_id,project) DO UPDATE SET revision=excluded.revision,digest=excluded.digest').run(record.device_id, record.project, record.revision, digest(record));
    }
}
export async function recover(store: TrustedStore, kit: RecoveryKit | undefined, owner: Device, chain: PublicObject[] = [], now = 0): Promise<PublicObject> {
    if (!kit)
        throw new Error('E2E_DATA_UNRECOVERABLE');
    await kit.verifyAnchor(store);
    if (!Array.isArray(chain) || chain.some(candidate => !candidate || candidate.opaque_project_id !== kit.project))
        throw new Error('RECOVERY_CHAIN_PROJECT_MISMATCH');
    const db = store.connect();
    let result: PublicObject;
    let anchor: PublicObject;
    try {
        await kit.verifyAnchor(store, true, db);
        if (digest(store.current(kit.project!, db)) !== kit.manifestAnchor)
            throw new Error('RECOVERY_FRESHNESS_UNVERIFIABLE');
        for (const m of chain)
            await store.accept(m, db);
        const previous = store.current(kit.project!, db), prefix = Math.max(...previous.members.map((m: PublicObject) => m.nonce_prefix)) + 1;
        if (prefix > 4294967295)
            throw new Error('PREFIX_EXHAUSTED');
        const value = structuredClone(previous);
        for (const m of value.members)
            if (m.status !== 'REVOKED')
                Object.assign(m, {
                    status: 'REVOKED', revoked_at: Math.max(now, m.granted_at)
                });
        value.members.push(owner.member('owner', prefix, 'ACTIVE', now));
        Object.assign(value, {
            operation: 'recovery', authority_device_id: owner.deviceId, previous_digest: digest(previous), membership_epoch: previous.membership_epoch + 1, key_epoch: previous.key_epoch + 1
        });
        result = await signedManifest(value, kit.signingSeed);
        await store.accept(result, db);
        const { signCheckpoint } = await import('./checkpoint.ts');
        const cp = await signCheckpoint(result, owner, kit.checkpointAnchor!.cursor, kit.checkpointAnchor!.chain_digest);
        anchor = await kit.stageAnchor(result, cp, store, [], undefined, db);
        db.exec('COMMIT');
    }
    finally {
        db.close();
    }
    kit.installAnchor(anchor!);
    return result!;
}
export async function makeRecoveryBackup(m: PublicObject, owner: Device, kit: RecoveryKit, key: Uint8Array): Promise<PublicObject> {
    if (memberOf(m, owner.deviceId, ['owner']).signing_public_key !== owner.signingPublic || m.recovery_device_id !== kit.deviceId || m.recovery_signing_public_key !== kit.signingPublic || m.recovery_recipient_public_key !== kit.recipientPublic)
        throw new Error('UNTRUSTED_RECOVERY_ROOT');
    const context = grantContext(m, {
        device_id: kit.deviceId, signing_public_key: kit.signingPublic, recipient_public_key: kit.recipientPublic
    }, randomUUID());
    return signedObject('RecoveryBackup', {
        version: 1, authority_device_id: owner.deviceId, manifest_digest: digest(m), context, wrapped_key: b64encode(await wrapKey(new Uint8Array(Buffer.from(kit.recipientPublic, 'hex')), key, context))
    }, owner.signingSeed);
}
export async function openRecoveryBackup(backup: PublicObject, store: TrustedStore, kit: RecoveryKit | undefined): Promise<Uint8Array> {
    if (!kit)
        throw new Error('E2E_DATA_UNRECOVERABLE');
    const m = await kit.verifyAnchor(store);
    fields(backup, 'version authority_device_id manifest_digest context wrapped_key signature'.split(' '));
    integer(backup.version, 1, 1);
    validateContext(backup.context);
    const c = backup.context;
    if (backup.manifest_digest !== digest(m) || c.opaque_project_id !== kit.project || c.key_epoch !== m.key_epoch || c.membership_epoch !== m.membership_epoch || c.recipient_device_id !== kit.deviceId || m.recovery_device_id !== kit.deviceId || c.recipient_signing_public_key !== kit.signingPublic || m.recovery_signing_public_key !== kit.signingPublic || c.recipient_public_key !== kit.recipientPublic || m.recovery_recipient_public_key !== kit.recipientPublic)
        throw new Error('RECOVERY_BACKUP_BINDING_MISMATCH');
    await verifySigned('RecoveryBackup', backup, memberOf(m, backup.authority_device_id, ['owner']).signing_public_key);
    return unwrapKey(kit.recipientSeed, b64decode(backup.wrapped_key, 80), c);
}
export class Rotation {
    manifest: PublicObject;
    grants: Record<string, PublicObject>;
    #key: Uint8Array;
    constructor(manifest: PublicObject, grants: Record<string, PublicObject>, key: Uint8Array) {
        this.manifest = manifest;
        this.grants = grants;
        this.#key = key;
    }
    get key(): Uint8Array {
        return this.#key;
    }
}
export async function revokeAndRotate(store: TrustedStore, vault: KeyVault, owner: Device, target: string, now = 0): Promise<Rotation> {
    const db = store.connect();
    try {
        const projects = db.prepare('SELECT project FROM roots').all() as {
            project: string;
        }[];
        if (projects.length !== 1)
            throw new Error('PROJECT_SELECTION_REQUIRED');
        const previous = await store.verifiedCurrent(projects[0].project, db), manifest = await transition(previous, owner, {
            revoke: target, now
        }), key = vault.create(manifest.opaque_project_id, manifest.key_epoch), grants: Record<string, PublicObject> = {};
        for (const member of manifest.members)
            if (member.status === 'ACTIVE')
                grants[member.device_id] = await makeGrant(manifest, owner, member.device_id, randomUUID(), key);
        await store.accept(manifest, db);
        db.exec('COMMIT');
        return new Rotation(manifest, grants, key);
    }
    finally {
        db.close();
    }
}
export async function classifyEnvelope(store: TrustedStore, env: PublicObject): Promise<PublicObject> {
    validateEnvelope(env);
    const db = store.connect();
    try {
        const current = await store.verifiedCurrent(env.opaque_project_id, db);
        if (env.membership_epoch < current.membership_epoch)
            return await verifyHistoricalEnvelope(env, store.history(env.opaque_project_id, env.membership_epoch, db), current);
        await verifyActiveEnvelope(env, current);
        return {status: 'AUTHORIZED', envelope_digest: digest(env)};
    } finally { db.close(); }
}
