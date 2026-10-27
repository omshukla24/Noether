// Hopper physics. step() is a pure function: it never touches its arguments
// and uses no clock or randomness, so the same inputs always give the same run.
// The player is a box: pos is the middle of its feet, so pos[1] is the floor level.
import { boxAt } from "./level.js";

export const DT = 1 / 60;
export const GRAVITY = 40; // units per second squared
export const RUN_ACCEL = 60;
export const AIR_CONTROL = 0.1; // share of RUN_ACCEL you keep in the air
export const MAX_RUN_SPEED = 10;
export const RUN_FRICTION = 0.985; // speed kept per frame on the ground while holding a direction
export const STOP_FRICTION = 0.8; // speed kept per frame on the ground with no direction held
export const JUMP_SPEED = 14;
export const COYOTE_FRAMES = 6;
export const JUMP_BUFFER_FRAMES = 5;
export const TERMINAL_SPEED = 22;
export const PLAYER_HALF = 0.4;
export const PLAYER_HEIGHT = 1.6;
export const COIN_RADIUS = 0.6;

const BELOW = [PLAYER_HALF, 0, PLAYER_HALF]; // how far the box reaches below pos, per axis
const ABOVE = [PLAYER_HALF, PLAYER_HEIGHT, PLAYER_HALF];

export function createState(level) {
  return {
    pos: [...level.spawn],
    vel: [0, 0, 0],
    grounded: true,
    airFrames: 0, // frames spent in the air since the feet last touched something
    buffer: 0, // frames left on a queued jump press
    jumpHeld: false,
    standingOn: null, // id of the platform under the feet, used to ride movers
    coins: [], // indexes into level.coins already picked up
    deaths: 0,
  };
}

export function playerBox(pos) {
  return {
    min: [pos[0] - BELOW[0], pos[1] - BELOW[1], pos[2] - BELOW[2]],
    max: [pos[0] + ABOVE[0], pos[1] + ABOVE[1], pos[2] + ABOVE[2]],
  };
}

/** Boxes that only share a face do not overlap. */
export function overlaps(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a.min[i] >= b.max[i] || a.max[i] <= b.min[i]) return false;
  }
  return true;
}

export function touchesGoal(state, level) {
  return overlaps(playerBox(state.pos), level.goal);
}

function touchesCoin(pos, coin) {
  const box = playerBox(pos);
  let dist2 = 0;
  for (let i = 0; i < 3; i++) {
    const nearest = Math.min(Math.max(coin[i], box.min[i]), box.max[i]);
    dist2 += (coin[i] - nearest) * (coin[i] - nearest);
  }
  return dist2 <= COIN_RADIUS * COIN_RADIUS;
}

function readInput(input) {
  const clamp = (v) => Math.max(-1, Math.min(1, Number(v) || 0));
  return { x: clamp(input.x), z: clamp(input.z), jump: Boolean(input.jump) };
}

/** Slide the player along one axis and push out of whatever it ran into. */
function moveAxis(pos, vel, axis, boxes) {
  pos[axis] += vel[axis] * DT;
  let hit = null;
  for (const { id, box } of boxes) {
    if (!overlaps(playerBox(pos), box)) continue;
    const centre = (box.min[axis] + box.max[axis]) / 2;
    const dir = vel[axis] > 0 ? 1 : vel[axis] < 0 ? -1 : pos[axis] < centre ? 1 : -1;
    pos[axis] = dir > 0 ? box.min[axis] - ABOVE[axis] : box.max[axis] + BELOW[axis];
    vel[axis] = 0;
    hit = { id, dir };
  }
  return hit;
}

/** A moving platform drags whoever stood on it last frame. */
function rideAlong(state, level, frame) {
  const pos = [...state.pos];
  const ride = level.platforms.find((p) => p.id === state.standingOn && p.move);
  if (!ride) return pos;
  const now = boxAt(ride, frame);
  const next = boxAt(ride, frame + 1);
  for (let i = 0; i < 3; i++) pos[i] += next.min[i] - now.min[i];
  return pos;
}

function respawn(state, level) {
  return { ...createState(level), coins: state.coins, deaths: state.deaths + 1 };
}

/**
 * Velocity and collision for one frame: everything between "what did the player
 * press" and "where did they end up". Moves `pos` in place, it is the caller's copy.
 */
function integrate(state, pos, move, jumping, boxes) {
  // sideways: accelerate toward the stick, friction eats the rest
  const accel = (state.grounded ? RUN_ACCEL : RUN_ACCEL * AIR_CONTROL) * DT;
  const friction = (held) => (held ? RUN_FRICTION : STOP_FRICTION);
  const vel = [
    (state.vel[0] + move.x * accel) * friction(move.x !== 0),
    Math.max(state.vel[1] - GRAVITY * DT, -TERMINAL_SPEED),
    (state.vel[2] + move.z * accel) * friction(move.z !== 0),
  ];
  const speed = Math.sqrt(vel[0] * vel[0] + vel[2] * vel[2]);
  if (speed > MAX_RUN_SPEED) {
    vel[0] *= MAX_RUN_SPEED / speed;
    vel[2] *= MAX_RUN_SPEED / speed;
  }
  if (jumping) vel[1] = JUMP_SPEED;

  // one axis at a time, so a wall stops you without stopping the fall
  moveAxis(pos, vel, 0, boxes);
  moveAxis(pos, vel, 2, boxes);
  const floor = moveAxis(pos, vel, 1, boxes);
  return { vel, floor: floor !== null && floor.dir < 0 ? floor : null };
}

/** Advance one frame (state at time `frame` -> state at `frame + 1`). */
export function step(state, input, level, frame) {
  const move = readInput(input);
  const boxes = level.platforms.map((p) => ({ id: p.id, box: boxAt(p, frame + 1) }));
  const pos = rideAlong(state, level, frame);

  // a jump press stays queued for a few frames, so tapping slightly early still counts
  const pressed = move.jump && !state.jumpHeld;
  let buffer = pressed ? JUMP_BUFFER_FRAMES : Math.max(0, state.buffer - 1);
  // coyote time: after walking off a ledge you can still jump for a few frames
  const canJump = state.airFrames <= COYOTE_FRAMES;
  const jumping = buffer > 0 && canJump;
  if (jumping) buffer = 0;

  const { vel, floor } = integrate(state, pos, move, jumping, boxes);
  const landed = floor !== null;

  const coins = [...state.coins];
  level.coins.forEach((coin, i) => {
    if (!coins.includes(i) && touchesCoin(pos, coin)) coins.push(i);
  });

  const next = {
    pos,
    vel,
    grounded: landed,
    airFrames: jumping ? COYOTE_FRAMES + 1 : landed ? 0 : state.airFrames + 1,
    buffer,
    jumpHeld: move.jump,
    standingOn: landed ? floor.id : null,
    coins,
    deaths: state.deaths,
  };
  return pos[1] < level.killY ? respawn(next, level) : next;
}
