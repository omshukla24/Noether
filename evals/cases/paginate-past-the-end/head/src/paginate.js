// Page `page` (1-based) of `total` items, `perPage` at a time. A page past the end is empty rather than an
// error, and an empty list has zero pages. start and end are item offsets: items.slice(start, end) is the page.
function assertInt(value, min, message) {
  if (!Number.isInteger(value) || value < min) throw new RangeError(message);
}

export function paginate(total, { page = 1, perPage = 10 } = {}) {
  assertInt(total, 0, "total must be a non-negative integer");
  assertInt(page, 1, "page starts at 1");
  assertInt(perPage, 1, "perPage must be at least 1");
  const pages = Math.ceil(total / perPage);
  const start = (page - 1) * perPage;
  const end = Math.min(start + perPage, total);
  return { pages, start, end, hasNext: page < pages };
}
