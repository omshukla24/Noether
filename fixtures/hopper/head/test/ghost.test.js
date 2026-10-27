import { test } from "node:test";
import assert from "node:assert/strict";
import { expand } from "../src/ghost.js";
import { simulate } from "../src/replay.js";

test("expand turns segments into one input per frame", () => {
  const inputs = expand([[2, 1, 0, 0], [1, 0, -1, 1]]);
  assert.deepEqual(inputs, [
    { x: 1, z: 0, jump: false },
    { x: 1, z: 0, jump: false },
    { x: 0, z: -1, jump: true },
  ]);
});

test("expand rejects a segment with no frames", () => {
  assert.throws(() => expand([[0, 1, 0, 0]]), RangeError);
  assert.throws(() => expand([[1.5, 1, 0, 0]]), RangeError);
});

test("simulate starts at the spawn and records every frame", () => {
  const level = {
    spawn: [0, 0, 0],
    killY: -10,
    platforms: [{ id: "floor", min: [-5, -2, -5], max: [5, 0, 5] }],
    coins: [],
    goal: { id: "goal", min: [3, 0, -1], max: [4, 2, 1] },
  };
  const run = simulate(level, expand([[120, 1, 0, 0]]));
  assert.equal(run.frames[0].f, 0);
  assert.deepEqual(run.frames[0].pos, [0, 0, 0]);
  assert.equal(run.reachedGoal, true);
  assert.equal(run.goalFrame, run.frames.length - 1);
  assert.equal(run.fellAtFrame, null);
});

test("simulate reports the frame where the player drops off the world", () => {
  const level = {
    spawn: [0, 0, 0],
    killY: -10,
    platforms: [{ id: "floor", min: [-1, -2, -1], max: [1, 0, 1] }],
    coins: [],
    goal: { id: "goal", min: [50, 0, -1], max: [51, 2, 1] },
  };
  const run = simulate(level, expand([[300, 1, 0, 0]]));
  assert.equal(run.reachedGoal, false);
  assert.ok(run.fellAtFrame > 0);
  assert.equal(run.frames.length, run.fellAtFrame + 1);
});

test("extraFrames lets a run play out after the inputs end", () => {
  const level = {
    spawn: [0, 0, 0],
    killY: -10,
    platforms: [{ id: "floor", min: [-1, -2, -1], max: [1, 0, 1] }],
    coins: [],
    goal: { id: "goal", min: [50, 0, -1], max: [51, 2, 1] },
  };
  const inputs = expand([[30, 1, 0, 0]]);
  assert.equal(simulate(level, inputs).fellAtFrame, null);
  assert.ok(simulate(level, inputs, { extraFrames: 200 }).fellAtFrame > 30);
});

test("the same inputs always give the same run", () => {
  const level = {
    spawn: [0, 0, 0],
    killY: -10,
    platforms: [{ id: "floor", min: [-5, -2, -5], max: [5, 0, 5] }],
    coins: [[1, 1, 0]],
    goal: { id: "goal", min: [40, 0, -1], max: [41, 2, 1] },
  };
  const inputs = expand([[30, 1, 0, 0], [1, 1, 1, 1], [40, 0, 1, 0]]);
  assert.deepEqual(simulate(level, inputs), simulate(level, inputs));
});
