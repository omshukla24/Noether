// Page `page` (1-based) of `total` items, `perPage` at a time. A page past the end is empty rather than an
// error, and an empty list has zero pages. start and end are item offsets: items.slice(start, end) is the page.
export function paginate(total, { page = 1, perPage = 10 } = {}) {
  if (!Number.isInteger(total) || total < 0) throw new RangeError("total must be a non-negative integer");
  if (!Number.isInteger(page) || page < 1) throw new RangeError("page starts at 1");
  if (!Number.isInteger(perPage) || perPage < 1) throw new RangeError("perPage must be at least 1");
  const pages = Math.ceil(total / perPage);
  const start = Math.min((page - 1) * perPage, total);
  const end = Math.min(start + perPage, total);
  return { pages, start, end, hasNext: page < pages };
}
