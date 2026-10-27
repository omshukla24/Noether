import { describe, expect, it } from "vitest";
import hopper from "../../public/runs/hopper.json";
import type { Bundle } from "./bundle";
import { collapseLines, droppedLines, headLineState, sealProgress, tally, threadProgress } from "./collapse";

const run = hopper as unknown as Bundle;
const lines = collapseLines(run);

describe("the lines", () => {
  it("has one line per pinned invariant, in plate order, none overlapping", () => {
    expect(lines).toHaveLength(run.invariants.filter((i) => i.kind !== "dropped").length);
    for (let i = 1; i < lines.length; i++) expect(lines[i].pos - lines[i - 1].pos).toBeGreaterThan(0.04);
    expect(lines.every((l) => l.pos > 0.05 && l.pos < 0.95)).toBe(true);
  });

  it("puts the faint dropped checks between pinned lines, one per dropped check", () => {
    const dropped = droppedLines(run, lines);
    expect(dropped.map((d) => d.name)).toEqual(run.dropped.map((d) => d.name));
    expect(dropped.every((d) => d.reason === "red on base")).toBe(true);
    expect(lines.some((l) => dropped.some((d) => Math.abs(d.pos - l.pos) < 0.02))).toBe(false);
  });
});

describe("scroll progress", () => {
  const held = lines.find((l) => l.kind === "held")!;
  const silent = lines.find((l) => l.kind === "silent")!;

  it("starts scattered and ends locked onto the twin for a held line", () => {
    const first = headLineState(held, 0, lines.length);
    expect(Math.abs(first.dx)).toBeGreaterThan(0.03);
    expect(first.lock).toBe(0);
    const end = headLineState(held, 1, lines.length);
    expect([Math.abs(end.dx), end.dy, end.lock, end.tear]).toEqual([0, 0, 1, 0]);
  });

  it("never locks the silent line; it aligns, then tears and falls", () => {
    const before = headLineState(silent, 0.58, lines.length);
    expect(before.lock).toBe(0);
    expect(before.tear).toBe(0);
    const after = headLineState(silent, 1, lines.length);
    expect(after.tear).toBe(1);
    expect(after.dy).toBeGreaterThan(0.05);
    expect(after.lock).toBe(0);
  });

  it("counts every held line locked and one torn at the end", () => {
    expect(tally(lines, 0)).toEqual({ locked: 0, torn: 0 });
    expect(tally(lines, 1)).toEqual({ locked: lines.length - 1, torn: 1 });
  });

  it("draws the thread after the tear and sets the seal last", () => {
    expect(threadProgress(0.6)).toBe(0);
    expect(threadProgress(1)).toBe(1);
    expect(sealProgress(0.9)).toBe(0);
    expect(sealProgress(1)).toBe(1);
  });
});
