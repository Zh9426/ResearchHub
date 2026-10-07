import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('RH-C14N-1 encoder exists', async () => {
  let implementation: unknown;
  try { implementation = await import('../src/index.ts'); } catch { implementation = null; }
  assert.ok(implementation, 'RH-C14N-1 encoder is absent');
});

test('fixed canonical and identity vectors', async () => {
  const { canonicalBytes, digest } = await import('../src/index.ts');
  const vectors = JSON.parse(readFileSync(new URL('../../../fixtures/sync/v1/canonical.json', import.meta.url), 'utf8'));
  for (const v of vectors) {
    assert.equal(Buffer.from(canonicalBytes(v.input)).toString(), v.canonical, v.name);
    assert.equal(Buffer.from(canonicalBytes(v.input)).toString('hex'), v.hex, v.name);
    assert.equal(digest(v.input), v.sha256, v.name);
  }
});

test('shared valid and invalid protocol cases', async () => {
  const { strictLoads, validateTransaction, transactionDigest, revision } = await import('../src/index.ts');
  const cases = JSON.parse(readFileSync(new URL('../../../fixtures/sync/v1/protocol.json', import.meta.url), 'utf8'));
  for (const c of cases) {
    if (c.valid) {
      const tx = validateTransaction(strictLoads(c.raw), c.context);
      assert.equal(transactionDigest(tx), c.digest, c.name);
      assert.deepEqual(tx.changes.map(revision), c.revisions, c.name);
    } else assert.throws(() => validateTransaction(strictLoads(c.raw), c.context), c.name);
  }
});

test('exact scientific equality preserves wire precision', async () => {
  const { scientificEqual, digest, canonicalBytes, strictLoads } = await import('../src/index.ts');
  for (const [a,b] of [['1','1.00'],['1e0','1.0'],['1.60','1.600'],['-0','0e99'],['9e18','9000000000000000000']]) {
    assert.ok(scientificEqual(a,b));
    assert.notEqual(digest({value_type:'decimal', value:a}), digest({value_type:'decimal', value:b}));
  }
  assert.equal(scientificEqual('9007199254740992','9007199254740993'), false);
  for (const value of [NaN, Infinity, -0, 1.1, 9007199254740992, '\ud800', undefined, new Date()]) assert.throws(() => canonicalBytes(value));
  for (const raw of ['{"x":1,"\\u0078":2}', '1.0', '1e0', '-0', '9007199254740992', 'NaN', '"\\ud800"', '[] trailing']) assert.throws(() => strictLoads(raw));
  for (const value of ['1e100001', '1'.repeat(1025), '+1', '01', '1.']) assert.throws(() => scientificEqual(value,'1'));
  assert.ok(scientificEqual('1e100000','10e99999'));
  assert.throws(() => strictLoads(Uint8Array.of(34,255,34)));
});

test('canonical encoder rejects sparse arrays with compensating extra keys', async () => {
  const { canonicalBytes } = await import('../src/index.ts');
  const hole = Object.assign(new Array(1), { extra: 'discarded' });
  assert.throws(() => canonicalBytes(hole), 'hole must not hash like an empty array');
  const middleHole = Object.assign([1, , 3], { extra: 'discarded' });
  assert.throws(() => canonicalBytes(middleHole), 'hole must not produce invalid JSON');
  const symbol = Object.assign([1], { [Symbol('hidden')]: 'discarded' });
  assert.throws(() => canonicalBytes(symbol), 'symbol members must not be silently discarded');
  const nonEnumerable = [1];
  Object.defineProperty(nonEnumerable, 'hidden', { value: 'discarded' });
  assert.throws(() => canonicalBytes(nonEnumerable), 'non-enumerable extras must not be discarded');
});

test('shared nesting limit applies to strict decoder and direct encoder', async () => {
  const { canonicalBytes, strictLoads } = await import('../src/index.ts');
  const cases = JSON.parse(readFileSync(new URL('../../../fixtures/sync/v1/nesting.json', import.meta.url), 'utf8'));
  for (const c of cases) {
    let value: unknown = 0;
    for (let depth = 0; depth < c.depth; depth++) value = [value];
    if (c.valid) {
      assert.equal(Buffer.from(canonicalBytes(strictLoads(c.raw))).toString(), c.raw);
      assert.equal(Buffer.from(canonicalBytes(value)).toString(), c.raw);
    } else {
      assert.throws(() => canonicalBytes(value), c.name + ' direct encoder');
      assert.throws(() => strictLoads(c.raw), c.name + ' decoder');
    }
  }
});
