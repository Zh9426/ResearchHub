import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateTransaction, validateChange, transactionDigest, revision, strictLoads, requireVersionPair, ProtocolError } from '../src/index.ts';
const cases = JSON.parse(readFileSync(new URL('../../../fixtures/sync/v2/protocol.json', import.meta.url), 'utf8'));
for (const c of cases) test(`v2 fixed: ${c.name}`, () => {
  if (!c.valid) assert.throws(() => validateTransaction(strictLoads(c.raw), c.context));
  else {
    const tx = validateTransaction(strictLoads(c.raw));
    validateTransaction(tx); validateChange(tx.changes[0]);
    assert.equal(transactionDigest(tx), c.digest);
    assert.deepEqual(tx.changes.map(revision), c.revisions);
  }
});

test('v1-only capability refuses v2 without downgrade', () => {
  assert.throws(() => requireVersionPair(2,2,[[1,1]]), (error: unknown) => error instanceof ProtocolError && error.code === 'UPGRADE_REQUIRED');
});
