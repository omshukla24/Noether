import { test } from "node:test";
import assert from "node:assert/strict";
import { createState, overlaps, playerBox, step } from "../src/physics.js";

const NO_INPUT = { x: 0, z: 0, jump: false };

// a small level of our own, so these tests do not care about the real one
const room = {
  spawn: [0, 0, 0],
  killY: -10,
  platforms: [
    { id: "floor", min: [-5, -2, -5], max: [5, 0, 5] },
    { id: "wall", min: [3, 0, -5], max: [4, 3, 5] },
  ],
  coins: [[0, 1, 0], [2, 1, 3]],
  goal: { id: "goal", min: [-5, 0, -5], max: [-4, 3, -4] },
};

function run(state, input, level, frames) {
  let s = state;
  for (let f = 0; f < frames; f++) s = step(s, input, level, f);
  return s;
}

test("boxes overlap only when they share volume", () => {
  const a = { min: [0, 0, 0], max: [2, 2, 2] };
  assert.equal(overlaps(a, { min: [1, 1, 1], max: [3, 3, 3] }), true);
  assert.equal(overlaps(a, { min: [3, 0, 0], max: [4, 2, 2] }), false);
  assert.equal(overlaps(a, { min: [2, 0, 0], max: [4, 2, 2] }), false, "touching faces do not count");
});

test("the player box sits on top of pos", () => {
  const box = playerBox([1, 2, 3]);
  assert.equal(box.min[1], 2);
  assert.ok(box.max[1] > 2);
  assert.ok(box.min[0] < 1 && box.max[0] > 1);
});

test("falling onto a platform lands exactly on its top", () => {
  const start = { ...createState(room), pos: [0, 2, 0], grounded: false, airFrames: 1 };
  const s = run(start, NO_INPUT, room, 60);
  assert.equal(s.pos[1], 0);
  assert.equal(s.grounded, true);
  assert.equal(s.vel[1], 0);
});

test("a wall stops sideways movement", () => {
  const s = run(createState(room), { x: 1, z: 0, jump: false }, room, 90);
  const box = playerBox(s.pos);
  assert.ok(box.max[0] <= 3 + 1e-9, `player went through the wall, max x ${box.max[0]}`);
  assert.ok(s.pos[0] > 1, "player should have walked up to the wall");
});

test("step never changes the state it is given", () => {
  const before = createState(room);
  const copy = structuredClone(before);
  step(before, { x: 1, z: 1, jump: true }, room, 0);
  assert.deepEqual(before, copy);
});

test("walking through a coin picks it up once", () => {
  const start = createState(room);
  const first = step(start, NO_INPUT, room, 0);
  assert.deepEqual(first.coins, [0]);
  const second = step(first, NO_INPUT, room, 1);
  assert.deepEqual(second.coins, [0]);
});

test("a coin out of reach stays", () => {
  const s = run(createState(room), NO_INPUT, room, 30);
  assert.deepEqual(s.coins, [0]);
});

test("falling below the kill plane respawns at the spawn point", () => {
  const level = { ...room, platforms: [] };
  const start = { ...createState(level), pos: [3, -9.99, 1], vel: [0, -5, 0], grounded: false, airFrames: 9, coins: [0] };
  const s = step(start, NO_INPUT, level, 0);
  assert.deepEqual(s.pos, level.spawn);
  assert.equal(s.deaths, 1);
  assert.deepEqual(s.coins, [0], "coins survive a respawn");
});
