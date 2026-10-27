import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { GAP, formatChange, ghostRun } from "./sim";

describe("hopper copies", () => {
  it("match the fixture and the sealed run's fix", () => {
    const run = spawnSync(process.execPath, ["scripts/sync-hopper.mjs", "--check"], { encoding: "utf8" });
    expect(run.stdout).toContain("current");
    expect(run.status).toBe(0);
  });
});

describe("the recorded run", () => {
  it("clears the long gap on base and conserves momentum in the air", () => {
    const run = ghostRun("base");
    expect(run.reachedGoal).toBe(true);
    expect(run.jump!.margin).toBeCloseTo(0.332, 3);
    expect(formatChange(run.jump!.pChange)).toBe("conserved");
  });

  it("falls short on head because momentum melts mid-air", () => {
    const run = ghostRun("head");
    expect(run.reachedGoal).toBe(false);
    expect(run.fellAtFrame).not.toBeNull();
    expect(run.jump!.margin).toBeCloseTo(-3.049, 3);
    expect(run.jump!.pChange).toBeLessThan(-0.1);
  });

  it("clears it again with the re-proved fix", () => {
    const fixed = ghostRun("fixed");
    expect(fixed.reachedGoal).toBe(true);
    expect(fixed.jump!.margin).toBeCloseTo(ghostRun("base").jump!.margin, 9);
  });

  it("measures the gap from the level", () => {
    expect(GAP.width).toBeCloseTo(8.15, 9);
  });
});
