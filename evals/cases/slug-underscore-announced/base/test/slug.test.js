import { test } from 'node:test';
import assert from 'node:assert/strict';
import { slugify } from '../src/slug.js';

test('words are lowercased and joined', () => {
  assert.equal(slugify('Hello World'), 'hello-world');
});

test('camelCase and acronym-led words are split', () => {
  assert.equal(slugify('fooBar'), 'foo-bar');
  assert.equal(slugify('HTMLParser'), 'html-parser');
});

test('accents are dropped and edges trimmed', () => {
  assert.equal(slugify('Crème brûlée!'), 'creme-brulee');
  assert.equal(slugify('  --trim me--  '), 'trim-me');
});
