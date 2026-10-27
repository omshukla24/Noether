// Turns a title into a URL slug: accents are dropped, camelCase and acronyms are split into words, everything
// is lowercased and any run of other characters becomes one hyphen.
export function slugify(text) {
  return String(text)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/([a-z\d])([A-Z])/g, "$1-$2")
    .replace(/([A-Z]+)([A-Z][a-z\d]+)/g, "$1-$2")
    .toLowerCase()
    .replace(/[^a-z\d]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
