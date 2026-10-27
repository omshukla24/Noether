// Keeps the first item for every key, in the order the keys first appear.
export function uniqBy(items, key) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const k = key(item);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(item);
  }
  return out;
}
