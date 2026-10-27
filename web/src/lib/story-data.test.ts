import { describe, expect, it } from "vitest";
import hopper from "../../public/runs/hopper.json";
import intended from "../../public/runs/20261027-025352-edb700.json";
import type { Bundle } from "./bundle";
import { darkroomPlates } from "./darkroom";
import { judgeCase } from "./judge";

const run = hopper as unknown as Bundle;
const other = intended as unknown as Bundle;

describe("darkroomPlates", () => {
  const { plates, seconds } = darkroomPlates(run);

  it("makes a plate per snapshot, base first, with the full id behind the short one", () => {
    expect(plates.map((p) => p.key)).toEqual(["base", "head", "fix"]);
    expect(plates[0].full.startsWith(plates[0].short)).toBe(true);
    expect(seconds).toBe(run.sandbox.seconds);
  });

  it("lists every candidate on base, with the dropped ones red on both runs", () => {
    const base = plates[0];
    expect(base.rows).toHaveLength(run.invariants.length + run.dropped.length);
    const red = base.rows.filter((r) => r.cells[2].text === "red on base");
    expect(red.map((r) => r.name).sort()).toEqual(run.dropped.map((d) => d.name).sort());
    expect(red.every((r) => r.cells[0].text === "fail" && r.cells[1].text === "fail")).toBe(true);
  });

  it("shows the one check that failed on head and the proved fix", () => {
    const failed = plates[1].rows.filter((r) => r.cells[1].text === "fail");
    expect(failed.map((r) => r.name)).toEqual([run.breaks[0].invariant]);
    expect(plates[2].rows[0].cells[2].text).toBe("proved");
  });
});

describe("judgeCase", () => {
  it("reads the silent ruling from the Hopper run and the intended one from the other", () => {
    const silent = judgeCase(run, "silent", "hopper.json")!;
    const announced = judgeCase(other, "intended", "20261027-025352-edb700.json")!;
    expect(silent.truth).toBe("silent");
    expect(silent.failure).toContain("0.0985 !== 0.1");
    expect(announced.truth).toBe("intended");
    expect(announced.failure).toContain("-22 !== -18");
    expect(announced.runId).not.toBe(silent.runId);
    expect(announced.reason).toContain("TERMINAL_SPEED");
  });

  it("returns nothing when the run has no such ruling", () => {
    expect(judgeCase(run, "intended", "hopper.json")).toBeNull();
  });
});
