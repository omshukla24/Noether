// Data and timing for "The Collapse": one line per pinned invariant, a head twin that
// drifts onto its base line (or tears away from it) as the page scrolls.
// Pure functions of scroll progress, so the set-piece can be tested without a browser.
import { COLLAPSE } from "../motion/config.js";
import type { Bundle } from "./bundle";

export interface CollapseLine {
  index: number;
  name: string;
  claim: string;
  kind: "held" | "intended" | "silent";
  base: string;
  head: string;
  /** the pinned check as written by Super, one statement per line */
  code: string;
  output: string;
  /** position along the plate, 0..1 */
  pos: number;
  /** where the head twin starts, in plate widths and heights off the base line */
  scatterX: number;
  scatterY: number;
}

export interface DroppedLine {
  name: string;
  /** short reason: the pipeline's own words up to the first colon */
  reason: string;
  pos: number;
}

export interface LineState {
  /** offsets of the head line from its base twin, in plate widths and heights */
  dx: number;
  dy: number;
  /** 0 = still spectral, 1 = locked onto the twin in indigo */
  lock: number;
  /** 0 = whole, 1 = torn (dashed, fallen, vermilion) */
  tear: number;
}

/** Stable 0..1 value from a name, so each line keeps its place between renders. */
function unit(name: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < name.length; i++) h = Math.imul(h ^ name.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10007) / 10007;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const between = ([a, b]: number[], x: number) => clamp01((x - a) / (b - a));
const settle = (t: number) => 1 - (1 - t) ** 3;
const snap = (t: number) => (t < 0.5 ? 8 * t ** 4 : 1 - 8 * (1 - t) ** 4);

/**
 * Line positions along the plate: evenly spread, nudged by the name so the spacing is irregular
 * like a real spectrum. It is an encoding of which check the line is, not a measurement of the program.
 */
function spread(names: string[], salt: number): number[] {
  const n = names.length;
  return names.map((name, i) => 0.07 + (0.86 * (i + 0.5 + 0.55 * (unit(name, salt) - 0.5))) / n);
}

export function collapseLines(bundle: Bundle): CollapseLine[] {
  const live = bundle.invariants.filter((i) => i.kind !== "dropped");
  const pos = spread(live.map((i) => i.name), 1);
  return live.map((inv, index) => {
    const sx = (unit(inv.name, 2) * 2 - 1) * COLLAPSE.scatterX;
    const sy = (unit(inv.name, 3) * 2 - 1) * COLLAPSE.scatterY;
    return {
      index,
      name: inv.name,
      claim: inv.claim,
      kind: inv.kind === "silent" ? "silent" : inv.kind === "intended" ? "intended" : "held",
      base: inv.base,
      head: inv.head ?? "pass",
      code: inv.test_code.replace(/;(?=import )/g, ";\n"),
      output: inv.output,
      pos: pos[index],
      // never start exactly on the twin, or the drift would have nothing to show
      scatterX: Math.abs(sx) < COLLAPSE.scatterX * 0.4 ? Math.sign(sx || 1) * COLLAPSE.scatterX * 0.4 : sx,
      scatterY: sy,
    };
  });
}

/** Dropped checks sit between the pinned lines, faint, on the base plate only. */
export function droppedLines(bundle: Bundle, pinned: CollapseLine[]): DroppedLine[] {
  const gaps = [0, ...pinned.map((l) => l.pos), 1];
  return bundle.dropped.map((d, i) => {
    const slot = Math.min(i * 2 + 1, gaps.length - 2);
    return {
      name: d.name,
      reason: d.reason.split(":")[0],
      pos: (gaps[slot] + gaps[slot + 1]) / 2,
    };
  });
}

export function headLineState(line: CollapseLine, p: number, count: number): LineState {
  const [d0, d1] = COLLAPSE.drift;
  const w = COLLAPSE.driftWindow;
  const start = d0 + ((d1 - d0 - w) * line.index) / Math.max(1, count - 1);
  const align = settle(clamp01((p - start) / w));
  const tear = line.kind === "silent" ? snap(between(COLLAPSE.tear, p)) : 0;
  return {
    dx: line.scatterX * (1 - align) - COLLAPSE.tearShift * tear,
    dy: line.scatterY * (1 - align) + COLLAPSE.tearDrop * tear,
    lock: line.kind === "silent" ? 0 : clamp01(align * 5 - 4),
    tear,
  };
}

export const threadProgress = (p: number) => settle(between(COLLAPSE.thread, p));
export const sealProgress = (p: number) => between(COLLAPSE.seal, p);

export function tally(lines: CollapseLine[], p: number) {
  const states = lines.map((l) => headLineState(l, p, lines.length));
  return {
    locked: states.filter((s) => s.lock >= 0.99).length,
    torn: states.filter((s) => s.tear >= 0.99).length,
  };
}
