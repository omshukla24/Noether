// The three Hopper builds side by side, and the measurements the site prints.
// Every number on the page about the jump comes from these functions running
// the copied game code, never from a hand-typed constant.
import * as base from "./base/index.js";
import * as head from "./head/index.js";
import * as fixed from "./fixed/index.js";

export type Build = "base" | "head" | "fixed";
export type Input = { x: number; z: number; jump: boolean };
export type Level = typeof base.LEVEL;
export type Platform = Level["platforms"][number];
export interface Box {
  min: number[];
  max: number[];
}

export interface State {
  pos: number[];
  vel: number[];
  grounded: boolean;
  airFrames: number;
  buffer: number;
  jumpHeld: boolean;
  standingOn: string | null;
  coins: number[];
  deaths: number;
}

export interface Frame {
  f: number;
  pos: number[];
  vel: number[];
  grounded: boolean;
  coins: number;
}

export interface Run {
  frames: Frame[];
  reachedGoal: boolean;
  goalFrame: number | null;
  coins: number;
  fellAtFrame: number | null;
}

/** The game's public API (fixtures/hopper/README.md); the three builds share it. */
export interface Game {
  LEVEL: Level;
  GHOST: number[][];
  createState: (level: Level) => State;
  step: (state: State, input: Input, level: Level, frame: number) => State;
  simulate: (level: Level, inputs: Input[], opts?: { stopOnFall?: boolean; extraFrames?: number; maxFrames?: number }) => Run;
  expand: (ghost: number[][]) => Input[];
  touchesGoal: (state: State, level: Level) => boolean;
  boxAt: (platform: Platform, frame: number) => Box;
}

export const GAMES: Record<Build, Game> = {
  base: base as unknown as Game,
  head: head as unknown as Game,
  fixed: fixed as unknown as Game,
};
export const LEVEL = base.LEVEL;
export const DT = base.DT;
export const PLAYER_HALF = base.PLAYER_HALF;

const NEAR = LEVEL.platforms.find((p) => p.id === "s6")!;
const FAR = LEVEL.platforms.find((p) => p.id === "s7")!;
export const GAP = { from: NEAR.max[0], to: FAR.min[0], width: FAR.min[0] - NEAR.max[0], top: FAR.max[1] };

/** Horizontal momentum per unit mass: the quantity a conserved translation symmetry keeps. */
export const momentum = (vel: readonly number[]) => Math.hypot(vel[0], vel[2]);

export interface LongJump {
  takeoffFrame: number;
  takeoffX: number;
  downFrame: number;
  /** front of the player's box on the frame it comes back down to the far platform's top */
  reach: number;
  margin: number;
  pTakeoff: number;
  pDown: number;
  /** relative change of momentum over the flight, 0 when conserved */
  pChange: number;
}

/** Same measurement as fixtures/hopper/tools/gap.mjs: the jump that leaves s6. */
export function longJump(frames: Frame[]): LongJump | null {
  const takeoff = frames.findIndex((f) => f.vel[1] > 0 && f.pos[0] >= NEAR.min[0]);
  if (takeoff < 0) return null;
  for (let k = takeoff + 1; k < frames.length; k++) {
    if (frames[k].pos[1] > FAR.max[1]) continue;
    const reach = frames[k].pos[0] + PLAYER_HALF;
    const pTakeoff = momentum(frames[takeoff].vel);
    const pDown = momentum(frames[k].vel);
    return {
      takeoffFrame: takeoff,
      takeoffX: frames[takeoff].pos[0],
      downFrame: k,
      reach,
      margin: reach - FAR.min[0],
      pTakeoff,
      pDown,
      pChange: pTakeoff ? (pDown - pTakeoff) / pTakeoff : 0,
    };
  }
  return null;
}

export interface GhostRun {
  build: Build;
  frames: Frame[];
  reachedGoal: boolean;
  goalFrame: number | null;
  fellAtFrame: number | null;
  coins: number;
  jump: LongJump | null;
}

const ghostCache = new Map<Build, GhostRun>();

/** The recorded run played on one build; a failed run keeps falling until it respawns. */
export function ghostRun(build: Build): GhostRun {
  const cached = ghostCache.get(build);
  if (cached) return cached;
  const game = GAMES[build];
  const run = game.simulate(game.LEVEL, game.expand(game.GHOST), { extraFrames: 120 });
  const result: GhostRun = { build, ...run, jump: longJump(run.frames) };
  ghostCache.set(build, result);
  return result;
}

/** Signed percent with one decimal, "conserved" inside half a percent. */
export function formatChange(change: number): string {
  if (Math.abs(change) < 0.005) return "conserved";
  const pct = (change * 100).toFixed(1);
  return `${change > 0 ? "+" : "−"}${pct.replace("-", "")} %`;
}
