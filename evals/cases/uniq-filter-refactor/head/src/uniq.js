// Keeps the first item for every key, in the order the keys first appear.
export function uniqBy(items, key) {
  const seen = new Set();
  return items.filter((item) => {
    const k = key(item);
    return !seen.has(k) && seen.add(k);
  });
}
