import { test } from 'node:test';
import assert from 'node:assert/strict';
import { slugify } from '../src/slug.js';

test('words are lowercased and joined', () => {
  assert.equal(slugify('Hello World'), 'hello_world');
});

test('camelCase and acronym-led words are split', () => {
  assert.equal(slugify('fooBar'), 'foo_bar');
  assert.equal(slugify('HTMLParser'), 'html_parser');
});

test('accents are dropped and edges trimmed', () => {
  assert.equal(slugify('Crème brûlée!'), 'creme_brulee');
  assert.equal(slugify('  --trim me--  '), 'trim_me');
});
