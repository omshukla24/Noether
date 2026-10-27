import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The deployed function imports web/py/noether, a copy of the package at the repository root.
describe("vendored noether package", () => {
  it("matches the repository root (fix with: npm run sync:noether)", () => {
    const run = spawnSync(process.execPath, [join(__dirname, "sync-noether.mjs"), "--check"], { encoding: "utf8" });
    expect(run.stderr).toBe("");
    expect(run.status).toBe(0);
  });
});
