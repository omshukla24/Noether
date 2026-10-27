import { test } from 'node:test';
import assert from 'node:assert/strict';
import { discountAmount, lineTotal, orderTotal, shippingFor, subtotal } from '../src/cart.js';

test('line total multiplies price by quantity', () => {
  assert.equal(lineTotal({ price: 9.99, qty: 3 }), 29.97);
});

test('subtotal adds the line totals', () => {
  assert.equal(subtotal([{ price: 10, qty: 2 }, { price: 5.5, qty: 1 }]), 25.5);
});

test('a round discount is exact', () => {
  assert.equal(discountAmount(100, 10), 10);
});

test('small orders pay shipping', () => {
  assert.equal(shippingFor(20), 4.99);
});

test('free shipping from 75', () => {
  assert.equal(shippingFor(100), 0);
});

test('order total adds shipping to a small order', () => {
  assert.equal(orderTotal([{ price: 10, qty: 2 }]), 24.99);
});
