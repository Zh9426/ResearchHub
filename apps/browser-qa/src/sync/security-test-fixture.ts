/** TEST ONLY bridge. Tree-shaken out of normal builds; never grants UI trust. */
import * as security from '../../../../packages/secure-sync/src/browser';
import { digest, canonicalBytes } from '../../../../packages/sync-protocol/src/browser';
import { WireSealer } from './seal';
import { openLocalDatabase } from '../local/db';
import { StableWireAdapter, type BindingRecord } from './wire';
import { LocalCommandService } from '../local/commands';
const open = () => openLocalDatabase('researchhub-browser-sync-qa-business-v1');
const sealer = new WireSealer(open, true), commands = new LocalCommandService(open, 'researchhub-browser-sync-qa-changes-v1', true), adapter = new StableWireAdapter(open, true);
async function publicDevice() { const vault = await sealer.initialize(), d = await vault.device(); return { deviceId: d.deviceId, signingPublic: d.signingPublic, recipientPublic: d.recipientPublic, nonextractable: !d.signing.privateKey.extractable && !d.recipient.privateKey.extractable }; }
async function install(material: any) { const vault = await sealer.vault(); await vault.pin(material.ownerRoot, material.recoveryRoot, material.chain); await vault.acceptGrant(material.grant); const d = await vault.device(), s = await commands.snapshot(), p = s.projects.find(p => p.id === material.semanticProject)!; const m = material.chain.at(-1); const principal = { device_id: d.deviceId, actor_id: material.actorId, actor_type: 'human' as const, role: 'writer' as const }; const record: BindingRecord = { id: `binding:${p.id}`, state: 'TEST_ONLY', generation: 1, binding: { binding_version: 1, semantic_project_id: p.id, opaque_project_id: m.opaque_project_id, module_snapshot: p.module_snapshot, module_snapshot_hash: await digest(p.module_snapshot), local_module_hash: { algorithm: 'sha256-json-stringify', value: p.module_hash }, capabilities: { protocol_version: 2, schema_version: 2, object_types: ['ResearchRun', 'Note'] }, principal_map: [principal], principal, trust: { membership_epoch: m.membership_epoch, key_epoch: m.key_epoch, manifest_head: await digest(m), owner_root: material.ownerRoot, recovery_root: material.recoveryRoot, manifest_chain: material.chain } } }; const db = await open(); await new Promise<void>((ok, no) => { const tx = db.transaction('meta', 'readwrite'); tx.objectStore('meta').put(record); tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); }); db.close(); return { key: await vault.keyInfo(m.opaque_project_id, m.key_epoch) }; }
async function fixed(f: any) {
    const db = await new Promise<IDBDatabase>((ok, no) => { const r = indexedDB.open('researchhub-browser-sync-qa-TEST_ONLY-imported-keys', 1); r.onupgradeneeded = () => r.result.createObjectStore('keys'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
    const previous = await new Promise<any>((ok, no) => { const tx = db.transaction('keys'); const r = tx.objectStore('keys').get('TEST_ONLY'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
    let keys = previous;
    if (!keys) {
        const pair = async (seed: string, pub: string, oid: string, name: string, usage: KeyUsage) => ({ privateKey: await crypto.subtle.importKey('pkcs8', security.bytes(security.hexDecode('302e020100300506032b' + oid + '04220420' + seed)), name, false, [usage]), publicKey: await crypto.subtle.importKey('raw', security.bytes(security.hexDecode(pub)), name, true, name === 'Ed25519' ? ['verify'] : []) });
        keys = { signing: await pair(f.signing_seed_TEST_ONLY, f.signing_public_key, '6570', 'Ed25519', 'sign'), recipient: await pair(f.recipient_seed_TEST_ONLY, f.wrap_context.recipient_public_key, '656e', 'X25519', 'deriveBits'), aes: (await security.importProjectKey(security.hexDecode(f.key_TEST_ONLY))).key };
        await new Promise<void>((ok, no) => { const tx = db.transaction('keys', 'readwrite'); tx.objectStore('keys').add(keys, 'TEST_ONLY'); tx.oncomplete = () => ok(); tx.onabort = () => no(tx.error); });
    }
    db.close();
    const unwrapped = await security.unwrapKey(keys.recipient, security.hexDecode(f.wrapped_key_hex), f.wrap_context);
    const env = await security.decodeEnvelope(security.hexDecode(f.envelope_canonical_hex));
    const value = await security.openTransaction(env, keys.aes, security.hexDecode(f.signing_public_key), f.bindings);
    const signature = await security.sign(keys.signing.privateKey, canonicalBytes(value));
    await security.verify(security.hexDecode(f.signing_public_key), signature, canonicalBytes(value));
    return { canonical: security.hexEncode(canonicalBytes(value)), digest: await digest(value), reused: !!previous, unwrapMatches: security.hexEncode(unwrapped) === f.key_TEST_ONLY, privateNonextractable: !keys.signing.privateKey.extractable && !keys.recipient.privateKey.extractable && !keys.aes.extractable };
}
(window as any).__B1_TEST_ONLY__ = { security, digest, canonicalBytes, sealer, commands, adapter, publicDevice, install, fixed };
