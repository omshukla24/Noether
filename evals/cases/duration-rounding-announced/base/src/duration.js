// Formats a duration in milliseconds as "1h 2m 3.4s". Seconds keep one decimal and are cut, never rounded up,
// so a duration just under a minute never reads as a whole one.
const UNITS = [
  ["d", 86_400_000],
  ["h", 3_600_000],
  ["m", 60_000],
];

export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) throw new RangeError("duration must be a non-negative number");
  const parts = [];
  let rest = ms;
  for (const [label, size] of UNITS) {
    const count = Math.floor(rest / size);
    if (count > 0) parts.push(`${count}${label}`);
    rest -= count * size;
  }
  const seconds = Math.floor(rest / 100) / 10;
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds}s`);
  return parts.join(" ");
}
