import { describe, expect, it } from "vitest";
import { verifySeal } from "./bundle";
import { tokensByModel } from "./run";
import { LIVE_RUN_ID, listRunIds, loadRun } from "./runs";

describe("sealed runs shipped with the site", () => {
  it("lists hopper first and loads only names that exist", () => {
    const ids = listRunIds();
    expect(ids[0]).toBe("hopper");
    expect(ids).toContain("20261027-025352-edb700");
    expect(loadRun("../package")).toBeNull();
    expect(loadRun("hopper.json")).toBeNull();
  });

  it("verifies each seal in the same way the browser does, and notices a change", async () => {
    for (const id of listRunIds()) {
      const bundle = loadRun(id)!;
      expect(await verifySeal(bundle)).toBe(true);
      expect(await verifySeal({ ...bundle, reason: `${bundle.reason} ` })).toBe(false);
    }
  });

  it("groups the model calls by model", () => {
    const rows = tokensByModel(loadRun("hopper")!);
    expect(rows.map((r) => r.roles)).toEqual([["intent"], ["pin"], ["judge", "fix"]]);
    expect(rows.reduce((n, r) => n + r.calls, 0)).toBe(loadRun("hopper")!.models.length);
  });

  it("recognises the ids the API makes", () => {
    expect(LIVE_RUN_ID.test("20261027-120751-aaaaaa")).toBe(true);
    expect(LIVE_RUN_ID.test("hopper")).toBe(false);
    expect(LIVE_RUN_ID.test("20261027-120751-AAAAAA")).toBe(false);
  });
});
