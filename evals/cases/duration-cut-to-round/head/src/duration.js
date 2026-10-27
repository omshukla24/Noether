// Formats a duration in milliseconds as "1h 2m 3.4s". Seconds keep one decimal.
const UNITS = [
  ["d", 86_400_000],
  ["h", 3_600_000],
  ["m", 60_000],
];

// summed timers carry float error, so seconds are rounded to the nearest tenth
function tenths(rest) {
  return Math.round(rest / 100) / 10;
}

export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) throw new RangeError("duration must be a non-negative number");
  const parts = [];
  let rest = ms;
  for (const [label, size] of UNITS) {
    const count = Math.floor(rest / size);
    if (count > 0) parts.push(`${count}${label}`);
    rest -= count * size;
  }
  const seconds = tenths(rest);
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds}s`);
  return parts.join(" ");
}
