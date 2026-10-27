// "The Gap": the Hopper level you can play, with the recorded run replayed on
// base (indigo) and head (vermilion) beside you. One world clock drives the
// ferry, the ghosts and the player, so everyone rides the same platform.
// init(canvas) -> controller with dispose(), like every motion module here.
import * as THREE from "three";
import { gsap } from "gsap";
import type { Line2 } from "three/examples/jsm/lines/Line2.js";
import type { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { GAMES, GAP, LEVEL, DT, ghostRun, momentum, type Build, type GhostRun, type Input, type State } from "@/hopper/sim";
import { HOPPER_VIEW, PERF } from "@/motion/config.js";
import { clamp, damp, lerp } from "@/motion/math.js";
import { buildWorld, trailLine, type Palette } from "./world";

export interface GhostHud {
  x: number;
  p: number;
  state: "running" | "cleared" | "fell";
}

export interface PlayerHud {
  build: Build;
  x: number;
  p: number;
  airborne: boolean;
  /** momentum change since the last takeoff, null before the first jump */
  jumpChange: number | null;
  tries: Record<Build, number>;
  cleared: Record<Build, number>;
  touched: boolean;
}

export interface Hud {
  frame: number;
  total: number;
  base: GhostHud;
  head: GhostHud;
  player: PlayerHud;
}

export type PlayerEvent = "fell" | "cleared" | "goal";

export interface HopperLabels {
  base: HTMLElement;
  head: HTMLElement;
  you: HTMLElement;
  gap: HTMLElement;
  baseMark: HTMLElement;
  headMark: HTMLElement;
}

export interface HopperOptions {
  palette: Palette;
  reduced: boolean;
  labels: HopperLabels;
  onHud: (hud: Hud) => void;
  onEvent?: (event: PlayerEvent, build: Build) => void;
  /** which two builds the recorded run is replayed on, in label order; the hero shows base and head */
  ghosts?: [Build, Build];
  /** the build the player starts on */
  build?: Build;
  /** world units the dive frame looks higher, which moves the gap lower on screen to make room for copy above it */
  diveShift?: number;
}

export interface HopperScene {
  setBuild: (build: Build) => void;
  setInput: (input: Input) => void;
  setPlaying: (on: boolean) => void;
  /** 0 = following the run, 1 = frozen on the gap */
  setDive: (t: number) => void;
  replay: () => void;
  setActive: (on: boolean) => void;
  dispose: () => void;
}

const IDLE: Input = { x: 0, z: 0, jump: false };
const LEAD_IN = -40; // frames the ghosts hold at the spawn before they run
const CAMERA_LAMBDA = -Math.log(1 - HOPPER_VIEW.cameraLerp) * 60;
const FOLLOW = { ahead: 4, y: 4.2, offset: new THREE.Vector3(-4, 10, 46) };
const DIVE = { target: new THREE.Vector3(76.6, 1.2, 0), position: new THREE.Vector3(71.2, 6.4, 24) };
// the two ghosts run the same inputs; a small sideways lane keeps both visible
const LANE: Record<"base" | "head", number> = { base: -0.55, head: 0.55 };

type Tag = "base" | "head";

interface Ghost {
  run: GhostRun;
  line: Line2;
  /** last frame index that belongs to the run (the frame before a respawn) */
  last: number;
  /** where the ghost is shown once the page dives to the gap */
  freeze: number;
}

// a build that breaks the jump is drawn in vermilion and dashed; the others in indigo
const tintOf = (build: Build, palette: Palette) => (build === "head" ? palette.broken : palette.accent);

function makeGhost(tag: Tag, build: Build, palette: Palette): Ghost {
  const run = ghostRun(build);
  const last = (run.fellAtFrame ?? run.frames.length) - 1;
  const pts: number[] = [];
  for (let i = 0; i <= last; i++) {
    const f = run.frames[i];
    pts.push(f.pos[0], f.pos[1] + 0.8, f.pos[2] + LANE[tag]);
  }
  const line = trailLine(pts, tintOf(build, palette), build === "head");
  const down = run.jump?.downFrame ?? last;
  return { run, line, last, freeze: Math.min(last, down + (build === "head" ? 16 : 4)) };
}

function squashScale(vy: number, impulse: number): number {
  return 1 + clamp(vy * 0.012, -HOPPER_VIEW.squash, HOPPER_VIEW.squash) + impulse;
}

export function createHopperScene(canvas: HTMLCanvasElement, opts: HopperOptions): HopperScene {
  const { palette, reduced, labels } = opts;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  let dpr = Math.min(window.devicePixelRatio || 1, PERF.dprMax);
  renderer.setPixelRatio(dpr);

  const [first, second] = opts.ghosts ?? (["base", "head"] as [Build, Build]);
  const world = buildWorld(palette, { base: tintOf(first, palette), head: tintOf(second, palette) });
  const camera = new THREE.PerspectiveCamera(HOPPER_VIEW.fov, 1, 0.5, 260);
  const ghosts: Record<Tag, Ghost> = { base: makeGhost("base", first, palette), head: makeGhost("head", second, palette) };
  // the camera follows whichever recorded run keeps going longest
  const leader = ghosts.base.last >= ghosts.head.last ? ghosts.base : ghosts.head;
  world.scene.add(ghosts.base.line, ghosts.head.line);
  const total = Math.max(ghosts.base.last, ghosts.head.last);

  // the measured bracket over the gap, and a tick where each build comes down
  const jumpB = ghosts.base.run.jump!;
  const jumpH = ghosts.head.run.jump!;
  const bracketY = GAP.top + 3.2;
  const measures = [
    trailLine([GAP.from, bracketY, 0, GAP.to, bracketY, 0], palette.ink, false),
    trailLine([GAP.from, bracketY - 0.4, 0, GAP.from, bracketY + 0.4, 0], palette.ink, false),
    trailLine([GAP.to, bracketY - 0.4, 0, GAP.to, bracketY + 0.4, 0], palette.ink, false),
    trailLine([jumpB.reach, GAP.top, 0.2, jumpB.reach, GAP.top + 1.6, 0.2], tintOf(first, palette), false),
    trailLine([jumpH.reach, GAP.top, 0.2, jumpH.reach, GAP.top + 1.6, 0.2], tintOf(second, palette), false),
  ];
  measures.forEach((m) => world.measure.add(m));
  const lines = [ghosts.base.line, ghosts.head.line, ...measures];

  // world clock and the player
  let t = LEAD_IN;
  let acc = 0;
  let build: Build = opts.build ?? "head";
  let input: Input = IDLE;
  let playing = false;
  let dive = 0;
  let active = false;
  let state: State = GAMES[build].createState(LEVEL);
  let prev: State = state;
  let touched = false;
  let attemptCleared = false;
  let jumpP0: number | null = null;
  let jumpChange: number | null = null;
  let landImpulse = 0;
  const tries: Record<Build, number> = { base: 0, head: 0, fixed: 0 };
  const cleared: Record<Build, number> = { base: 0, head: 0, fixed: 0 };

  const camPos = new THREE.Vector3();
  const camTarget = new THREE.Vector3();
  const wantPos = new THREE.Vector3();
  const wantTarget = new THREE.Vector3();
  const tmp = new THREE.Vector3();
  let width = 1;
  let height = 1;

  function resetPlayer() {
    state = GAMES[build].createState(LEVEL);
    prev = state;
    attemptCleared = false;
    jumpP0 = null;
    jumpChange = null;
  }

  function stepPlayer() {
    const before = state;
    const next = GAMES[build].step(before, playing ? input : IDLE, LEVEL, Math.max(0, t));
    prev = before;
    state = next;
    if (playing && (input.x || input.z || input.jump)) touched = true;
    if (before.grounded && !next.grounded) jumpP0 = momentum(next.vel);
    if (!next.grounded && jumpP0) jumpChange = (momentum(next.vel) - jumpP0) / jumpP0;
    if (!before.grounded && next.grounded) landImpulse = -0.16;
    if (next.deaths > before.deaths) {
      tries[build] += 1;
      attemptCleared = false;
      prev = state;
      opts.onEvent?.("fell", build);
    } else if (next.standingOn === "s7" && !attemptCleared) {
      attemptCleared = true;
      cleared[build] += 1;
      opts.onEvent?.("cleared", build);
    }
    if (GAMES[build].touchesGoal(state, LEVEL)) {
      tries[build] += 1;
      opts.onEvent?.("goal", build);
      resetPlayer();
    }
  }

  function placeBody(group: THREE.Object3D, a: readonly number[], b: readonly number[], alpha: number, vy: number, impulse = 0) {
    group.position.set(lerp(a[0], b[0], alpha), lerp(a[1], b[1], alpha), lerp(a[2], b[2], alpha));
    const sy = squashScale(vy, impulse);
    group.scale.set(1 / Math.sqrt(sy), sy, 1 / Math.sqrt(sy));
  }

  function ghostIndex(g: Ghost): number {
    if (dive > 0.02) return g.freeze;
    return clamp(t, 0, g.last);
  }

  function drawGhost(tag: Tag, alpha: number): GhostHud {
    const g = ghosts[tag];
    const i = ghostIndex(g);
    const frozen = dive > 0.02 || t >= g.last || t <= 0;
    const a = g.run.frames[i];
    const b = g.run.frames[Math.min(i + 1, g.last)];
    const fell = g.run.fellAtFrame !== null && t >= g.last && dive <= 0.02;
    const body = world.ghosts[tag].group;
    body.visible = !fell;
    placeBody(body, a.pos, frozen ? a.pos : b.pos, frozen ? 0 : alpha, a.vel[1]);
    body.position.z += LANE[tag];
    const geo = g.line.geometry as unknown as { instanceCount: number };
    geo.instanceCount = Math.max(0, i);
    if (g.run.build === "head") {
      const end = g.run.frames[g.last];
      world.impact.visible = fell || (dive > 0.02 && g.run.fellAtFrame !== null);
      world.impact.position.set(end.pos[0], LEVEL.killY + 0.02, end.pos[2] + LANE[tag]);
    }
    return { x: a.pos[0], p: momentum(a.vel), state: fell ? "fell" : g.run.reachedGoal && i >= g.last ? "cleared" : "running" };
  }

  function placeLabel(el: HTMLElement, x: number, y: number, z: number, show: boolean) {
    if (!show) {
      el.style.opacity = "0";
      return;
    }
    tmp.set(x, y, z).project(camera);
    const visible = tmp.z < 1 && Math.abs(tmp.x) < 1.1 && Math.abs(tmp.y) < 1.1;
    el.style.opacity = visible ? "1" : "0";
    el.style.transform = `translate3d(${((tmp.x + 1) / 2) * width}px, ${((1 - tmp.y) / 2) * height}px, 0)`;
  }

  function aimCamera(dt: number, snap: boolean) {
    const ghostLead = t > 0 && t < total ? leader.run.frames[clamp(t, 0, leader.last)].pos[0] - 1.5 : null;
    const focusX = touched || ghostLead === null ? state.pos[0] : ghostLead;
    const fit = clamp(1.25 / (width / height), 1, 1.9); // narrow screens step back
    wantTarget.set(focusX + FOLLOW.ahead, FOLLOW.y, 0.5);
    wantPos.copy(wantTarget).addScaledVector(FOLLOW.offset, fit);
    const shift = opts.diveShift ?? 0;
    const diveTarget = tmp.copy(DIVE.target);
    diveTarget.y += shift;
    wantTarget.lerp(diveTarget, dive);
    const divePos = DIVE.position.clone().sub(DIVE.target).multiplyScalar(fit).add(DIVE.target);
    divePos.y += shift;
    wantPos.lerp(divePos, dive);
    if (snap) {
      camPos.copy(wantPos);
      camTarget.copy(wantTarget);
    } else {
      const k = 1 - Math.exp(-CAMERA_LAMBDA * dt);
      camPos.lerp(wantPos, k);
      camTarget.lerp(wantTarget, k);
    }
    camera.position.copy(camPos);
    camera.lookAt(camTarget);
    world.sun.position.set(camTarget.x - 18, 34, 26);
    world.sun.target.position.copy(camTarget);
  }

  let hudTick = 0;
  function draw(dt: number, snap = false) {
    const alpha = reduced ? 0 : clamp(acc / DT, 0, 1);
    landImpulse = damp(landImpulse, 0, 14, dt);
    const ferryBox = LEVEL.platforms.find((p) => p.move)!;
    const ferryNow = GAMES.base.boxAt(ferryBox, Math.max(0, t));
    world.ferry.position.x = (ferryNow.min[0] + ferryNow.max[0]) / 2;

    const showPlayer = dive < 0.05 && !reduced;
    world.player.group.visible = showPlayer;
    placeBody(world.player.group, prev.pos, state.pos, alpha, state.vel[1], landImpulse);
    world.coins.forEach((c, i) => {
      c.visible = !(showPlayer && state.coins.includes(i));
    });

    const base = drawGhost("base", alpha);
    const head = drawGhost("head", alpha);
    world.measure.visible = dive > 0.02;
    aimCamera(dt, snap);
    renderer.render(world.scene, camera);

    const gb = world.ghosts.base.group.position;
    const gh = world.ghosts.head.group.position;
    placeLabel(labels.base, gb.x, gb.y + 2.3, gb.z, world.ghosts.base.group.visible);
    placeLabel(labels.head, gh.x, gh.y + 2.3, gh.z, world.ghosts.head.group.visible && dive < 0.5);
    const yp = world.player.group.position;
    placeLabel(labels.you, yp.x, yp.y + 2.3, yp.z, showPlayer && touched);
    const showMeasure = dive > 0.6;
    placeLabel(labels.gap, (GAP.from + GAP.to) / 2, bracketY + 0.5, 0, showMeasure);
    placeLabel(labels.baseMark, jumpB.reach, GAP.top + 1.9, 0.2, showMeasure);
    placeLabel(labels.headMark, jumpH.reach, GAP.top + 1.9, 0.2, showMeasure);

    if (snap || ++hudTick % 4 === 0) {
      opts.onHud({
        frame: clamp(t, 0, total),
        total,
        base,
        head,
        player: {
          build,
          x: state.pos[0],
          p: momentum(state.vel),
          airborne: !state.grounded,
          jumpChange,
          tries: { ...tries },
          cleared: { ...cleared },
          touched,
        },
      });
    }
  }

  // frame-time watch: drop the pixel ratio once if the device cannot keep up
  let sampleMs = 0;
  let samples = 0;
  function watchFrames(deltaMs: number) {
    if (dpr <= PERF.dprDegraded) return;
    sampleMs += deltaMs;
    samples += 1;
    if (samples < PERF.sampleFrames) return;
    if (sampleMs / samples > PERF.degradeFrameMs) {
      dpr = PERF.dprDegraded;
      renderer.setPixelRatio(dpr);
      resize();
    }
    sampleMs = 0;
    samples = 0;
  }

  function tick(_time: number, deltaMs: number) {
    const dt = Math.min(deltaMs / 1000, 0.1);
    watchFrames(deltaMs);
    if (dive <= 0.02) {
      acc += dt;
      while (acc >= DT) {
        acc -= DT;
        t += 1;
        stepPlayer();
      }
    }
    draw(dt);
  }

  function resize() {
    const box = canvas.parentElement ?? canvas;
    width = Math.max(1, box.clientWidth);
    height = Math.max(1, box.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    lines.forEach((l) => (l.material as LineMaterial).resolution.set(width, height));
    if (reduced || !active) draw(0, true);
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas.parentElement ?? canvas);

  if (reduced) {
    dive = 1;
    t = total;
  }
  resize();
  draw(0, true);

  return {
    setBuild(next) {
      if (next === build) return;
      build = next;
      resetPlayer();
      if (!active) draw(0, true);
    },
    setInput(next) {
      input = next;
    },
    setPlaying(on) {
      playing = on && !reduced;
      if (!playing) input = IDLE;
    },
    setDive(v) {
      dive = reduced ? 1 : clamp(v, 0, 1);
      if (!active) draw(0, true);
    },
    replay() {
      t = LEAD_IN;
      acc = 0;
      touched = false;
      resetPlayer();
      draw(0);
    },
    setActive(on) {
      if (on === active || reduced) return;
      active = on;
      if (on) gsap.ticker.add(tick);
      else gsap.ticker.remove(tick);
    },
    dispose() {
      gsap.ticker.remove(tick);
      ro.disconnect();
      lines.forEach((l) => {
        l.geometry.dispose();
        (l.material as LineMaterial).dispose();
      });
      world.dispose();
      renderer.dispose();
    },
  };
}
