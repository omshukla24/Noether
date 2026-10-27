import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatDuration } from '../src/duration.js';

test('zero reads as 0s', () => {
  assert.equal(formatDuration(0), '0s');
});

test('seconds keep one decimal', () => {
  assert.equal(formatDuration(1500), '1.5s');
  assert.equal(formatDuration(2000), '2s');
});

test('minutes, hours and days stack', () => {
  assert.equal(formatDuration(61_000), '1m 1s');
  assert.equal(formatDuration(3_661_000), '1h 1m 1s');
  assert.equal(formatDuration(90_000_000), '1d 1h');
});

test('a negative or non-finite duration throws', () => {
  assert.throws(() => formatDuration(-1), RangeError);
  assert.throws(() => formatDuration(Number.NaN), RangeError);
});

test('1999 ms rounds to 2s', () => {
  assert.equal(formatDuration(1999), '2s');
});
