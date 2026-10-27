// The one Hopper level. x runs along the level, y is up, z is sideways.
// Boxes are { id, min: [x, y, z], max: [x, y, z] }. A platform with `move`
// slides along one axis on a triangle wave of the frame number.

export const LEVEL = {
  spawn: [0, 0, 0],
  killY: -12,
  platforms: [
    { id: "start", min: [-4, -4, -5], max: [9, 0, 5] },
    { id: "s1", min: [11.5, -4, -5], max: [18, 0.8, 5] },
    { id: "s2", min: [20.5, -4, -5], max: [26, 1.6, 5] },
    { id: "s3", min: [28.5, -4, 3], max: [35, 1.6, 10] },
    { id: "s4", min: [37.5, -4, -2], max: [43, 2.4, 8] },
    { id: "s5", min: [45.5, -4, -5], max: [52, 1.6, 5] },
    // the ferry carries you across the 10 unit pit between s5 and s6
    {
      id: "ferry",
      min: [52, -0.4, -2],
      max: [56, 1.6, 2],
      move: { axis: 0, range: 6, period: 360, phase: 20 },
    },
    { id: "s6", min: [62, -4, -5], max: [72, 1.6, 5] },
    // the long gap: s6 ends at x = 72, s7 starts at x = 80.15
    { id: "s7", min: [80.15, -4, -5], max: [89.15, 1.6, 5] },
  ],
  coins: [
    [14.5, 1.8, 0],
    [32, 2.6, 6.5],
    [40.2, 3.4, 5.5],
    [57.5, 2.6, 0],
    [76.3, 4.4, 0],
  ],
  goal: { id: "goal", min: [85.65, 1.6, -1.5], max: [87.65, 4.6, 1.5] },
};

/** Where a platform's box is at a given frame. Fixed platforms return themselves. */
export function boxAt(platform, frame) {
  const move = platform.move;
  if (!move) return platform;
  const t = ((frame + move.phase) % move.period) / move.period;
  const offset = move.range * (t < 0.5 ? 2 * t : 2 - 2 * t);
  const min = [...platform.min];
  const max = [...platform.max];
  min[move.axis] += offset;
  max[move.axis] += offset;
  return { min, max };
}
