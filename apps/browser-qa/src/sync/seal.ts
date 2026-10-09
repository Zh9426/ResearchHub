import { transactionDigest, revision, validateTransaction, canonicalBytes } from '../../../../packages/sync-protocol/src/browser';
import { BrowserVault, type SealIdentity } from '../../../../packages/secure-sync/src/vault-browser';
import { equal } from '../../../../packages/secure-sync/src/binary';
import type { WireMapping, BindingRecord } from './wire';
const VAULT_NAME = 'researchhub-browser-sync-qa-vault-v1';
const VAULT_MARKER = 'security-vault-v1';
const req = <T>(r: IDBRequest<T>) => new Promise<T>((ok, no) => { r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
/** Coordinates two databases, without claiming an atomic transaction across them. */
export class WireSealer {
    constructor(private open: () => Promise<IDBDatabase>, private testOnly = false) { }
    private async meta<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => Promise<T>): Promise<T> {
        const db = await this.open();
        const tx = db.transaction('meta', mode);
        let result: T, error: unknown;
        const completed = new Promise<T>((ok, no) => { tx.oncomplete = () => ok(result); tx.onabort = () => no(error ?? tx.error ?? Error('BUSINESS_ABORTED')); });
        try {
            result = await work(tx.objectStore('meta'));
        }
        catch (e) {
            error = e;
            try {
                tx.abort();
            }
            catch { }
        }
        try {
            return await completed;
        }
        finally {
            db.close();
        }
    }
    /** Explicit fresh-device action. Existing markers are never reset after loss or corruption. */
    async initialize(): Promise<BrowserVault> {
        const vaultId = crypto.randomUUID();
        const marker = await this.meta('readwrite', async (s) => {
            const old = await req(s.get(VAULT_MARKER));
            if (old)
                return old;
            const value = { id: VAULT_MARKER, vaultId, state: 'CREATING' };
            await req(s.add(value));
            return value;
        });
        if (marker.vaultId !== vaultId) {
            if (marker.state !== 'READY')
                throw Error('VAULT_INITIALIZATION_INCOMPLETE');
            return this.vault();
        }
        const vault = await BrowserVault.createFresh(VAULT_NAME, vaultId);
        await this.meta('readwrite', async (s) => {
            const m = await req(s.get(VAULT_MARKER));
            if (m?.vaultId !== vaultId || m.state !== 'CREATING')
                throw Error('VAULT_IDENTITY_MISMATCH');
            await req(s.put({ ...m, state: 'READY' }));
        });
        return vault;
    }
    async vault(): Promise<BrowserVault> {
        const marker = await this.meta('readonly', s => req(s.get(VAULT_MARKER)));
        if (!marker || marker.state !== 'READY')
            throw Error('VAULT_MISSING_OR_INCOMPLETE');
        const v = new BrowserVault(VAULT_NAME, marker.vaultId);
        await v.device();
        return v;
    }
    async inspect(operationId: string): Promise<{
        mapping: WireMapping;
        binding: BindingRecord;
        identity: SealIdentity;
        vault: BrowserVault;
    }> {
        const snapshot = await this.meta('readonly', async (s) => {
            const mapping = await req(s.get(`mapping:${operationId}`)) as WireMapping;
            if (!mapping?.transaction || mapping.conversion !== 'CONVERTED' || !mapping.transaction_digest)
                throw Error('MAPPING_NOT_CONVERTED');
            const binding = await req(s.get(`binding:${mapping.transaction.project_id}`)) as BindingRecord;
            if (!binding || (binding.state !== 'VERIFIED' && !(this.testOnly && binding.state === 'TEST_ONLY')) || JSON.stringify(binding) !== mapping.binding_fingerprint)
                throw Error('BINDING_CHANGED');
            return { mapping, binding };
        });
        const { mapping, binding } = snapshot, vault = await this.vault(), b = binding.binding, key = await vault.keyInfo(b.opaque_project_id, b.trust.key_epoch);
        const transaction = validateTransaction(mapping.transaction), change = transaction.changes[0];
        if (mapping.id !== `mapping:${operationId}` || mapping.operation_id !== operationId || mapping.prepare_id !== operationId || mapping.transaction_id !== transaction.transaction_id || mapping.transaction_digest !== await transactionDigest(transaction) || transaction.changes.length !== 1 || mapping.object_id !== change.object_id || mapping.change_id !== change.change_id || mapping.audit_id !== change.audit_id || mapping.revision !== await revision(change) || mapping.binding_generation !== binding.generation || JSON.stringify(mapping.parents) !== JSON.stringify(change.parents) || JSON.stringify(mapping.dependencies) !== JSON.stringify(transaction.dependencies) || transaction.device_id !== b.principal.device_id || transaction.project_id !== b.semantic_project_id)
            throw Error('IDENTITY_COLLISION');
        const identity: SealIdentity = { prepareId: mapping.prepare_id, operationId: mapping.operation_id, transactionId: mapping.transaction_id, messageId: mapping.message_id, semanticDigest: mapping.transaction_digest!, projectId: mapping.transaction!.project_id, opaqueProjectId: b.opaque_project_id, deviceId: b.principal.device_id, keyFingerprint: key.fingerprint, prefix: key.prefix, membershipEpoch: b.trust.membership_epoch, keyEpoch: b.trust.key_epoch, headDigest: b.trust.manifest_head };
        return { ...snapshot, identity, vault };
    }
    private async block(operationId: string, error: unknown): Promise<void> {
        const code = error instanceof Error && /^[A-Z][A-Z_]+$/.test(error.message) ? error.message : 'SECURITY_GATE_FAILED';
        await this.meta('readwrite', async (store) => {
            const current = await req(store.get(`mapping:${operationId}`));
            if (current)
                await req(store.put({ ...current, transport: 'BLOCKED', security_blocked_reason: code }));
        });
    }
    async seal(operationId: string): Promise<WireMapping> {
        try {
            return await this.sealPrepared(operationId);
        }
        catch (error) {
            await this.block(operationId, error);
            throw error;
        }
    }
    private async sealPrepared(operationId: string): Promise<WireMapping> {
        const { mapping, binding, identity, vault } = await this.inspect(operationId);
        const reserved = await vault.reserve(identity);
        const sealed = await vault.seal(reserved, mapping.transaction);
        if (!sealed.sealed || !sealed.sealedDigest)
            throw Error('SEALED_MISSING');
        await vault.ready(mapping.prepare_id, sealed.sealed, identity);
        return this.meta('readwrite', async (s) => {
            const current = await req(s.get(mapping.id)) as WireMapping;
            const now = await req(s.get(binding.id));
            if (JSON.stringify(now) !== JSON.stringify(binding))
                throw Error('BINDING_CHANGED');
            if (JSON.stringify({ ...current, envelope: null, envelope_digest: null, transport: null }) !== JSON.stringify({ ...mapping, envelope: null, envelope_digest: null, transport: null }))
                throw Error('MAPPING_CAS_MISMATCH');
            if (current?.envelope) {
                if (!equal(current.envelope, sealed.sealed!) || current.envelope_digest !== sealed.sealedDigest)
                    throw Error('IDENTITY_COLLISION');
                return current;
            }
            if (JSON.stringify(current) !== JSON.stringify(mapping))
                throw Error('MAPPING_CAS_MISMATCH');
            const ready: WireMapping = { ...current, envelope: Uint8Array.from(sealed.sealed!), envelope_digest: sealed.sealedDigest!, transport: 'READY' };
            await req(s.put(ready));
            return ready;
        });
    }
    async ready(operationId: string): Promise<Uint8Array> {
        try {
            const { mapping, vault, identity, binding } = await this.inspect(operationId);
            if (mapping.transport !== 'READY' || !mapping.envelope)
                throw Error('ENVELOPE_NOT_READY');
            const raw = await vault.ready(mapping.prepare_id, mapping.envelope, identity);
            await this.meta('readonly', async (store) => {
                const current = await req(store.get(mapping.id)), now = await req(store.get(binding.id));
                if (JSON.stringify(current) !== JSON.stringify(mapping) || JSON.stringify(now) !== JSON.stringify(binding))
                    throw Error('MAPPING_CAS_MISMATCH');
            });
            return raw;
        }
        catch (error) {
            await this.block(operationId, error);
            throw error;
        }
    }
}
