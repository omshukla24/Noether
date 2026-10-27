// Run a list of per-frame inputs through step() and report what happened.
import { createState, step, touchesGoal } from "./physics.js";

function snapshot(f, state) {
  return {
    f,
    pos: [...state.pos],
    vel: [...state.vel],
    grounded: state.grounded,
    coins: state.coins.length,
  };
}

const IDLE = { x: 0, z: 0, jump: false };

/**
 * frames[k] is the world at time k, so frames[0] is the spawn and frames[k] is
 * the state after k steps. A fall shows up as the respawn at frames[fellAtFrame].
 * Options:
 *   stopOnFall   stop at the first respawn (default true)
 *   extraFrames  keep going with no input this many frames after the inputs run out (default 0)
 *   maxFrames    never simulate more than this many frames (default: no limit)
 */
export function simulate(level, inputs, opts = {}) {
  const stopOnFall = opts.stopOnFall ?? true;
  const total = Math.min(inputs.length + (opts.extraFrames ?? 0), opts.maxFrames ?? Infinity);
  let state = createState(level);
  const frames = [snapshot(0, state)];
  let goalFrame = null;
  let fellAtFrame = null;

  for (let f = 0; f < total; f++) {
    const next = step(state, inputs[f] ?? IDLE, level, f);
    frames.push(snapshot(f + 1, next));
    const fell = next.deaths > state.deaths;
    state = next;
    if (fell && fellAtFrame === null) fellAtFrame = f + 1;
    if (fell && stopOnFall) break;
    if (touchesGoal(state, level)) {
      goalFrame = f + 1;
      break;
    }
  }
  return {
    frames,
    reachedGoal: goalFrame !== null,
    goalFrame,
    coins: state.coins.length,
    fellAtFrame,
  };
}
