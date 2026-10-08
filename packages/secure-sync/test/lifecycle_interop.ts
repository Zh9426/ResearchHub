/** Independent Node crypto only; subprocess fixture seeds are PUBLIC TEST ONLY. */
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { digest } from '../../sync-protocol/src/canonical.ts';
import { recipientPublic, signingPublic } from '../src/crypto.ts';
import { Device, RecoveryKit, TrustedStore, bootstrap, transition, openGrant, makeGrant, openRecoveryBackup, makeRecoveryBackup } from '../src/keys.ts';
import { verifyBootstrap, verifyTransition } from '../src/membership.ts';
import { NonceVault } from '../src/nonce.ts';
import { TestOnlyMemoryStagingSink, openArtifact, sealArtifact } from '../src/artifacts.ts';
import { openSnapshot, sealSnapshot, signCheckpoint } from '../src/checkpoint.ts';
const f = JSON.parse(readFileSync(0, 'utf8')), raw = (hex: string) => new Uint8Array(Buffer.from(hex, 'hex'));
async function device(id: string, s: string, r: string): Promise<Device> {
    return new Device(id, raw(s), raw(r), Buffer.from(await signingPublic(raw(s))).toString('hex'), Buffer.from(await recipientPublic(raw(r))).toString('hex'));
}
const owner = await device(f.initial.authority_device_id, f.owner_signing_seed_TEST_ONLY, f.owner_recipient_seed_TEST_ONLY), target = await device(f.manifest.members[1].device_id, f.target_signing_seed_TEST_ONLY, f.target_recipient_seed_TEST_ONLY);
const kit = RecoveryKit.fromPublicTestVectors(raw(f.kit_signing_seed_TEST_ONLY), raw(f.kit_recipient_seed_TEST_ONLY), Buffer.from(await signingPublic(raw(f.kit_signing_seed_TEST_ONLY))).toString('hex'), Buffer.from(await recipientPublic(raw(f.kit_recipient_seed_TEST_ONLY))).toString('hex'));
kit.deviceId = f.initial.recovery_device_id;
const key = raw(f.key_TEST_ONLY), store = new TrustedStore(join(f.temp_path, 'node-trusted.sqlite'));
await verifyBootstrap(f.initial, owner.signingPublic, kit.signingPublic);
await verifyTransition(f.initial, f.manifest, kit.signingPublic);
await store.bootstrap(f.initial, owner.signingPublic, kit.signingPublic);
await store.accept(f.manifest);
await kit.updateAnchor(f.manifest, f.checkpoint, store);
if (digest(Buffer.from(await openGrant(f.grant, f.manifest, target)).toString('hex')) !== digest(f.key_TEST_ONLY) || digest(Buffer.from(await openRecoveryBackup(f.backup, store, kit)).toString('hex')) !== digest(f.key_TEST_ONLY))
    throw new Error('INTEROP_KEY_MISMATCH');
const sink = new TestOnlyMemoryStagingSink(), metadata = await openArtifact(f.bundle, f.manifest, key, sink), state = await openSnapshot(f.snapshot, f.manifest, key, f.checkpoint, 'a'.repeat(64));
const initial = await bootstrap(f.initial.opaque_project_id, owner, kit), manifest = await transition(initial, owner, {
    add: target.member('writer', 1)
});
const vault = new NonceVault(join(f.temp_path, 'node-nonce.sqlite'));
vault.registerNew(key, 0);
const bundle = await sealArtifact([sink.data.subarray(0, 65536), sink.data.subarray(65536)], metadata, manifest, owner, key, vault, randomUUID()), checkpoint = await signCheckpoint(manifest, owner, 0, '0'.repeat(64)), snapshot = await sealSnapshot(state, 'a'.repeat(64), checkpoint, manifest, owner, key, vault, randomUUID());
const grant = await makeGrant(manifest, owner, target.deviceId, randomUUID(), key), backup = await makeRecoveryBackup(manifest, owner, kit, key);
process.stdout.write(JSON.stringify({
    input_verified: true, initial, manifest, grant, backup, bundle, checkpoint, snapshot
}));
