// A recorded run that beats the level. Each segment is
// [frames, moveX, moveZ, jump]: hold that input for that many frames.
// jump is 1 while the button is down, so [1, 1, 0, 1] is a one frame tap.
export const GHOST = [
  [53, 1, 0, 0],
  [1, 1, 0, 1],
  [53, 1, 0, 0],
  [1, 1, 0, 1],
  [39, 1, 0, 0],
  [15, 1, 1, 0],
  [1, 1, 1, 1],
  [42, 1, 1, 0],
  [6, 1, 0, 0],
  [4, 1, -1, 0],
  [3, 1, 0, 0],
  [1, 1, -1, 0],
  [6, 1, 0, 0],
  [1, 1, 0, 1],
  [39, 1, 0, 0],
  [4, 1, -1, 0],
  [1, 1, -1, 1],
  [31, 1, -1, 0],
  [11, 1, 0, 0],
  [4, 1, 1, 0],
  [7, 1, -1, 0],
  [1, 0, -1, 0],
  [8, 1, -1, 0],
  [4, 1, 0, 0],
  [1, 1, -1, 0],
  [19, 1, 0, 0],
  [164, 0, 0, 0],
  [76, 1, 0, 0],
  [1, 1, 0, 1],
  [74, 1, 0, 0],
];

/** Turn segments into one { x, z, jump } per frame. */
export function expand(ghost) {
  const inputs = [];
  for (const [frames, x, z, jump] of ghost) {
    if (!Number.isInteger(frames) || frames < 1) {
      throw new RangeError(`ghost segment needs a whole number of frames, got ${frames}`);
    }
    for (let i = 0; i < frames; i++) inputs.push({ x, z, jump: Boolean(jump) });
  }
  return inputs;
}
