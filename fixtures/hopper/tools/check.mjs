// Prints the facts that make Hopper a good Noether fixture, and exits non-zero if any of them is false.
//
//   node tools/check.mjs
//
// It runs base, head and a "fixed" head (head with only the slipped line put back),
// all against the same recorded ghost run.
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { gapReport } from "./gap.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SLIP_HEAD = "const friction = (held) => (held ? RUN_FRICTION : STOP_FRICTION);";
const SLIP_FIXED = "const friction = (held) => (state.grounded ? (held ? RUN_FRICTION : STOP_FRICTION) : 1);";

let failures = 0;
function fact(ok, text) {
  if (!ok) failures++;
  console.log(`${ok ? "ok  " : "FAIL"} ${text}`);
}
const n = (v, d = 3) => v.toFixed(d);

async function load(srcDir) {
  const url = (f) => pathToFileURL(join(srcDir, f)).href;
  const [physics, level, ghost, replay] = await Promise.all(
    ["physics.js", "level.js", "ghost.js", "replay.js"].map((f) => import(url(f))),
  );
  return { ...physics, ...level, ...ghost, ...replay };
}

/** A copy of head/src in a temp folder with one source line swapped for another. */
function variant(name, edits) {
  const dir = mkdtempSync(join(tmpdir(), `hopper-${name}-`));
  cpSync(join(ROOT, "head", "src"), dir, { recursive: true });
  let text = readFileSync(join(dir, "physics.js"), "utf8");
  for (const [from, to] of edits) {
    if (text.split(from).length !== 2) throw new Error(`expected exactly one "${from}" in head/src/physics.js`);
    text = text.replace(from, to);
  }
  writeFileSync(join(dir, "physics.js"), text);
  return dir;
}

function ownSuite(version) {
  const run = spawnSync(process.execPath, ["--test"], { cwd: join(ROOT, version), encoding: "utf8" });
  const grab = (word) => Number((run.stdout.match(new RegExp(`(?:ℹ|#) ${word} (\\d+)`)) ?? [0, NaN])[1]);
  return { exit: run.status, pass: grab("pass"), fail: grab("fail") };
}

/** Longest line-diff: head line numbers that do not appear in base, in order. */
function changedHeadLines(baseText, headText) {
  const a = baseText.split("\n");
  const b = headText.split("\n");
  const lcs = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const changed = [];
  let i = 0;
  let j = 0;
  while (j < b.length) {
    if (i < a.length && a[i] === b[j]) {
      i++;
      j++;
    } else if (i < a.length && lcs[i + 1][j] >= lcs[i][j + 1]) {
      i++;
    } else {
      changed.push(j + 1);
      j++;
    }
  }
  return changed;
}

function hunks(lines) {
  const out = [];
  for (const line of lines) {
    const last = out[out.length - 1];
    if (last && last.start + last.length === line) last.length++;
    else out.push({ start: line, length: 1 });
  }
  return out;
}

/** Walks off a ledge and reports the latest airborne frame a jump press still works on. */
function coyoteFrames(P) {
  const ledge = {
    spawn: [0, 0, 0],
    killY: -50,
    platforms: [{ id: "ledge", min: [-10, -4, -5], max: [5, 0, 5] }],
    coins: [],
    goal: { id: "g", min: [999, 0, 0], max: [1000, 1, 1] },
  };
  let best = 0;
  for (let wait = 0; wait <= 12; wait++) {
    let s = P.createState(ledge);
    s = { ...s, pos: [4.2, 0, 0] };
    let f = 0;
    while (s.grounded && f < 60) s = P.step(s, { x: 1, z: 0, jump: false }, ledge, f++);
    for (let k = 1; k < wait; k++) s = P.step(s, { x: 1, z: 0, jump: false }, ledge, f++);
    const jumped = P.step(s, { x: 1, z: 0, jump: true }, ledge, f);
    if (jumped.vel[1] > 0) best = wait;
  }
  return best;
}

/** Drops from far up and reports the fastest downward speed it reaches. */
function terminalSpeed(P) {
  const shaft = {
    spawn: [0, 200, 0],
    killY: -500,
    platforms: [],
    coins: [],
    goal: { id: "g", min: [999, 0, 0], max: [1000, 1, 1] },
  };
  let s = { ...P.createState(shaft), grounded: false, airFrames: 99 };
  let fastest = 0;
  for (let f = 0; f < 600; f++) {
    s = P.step(s, { x: 0, z: 0, jump: false }, shaft, f);
    fastest = Math.max(fastest, -s.vel[1]);
  }
  return fastest;
}

/** Horizontal speed left 30 frames after leaving the ground at a full run, no stick held in the air. */
function airSpeed(P) {
  const field = {
    spawn: [0, 0, 0],
    killY: -50,
    platforms: [{ id: "floor", min: [-10, -4, -5], max: [400, 0, 5] }],
    coins: [],
    goal: { id: "g", min: [999, 0, 0], max: [1000, 1, 1] },
  };
  let s = P.createState(field);
  let f = 0;
  for (; f < 40; f++) s = P.step(s, { x: 1, z: 0, jump: false }, field, f);
  s = P.step(s, { x: 1, z: 0, jump: true }, field, f++);
  for (let k = 0; k < 30; k++) s = P.step(s, { x: 0, z: 0, jump: false }, field, f++);
  return Math.abs(s.vel[0]);
}

/** Deterministic pseudo-random input runs, to compare two builds frame by frame. */
function sameEverywhere(A, B, level) {
  let seed = 12345;
  const rand = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
  const pick = () => Math.floor(rand() * 3) - 1;
  for (let run = 0; run < 40; run++) {
    let a = A.createState(level);
    let b = B.createState(level);
    for (let f = 0; f < 900; f++) {
      const input = { x: rand() < 0.7 ? 1 : pick(), z: rand() < 0.8 ? 0 : pick(), jump: rand() < 0.08 };
      a = A.step(a, input, level, f);
      b = B.step(b, input, level, f);
      if (JSON.stringify(a) !== JSON.stringify(b)) return false;
    }
  }
  return true;
}

/** Biggest gap a full speed jump can clear, trying every takeoff point. */
function gapCapacity(P) {
  const edge = 30;
  const run = {
    spawn: [0, 0, 0],
    killY: -12,
    platforms: [{ id: "near", min: [-10, -4, -5], max: [edge, 0, 5] }],
    coins: [],
    goal: { id: "g", min: [999, 0, 0], max: [1000, 1, 1] },
  };
  let best = 0;
  for (let takeoff = 25; takeoff <= 33; takeoff += 0.01) {
    let s = P.createState(run);
    for (let f = 0; f < 400; f++) {
      const jump = s.pos[0] >= takeoff && !s.jumpHeld;
      const next = P.step(s, { x: 1, z: 0, jump }, run, f);
      if (s.vel[1] < 0 && s.pos[1] >= 0 && next.pos[1] < 0) {
        const t = s.pos[1] / (s.pos[1] - next.pos[1]);
        best = Math.max(best, s.pos[0] + t * (next.pos[0] - s.pos[0]) + P.PLAYER_HALF - edge);
        break;
      }
      s = next;
    }
  }
  return best;
}

const base = await load(join(ROOT, "base", "src"));
const head = await load(join(ROOT, "head", "src"));
const fixedDir = variant("fixed", [[SLIP_HEAD, SLIP_FIXED]]);
const revertedDir = variant("reverted", [
  [SLIP_HEAD, SLIP_FIXED],
  ["export const COYOTE_FRAMES = 6;", "export const COYOTE_FRAMES = 4;"],
  ["export const TERMINAL_SPEED = 22;", "export const TERMINAL_SPEED = 18;"],
]);
const fixed = await load(join(fixedDir, ""));
const reverted = await load(join(revertedDir, ""));

try {
  const { LEVEL } = base;
  const inputs = base.expand(base.GHOST);
  const far = LEVEL.platforms.find((p) => p.id === "s7");
  const near = LEVEL.platforms.find((p) => p.id === "s6");

  console.log("\n1. the repo's own suite");
  for (const version of ["base", "head"]) {
    const r = ownSuite(version);
    fact(r.exit === 0 && r.fail === 0 && r.pass > 0, `${version}: node --test exit ${r.exit}, ${r.pass} passed, ${r.fail} failed`);
  }

  console.log("\n2. the recorded run (" + inputs.length + " frames, " + base.GHOST.length + " segments)");
  const runs = {};
  for (const [name, P] of [["base", base], ["head", head], ["fixed", fixed]]) {
    const r = P.simulate(LEVEL, inputs, { extraFrames: 150 });
    runs[name] = { r, gap: gapReport(LEVEL, r) };
    const g = runs[name].gap;
    const where = r.fellAtFrame === null ? "" : `, hits the kill plane at frame ${r.fellAtFrame}`;
    console.log(
      `     ${name}: reachedGoal ${r.reachedGoal}, goalFrame ${r.goalFrame}, coins ${r.coins}${where}\n` +
        `            long jump: takeoff frame ${g.takeoffFrame} at x ${n(g.takeoffX, 2)}, front of the box at ${n(g.reach)} when it comes down, far edge ${far.min[0]}, margin ${n(g.margin)}`,
    );
  }
  fact(runs.base.r.reachedGoal === true, "base: ghost reaches the goal");
  fact(runs.base.gap.margin >= 0.25, `base: clears the long gap by ${n(runs.base.gap.margin)} (needs >= 0.25)`);
  fact(runs.head.r.reachedGoal === false, "head: ghost does not reach the goal");
  fact(-runs.head.gap.margin >= 0.25, `head: still ${n(-runs.head.gap.margin)} short of the far edge when it comes down to its height (needs >= 0.25)`);
  const gapX = runs.head.gap.centre;
  fact(
    runs.head.r.fellAtFrame !== null && gapX > near.max[0] && gapX < far.min[0],
    `head: comes down at x ${n(gapX, 2)}, inside the gap (${near.max[0]} to ${far.min[0]}), and hits the kill plane at frame ${runs.head.r.fellAtFrame}`,
  );
  const earlierFall = runs.head.r.frames.slice(0, runs.head.gap.takeoffFrame).some((fr, i) => i > 0 && fr.pos[1] < -1);
  fact(!earlierFall, "head: gets all the way to the long gap without falling");

  console.log("\n3. the change that breaks it");
  const baseText = readFileSync(join(ROOT, "base", "src", "physics.js"), "utf8");
  const headText = readFileSync(join(ROOT, "head", "src", "physics.js"), "utf8");
  const changed = changedHeadLines(baseText, headText);
  const hunkList = hunks(changed);
  const slipLine = headText.split("\n").findIndex((l) => l.trim() === SLIP_HEAD) + 1;
  fact(slipLine > 0, `head/src/physics.js line ${slipLine}: ${SLIP_HEAD}`);
  fact(!baseText.includes(SLIP_HEAD), "that line does not exist in base (it is a changed line)");
  fact(hunkList.some((h) => slipLine >= h.start && slipLine < h.start + h.length), `it sits inside a head-side hunk: ${hunkList.map((h) => `${h.start}+${h.length}`).join(", ")}`);
  const differing = readFileSync(join(fixedDir, "physics.js"), "utf8").split("\n").filter((l, i) => l !== headText.split("\n")[i]);
  fact(differing.length === 1, `restoring that single line is the whole fix (${differing.length} line differs between head and fixed)`);

  console.log("\n4. the announced changes show up in a test written against base");
  const probes = [
    ["coyote frames", coyoteFrames, 4, "coyote 4 -> 6"],
    ["terminal speed", terminalSpeed, 18, "terminal 18 -> 22"],
  ];
  for (const [label, probe, expected, change] of probes) {
    const onBase = probe(base);
    const onHead = probe(head);
    fact(Math.abs(onBase - expected) < 0.01 && Math.abs(onHead - expected) > 0.5, `${label}: base ${n(onBase, 2)} (test passes), head ${n(onHead, 2)} (test fails), ${change}`);
  }
  const airBase = airSpeed(base);
  const airHead = airSpeed(head);
  fact(airBase > 9.9 && airHead < 2, `air speed 30 frames after a full speed jump, stick released: base ${n(airBase, 2)}, head ${n(airHead, 2)} (nobody announced this)`);

  console.log("\n5. fixed head (only the slipped line restored)");
  fact(runs.fixed.r.reachedGoal === true, `fixed: ghost reaches the goal at frame ${runs.fixed.r.goalFrame}, margin ${n(runs.fixed.gap.margin)}`);
  fact(coyoteFrames(fixed) === 6, `fixed: coyote time is still ${coyoteFrames(fixed)} frames`);
  fact(Math.abs(terminalSpeed(fixed) - 22) < 0.01, `fixed: terminal speed is still ${n(terminalSpeed(fixed), 2)}`);
  fact(sameEverywhere(base, reverted, LEVEL), "refactor is exact: fixed head with the two announced values put back matches base on 40 random runs, frame by frame");

  console.log("\n6. how big a gap a full speed jump can clear");
  const longGap = far.min[0] - near.max[0];
  for (const [name, P] of [["base", base], ["head", head], ["fixed", fixed]]) {
    const cap = gapCapacity(P);
    console.log(`     ${name}: ${n(cap, 3)} (the level's long gap is ${n(longGap, 2)})`);
  }
  fact(gapCapacity(base) > longGap, "base can clear the long gap");
  fact(gapCapacity(head) < longGap, "head cannot clear the long gap even with perfect timing");
} finally {
  rmSync(fixedDir, { recursive: true, force: true });
  rmSync(revertedDir, { recursive: true, force: true });
}

console.log(failures === 0 ? "\nall facts hold" : `\n${failures} fact(s) failed`);
process.exit(failures === 0 ? 0 : 1);
