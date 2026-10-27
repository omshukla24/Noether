import { test } from 'node:test';
import assert from 'node:assert/strict';
import { retryDelay } from '../src/backoff.js';

test('the delay doubles from the base', () => {
  assert.equal(retryDelay(1), 100);
  assert.equal(retryDelay(2), 200);
  assert.equal(retryDelay(3, { base: 50 }), 200);
});

test('the delay stops at max', () => {
  assert.equal(retryDelay(10, { max: 1000 }), 1000);
});

test('jitter takes a share off early delays', () => {
  assert.equal(retryDelay(1, { jitter: 0.5 }), 50);
});

test('attempts start at 1', () => {
  assert.throws(() => retryDelay(0), RangeError);
  assert.throws(() => retryDelay(1.5), RangeError);
});

test('the default cap is 30 seconds', () => {
  assert.equal(retryDelay(20), 30_000);
});
