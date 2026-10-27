import { test } from 'node:test';
import assert from 'node:assert/strict';
import { camelCase } from '../src/camel.js';

test('separators start a new word', () => {
  assert.equal(camelCase('foo-bar'), 'fooBar');
  assert.equal(camelCase('foo bar.baz'), 'fooBarBaz');
});

test('input case does not matter', () => {
  assert.equal(camelCase('FOO_BAR'), 'fooBar');
});

test('nothing but separators gives an empty string', () => {
  assert.equal(camelCase('  --  '), '');
});

test('a long number ends a word', () => {
  assert.equal(camelCase('foo123bar'), 'foo123Bar');
  assert.equal(camelCase('aa11aa'), 'aa11Aa');
});
