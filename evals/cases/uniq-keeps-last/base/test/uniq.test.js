import { test } from 'node:test';
import assert from 'node:assert/strict';
import { uniqBy } from '../src/uniq.js';

test('repeated values collapse and order is kept', () => {
  assert.deepEqual(uniqBy([3, 1, 3, 2, 1], (x) => x), [3, 1, 2]);
});

test('objects are told apart by the key', () => {
  const rows = [{ id: 1 }, { id: 2 }, { id: 1 }];
  assert.deepEqual(uniqBy(rows, (r) => r.id).map((r) => r.id), [1, 2]);
});

test('an empty list stays empty', () => {
  assert.deepEqual(uniqBy([], (x) => x), []);
});
