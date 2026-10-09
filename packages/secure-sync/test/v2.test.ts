import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { openTransaction, sealTransaction, validateHeader, headerOf } from '../src/envelope.ts';
import { canonicalBytes } from '../../sync-protocol/src/canonical.ts';
import { NonceVault } from '../src/nonce.ts';
const v = JSON.parse(readFileSync(new URL('../../../fixtures/sync/v2/envelope.TEST_ONLY.json', import.meta.url), 'utf8'));
const env = v.cases[0].envelope, key = Buffer.from(v.key_TEST_ONLY,'hex'), seed = Buffer.from(v.signing_seed_TEST_ONLY,'hex'), pub = Buffer.from(v.signing_public_key,'hex');
const binding = { opaque_project_id: env.opaque_project_id, sender_device_id: env.sender_device_id, membership_epoch: env.membership_epoch, key_epoch: env.key_epoch };
test('v2 fixed envelope opens and signed inner/outer mismatch fails', async () => {
  const options = {...binding, project_id: v.transaction.project_id, nonce_prefix:19};
  assert.deepEqual(canonicalBytes(await openTransaction(env,key,pub,options)),canonicalBytes(v.transaction));
  await assert.rejects(openTransaction(v.cases[1].envelope,key,pub,options), /TRANSACTION_BINDING_MISMATCH/);
});
test('v2 seal derives header versions and matches independent oracle', async () => {
  const dir=mkdtempSync(join(tmpdir(),'rh-v2-'));
  try {
    const vault=new NonceVault(join(dir,'nonce.sqlite')); vault.registerNew(key,19);
    assert.deepEqual(await sealTransaction(v.transaction,key,seed,vault,19,{...binding,message_id:env.message_id}),env);
  } finally { rmSync(dir,{recursive:true,force:true}); }
});
test('only transaction supports v2 and mixed pairs fail', () => {
  for (const kind of ['snapshot','artifact_manifest']) assert.throws(() => validateHeader({...headerOf(env),record_type:kind}));
  for (const [p,s] of [[1,2],[2,1],[3,3],[true,true]]) assert.throws(() => validateHeader({...headerOf(env),protocol_version:p,schema_version:s}));
});
