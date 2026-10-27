// Builds the ghost run and freezes it into src/ghost.js. Not shipped to the browser.
//
//   node tools/build-ghost.mjs            search and print the segments
//   node tools/build-ghost.mjs --write    also write base/src/ghost.js and head/src/ghost.js
//
// The ghost is a scripted route, tuned by simulation. Every candidate is stepped
// on base and on head at once and thrown away if either one falls, so the ghost
// is clean on both versions until the long gap on the last platform. That gap is
// the only place the two versions differ, which is the whole point of the fixture.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as baseP from "../base/src/physics.js";
import * as headP from "../head/src/physics.js";
import { LEVEL, boxAt } from "../base/src/level.js";
import { expand } from "../base/src/ghost.js";
import { simulate } from "../base/src/replay.js";
import { simulate as simulateHead } from "../head/src/replay.js";
import { gapReport } from "./gap.mjs";

const platform = (id) => LEVEL.platforms.find((p) => p.id === id);
const RUNUP_X = 66; // the long jump starts from a run on s6, at least this far along

const LEGS = [
  { from: "start", to: "s1", tz: 0 },
  { from: "s1", to: "s2", tz: 0 },
  { from: "s2", to: "s3", tz: 6.3 },
  { from: "s3", to: "s4", tz: 5.9 },
  { from: "s4", to: "s5", tz: 3 },
];

/** Bang-bang steering toward a z target that brakes before it gets there. */
function steerZ(state, target) {
  const dz = target - state.pos[2];
  const brake = Math.abs(state.vel[2]) * 0.07;
  if (Math.abs(dz) <= brake + 0.1) return 0;
  return Math.sign(dz);
}

function advance(pair, input) {
  const b = baseP.step(pair.b, input, LEVEL, pair.f);
  const h = headP.step(pair.h, input, LEVEL, pair.f);
  return { b, h, f: pair.f + 1, inputs: [...pair.inputs, input] };
}

const dead = (p) => p.b.deaths > 0 || p.h.deaths > 0;

/** Run toward `leg.to` and tap jump once when the player reaches x = jx. */
function runLeg(start, leg, jx) {
  const to = platform(leg.to);
  let pair = start;
  let jumped = false;
  for (let i = 0; i < 150; i++) {
    const jump = !jumped && pair.b.pos[0] >= jx;
    if (jump) jumped = true;
    pair = advance(pair, { x: 1, z: steerZ(pair.b, leg.tz), jump });
    if (dead(pair)) return null;
    if (jumped && pair.b.standingOn === leg.to && pair.h.standingOn === leg.to) {
      const roomB = pair.b.pos[0] - to.min[0];
      const roomH = pair.h.pos[0] - to.min[0];
      const zOk = Math.abs(pair.b.pos[2] - leg.tz) < 1.5;
      return roomB >= 1 && roomH >= 0.6 && zOk ? pair : null;
    }
  }
  return null;
}

/** Try every takeoff point and take the middle of the ones that work, so it is not a knife edge. */
function planLeg(start, leg) {
  const from = platform(leg.from);
  const good = [];
  for (let jx = from.max[0] - 2.5; jx <= from.max[0] + 0.5; jx += 0.1) {
    const pair = runLeg(start, leg, jx);
    if (pair) good.push({ jx, pair });
  }
  if (good.length === 0) throw new Error(`no takeoff works for ${leg.from} -> ${leg.to}`);
  return good[Math.floor(good.length / 2)].pair;
}

/** Wait at the edge of s5, ride the ferry across, walk off onto s6 and build up speed. */
function planFerry(start) {
  const period = platform("ferry").move.period;
  let best = null;
  for (const stopX of [49.8, 50.6, 51.2]) {
    let waitPair = start;
    for (let i = 0; i < 200 && waitPair.b.pos[0] < stopX; i++) {
      waitPair = advance(waitPair, { x: 1, z: steerZ(waitPair.b, 0), jump: false });
    }
    if (dead(waitPair)) continue;
    // the earliest boarding frame that works is the shortest wait
    for (let board = waitPair.f; board < waitPair.f + period; board++) {
      const pair = tryFerry(waitPair, board);
      if (!pair) continue;
      if (!best || pair.f < best.f) best = pair;
      break;
    }
  }
  if (!best) throw new Error("no ferry timing works");
  return best;
}

function tryFerry(waitPair, board) {
  const ferry = platform("ferry");
  const { period, phase } = ferry.move;
  let pair = waitPair;
  while (pair.f < board) {
    pair = advance(pair, { x: 0, z: steerZ(pair.b, 0), jump: false });
    if (dead(pair)) return null;
  }
  // walk onto the ferry and stop near its front
  for (let i = 0; i < 80; i++) {
    const frontGap = pair.b.pos[0] - boxAt(ferry, pair.f).min[0];
    const stopping = pair.b.standingOn === "ferry" && frontGap >= 2.6;
    pair = advance(pair, { x: stopping ? 0 : 1, z: steerZ(pair.b, 0), jump: false });
    if (dead(pair)) return null;
    if (stopping && Math.abs(pair.b.vel[0]) < 0.05) break;
  }
  if (pair.b.standingOn !== "ferry" || pair.h.standingOn !== "ferry") return null;
  // ride until the far end touches s6, then walk off
  while ((pair.f + phase - period / 2) % period !== 0) {
    pair = advance(pair, { x: 0, z: steerZ(pair.b, 0), jump: false });
    if (dead(pair) || pair.f > waitPair.f + 3 * period) return null;
  }
  for (let i = 0; i < 120; i++) {
    pair = advance(pair, { x: 1, z: steerZ(pair.b, 0), jump: false });
    if (dead(pair)) return null;
    if (pair.b.standingOn === "s6" && pair.h.standingOn === "s6" && pair.b.pos[0] >= RUNUP_X && pair.b.vel[0] > 9.9) return pair;
  }
  return null;
}

/** Try every jump frame for the long gap; keep the one that clears it by the widest margin on base and misses most on head. */
function planLongJump(start) {
  let best = null;
  for (let wait = 0; wait <= 60; wait++) {
    const tail = [];
    for (let i = 0; i < wait; i++) tail.push({ x: 1, z: 0, jump: false });
    tail.push({ x: 1, z: 0, jump: true });
    for (let i = 0; i < 200; i++) tail.push({ x: 1, z: 0, jump: false });
    const inputs = [...start.inputs, ...tail];
    const onBase = simulate(LEVEL, inputs);
    if (!onBase.reachedGoal) continue;
    const gb = gapReport(LEVEL, onBase);
    const gh = gapReport(LEVEL, simulateHead(LEVEL, inputs));
    if (!gb || !gh) continue;
    const quality = Math.min(gb.margin, -gh.margin);
    if (!best || quality > best.quality) {
      best = { quality, wait, goalFrame: onBase.goalFrame, baseMargin: gb.margin, headShort: -gh.margin };
    }
  }
  if (!best) throw new Error("no jump timing clears the long gap on base and fails on head");
  return best;
}

function toSegments(inputs) {
  const segs = [];
  for (const { x, z, jump } of inputs) {
    const j = jump ? 1 : 0;
    const last = segs[segs.length - 1];
    if (last && last[1] === x && last[2] === z && last[3] === j) last[0]++;
    else segs.push([1, x, z, j]);
  }
  return segs;
}

function ghostSource(segments) {
  const lines = segments.map((s) => `  [${s.join(", ")}],`).join("\n");
  return `// A recorded run that beats the level. Each segment is
// [frames, moveX, moveZ, jump]: hold that input for that many frames.
// jump is 1 while the button is down, so [1, 1, 0, 1] is a one frame tap.
export const GHOST = [
${lines}
];

/** Turn segments into one { x, z, jump } per frame. */
export function expand(ghost) {
  const inputs = [];
  for (const [frames, x, z, jump] of ghost) {
    if (!Number.isInteger(frames) || frames < 1) {
      throw new RangeError(\`ghost segment needs a whole number of frames, got \${frames}\`);
    }
    for (let i = 0; i < frames; i++) inputs.push({ x, z, jump: Boolean(jump) });
  }
  return inputs;
}
`;
}

let pair = { b: baseP.createState(LEVEL), h: headP.createState(LEVEL), f: 0, inputs: [] };
for (const leg of LEGS) {
  pair = planLeg(pair, leg);
  console.log(`${leg.from} -> ${leg.to}: frame ${pair.f}, x ${pair.b.pos[0].toFixed(2)}, z ${pair.b.pos[2].toFixed(2)}`);
}
const atFerry = pair.f;
pair = planFerry(pair);
console.log(`ferry crossed: s5 edge at frame ${atFerry}, on s6 at frame ${pair.f}, coins ${pair.b.coins.length}`);
const jump = planLongJump(pair);
console.log(`long jump: wait ${jump.wait} frames, base margin ${jump.baseMargin.toFixed(3)}, head short by ${jump.headShort.toFixed(3)}`);

const full = [...pair.inputs];
for (let i = 0; i < jump.wait; i++) full.push({ x: 1, z: 0, jump: false });
full.push({ x: 1, z: 0, jump: true });
while (full.length < jump.goalFrame) full.push({ x: 1, z: 0, jump: false });
const segments = toSegments(full.slice(0, jump.goalFrame));
const check = simulate(LEVEL, expand(segments));
console.log(`ghost: ${segments.length} segments, goal at frame ${check.goalFrame}, coins ${check.coins}, reached ${check.reachedGoal}`);
console.log(JSON.stringify(segments));

if (process.argv.includes("--write")) {
  for (const dir of ["base", "head"]) {
    writeFileSync(fileURLToPath(new URL(`../${dir}/src/ghost.js`, import.meta.url)), ghostSource(segments));
  }
  console.log("wrote base/src/ghost.js and head/src/ghost.js");
}
