// "foo-bar_baz qux" -> "fooBarBazQux". Words are split on - _ . and spaces, each one is lowercased,
// and every word after the first starts with a capital.
const cap = (word) => word[0].toUpperCase() + word.slice(1);

export function camelCase(input) {
  const words = String(input)
    .trim()
    .split(/[-_.\s]+/)
    .filter(Boolean)
    .map((word) => word.toLowerCase());
  return words.map((word, i) => (i === 0 ? word : cap(word))).join("");
}
