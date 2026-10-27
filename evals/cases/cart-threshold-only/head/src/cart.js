// Cart maths. Money is kept in whole cents inside every calculation so float
// error never leaks into a total.
export const FREE_SHIPPING_THRESHOLD = 75;
export const SHIPPING_FEE = 4.99;

export function toCents(amount) {
  return Math.round(amount * 100);
}

export function fromCents(cents) {
  return cents / 100;
}

export function roundMoney(amount) {
  return fromCents(toCents(amount));
}

export function lineTotal(item) {
  return roundMoney(item.price * item.qty);
}

export function subtotal(items) {
  return fromCents(items.reduce((sum, item) => sum + toCents(lineTotal(item)), 0));
}

export function discountAmount(amount, percent) {
  return fromCents(Math.round((toCents(amount) * percent) / 100));
}

export function shippingFor(amount) {
  return amount >= FREE_SHIPPING_THRESHOLD ? 0 : SHIPPING_FEE;
}

export function orderTotal(items, discountPercent = 0) {
  const sub = subtotal(items);
  const discounted = fromCents(toCents(sub) - toCents(discountAmount(sub, discountPercent)));
  return roundMoney(discounted + shippingFor(discounted));
}
