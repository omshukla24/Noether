// Keeps one item for every key, in the order the keys first appear.
export function uniqBy(items, key) {
  const byKey = new Map();
  for (const item of items) byKey.set(key(item), item);
  return [...byKey.values()];
}
