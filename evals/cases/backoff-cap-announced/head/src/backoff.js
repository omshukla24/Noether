// Delay in ms before retry number `attempt` (1 is the first retry). It doubles from `base` up to `max`, then
// `jitter` (0 to 1) takes that share off, so clients that fail together do not all come back together.
export function retryDelay(attempt, { base = 100, max = 10_000, jitter = 0 } = {}) {
  if (!Number.isInteger(attempt) || attempt < 1) throw new RangeError("attempt starts at 1");
  const capped = Math.min(base * 2 ** (attempt - 1), max);
  return Math.round(capped * (1 - jitter));
}
