# Hopper

A tiny 3D platformer, written as plain ES modules with no Node or DOM calls, so the same code runs in `node --test` and in a browser tab. It is the demo repo for Noether: `base/` is the game before a pull request, `head/` is the game after it, and `change.json` is the pull request text.

The level is one run of about 85 units along +x: a few steps up and down, a ferry that carries you over a pit, five coins, and one long gap at the end that needs a full speed jump. A recorded run (the ghost) beats it on `base`. On `head` the same inputs fall into the long gap, and the repo's own tests still pass.

## What the pull request says, and what it does

The text announces two things: coyote time 4 -> 6 frames, and terminal fall speed 18 -> 22. It also says there are no other behaviour changes. The diff also moves the movement code out of `step()` into `integrate()`, and in the move the ground check around friction got dropped, so friction now slows you in the air as well. Speed melts away mid-jump and the long gap can no longer be cleared. `node tools/check.mjs` prints all of this with numbers.

## Controls on the web

| Key | Input |
| --- | --- |
| D or Right arrow | `x: 1` (run along the level) |
| A or Left arrow | `x: -1` |
| W or Up arrow | `z: -1` (away from a camera that sits at +z) |
| S or Down arrow | `z: 1` |
| Space | `jump: true` while held |

Hold a direction to run, tap Space to jump, tap it a little early and the jump still comes out (jump buffer), and you can still jump for a few frames after running off a ledge (coyote time).

## API

Everything is exported from `src/index.js`.

World: x runs along the level, y is up, z is sideways, one unit is about a metre. The step is fixed at `DT = 1 / 60`; a renderer should keep a time accumulator and call `step` once per `DT`, drawing the latest state (or blending the last two).

```js
import { LEVEL, boxAt, createState, step, simulate, GHOST, expand } from "./src/index.js";
```

`LEVEL` has `spawn`, `killY`, `platforms`, `coins` and `goal`. Platforms and the goal are boxes `{ id, min: [x, y, z], max: [x, y, z] }`. Coins are points `[x, y, z]`. The ferry has a `move` field and slides on a triangle wave of the frame number, so draw it with `boxAt(platform, frame)`, which returns the box at that frame (fixed platforms come back unchanged).

`step(state, input, level, frame)` returns the next state and never changes its arguments. `frame` is the time of the state you pass in, starting at 0. `input` is `{ x, z, jump }`: `x` and `z` from -1 to 1, `jump` true while the button is down.

```js
let state = createState(LEVEL);
for (let frame = 0; ; frame++) state = step(state, readKeys(), LEVEL, frame);
```

The state is `{ pos, vel, grounded, airFrames, buffer, jumpHeld, standingOn, coins, deaths }`. `pos` is the middle of the player's feet (the box is 0.8 wide and 1.6 tall), `coins` lists the indexes of picked up coins, and `deaths` goes up each time the player falls under `killY` and is put back at the spawn. `touchesGoal(state, LEVEL)` tells you when the run is won.

`simulate(level, inputs, opts)` plays a list of per-frame inputs and returns the whole run for replaying or drawing:

```js
{
  frames: [{ f, pos: [x, y, z], vel: [x, y, z], grounded, coins }],  // frames[k] is the world at time k
  reachedGoal, goalFrame,  // goalFrame is an index into frames, or null
  coins,                   // coins picked up in total
  fellAtFrame,             // frames[fellAtFrame] is the respawn, or null
}
```

It stops at the goal and, by default, at the first fall. Options: `stopOnFall` (default true), `extraFrames` (keep going with no input after the inputs run out, so a failed run can finish falling), `maxFrames`.

`GHOST` is the recorded run as segments `[frames, moveX, moveZ, jump]`, and `expand(GHOST)` turns it into one input per frame for `simulate`. It is 671 frames, about 11 seconds.

## Checks

```
cd base && npm test
cd head && npm test
node tools/check.mjs
```

`tools/check.mjs` is the one that matters: it runs the ghost on base, on head, and on head with just the slipped line restored, and fails if any claimed fact stops being true. `tools/build-ghost.mjs` is how the ghost was made (a scripted route tuned by simulation); `--write` rewrites `src/ghost.js` in both folders. Neither is meant for the browser.

## Notes

No `Math.random`, no `Date`, no `Math.sin`: the moving platform is a triangle wave and everything else is plus, minus, times, divide and square root, which every engine rounds the same way, so a run replays identically everywhere.
