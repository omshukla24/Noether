import { test } from 'node:test';
import assert from 'node:assert/strict';
import { paginate } from '../src/paginate.js';

test('the first page is the default', () => {
  assert.deepEqual(paginate(25), { pages: 3, start: 0, end: 10, hasNext: true });
});

test('the last page is short', () => {
  assert.deepEqual(paginate(25, { page: 3 }), { pages: 3, start: 20, end: 25, hasNext: false });
});

test('an empty list has no pages', () => {
  assert.deepEqual(paginate(0), { pages: 0, start: 0, end: 0, hasNext: false });
});

test('bad arguments throw', () => {
  assert.throws(() => paginate(-1), /total/);
  assert.throws(() => paginate(5, { page: 0 }), /page/);
  assert.throws(() => paginate(5, { perPage: 0 }), /perPage/);
});
