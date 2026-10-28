import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Bundle } from "./bundle";
import { commentMarkdown, commentOf } from "./comment";

const WEB = join(__dirname, "..", "..");
const RUNS = join(WEB, "public", "runs");
const URL = "https://github.com/omshukla24/hopper/actions/runs/1";
const hasPython = spawnSync("python", ["--version"]).status === 0;

// comment.py (the vendored copy the deployed API imports) renders the same bundle; the two must agree to the byte.
function pythonComment(file: string): string {
  const script =
    "import json, sys; sys.path.insert(0, sys.argv[1]); from noether.comment import render_markdown; " +
    "sys.stdout.buffer.write(render_markdown(json.load(open(sys.argv[2], encoding='utf-8')), sys.argv[3]).encode())";
  // bytes, not text: text-mode stdout on Windows would turn every \n into \r\n
  const run = spawnSync("python", ["-I", "-c", script, join(WEB, "py"), file, URL], { encoding: "utf8" });
  expect(run.stderr).toBe("");
  return run.stdout;
}

describe("PR comment", () => {
  const bundles = readdirSync(RUNS).filter((n) => n.endsWith(".json"));

  it.skipIf(!hasPython).each(bundles)("matches comment.py for %s", (name) => {
    const file = join(RUNS, name);
    const bundle = JSON.parse(readFileSync(file, "utf8")) as Bundle;
    expect(commentMarkdown(commentOf(bundle), URL)).toBe(pythonComment(file));
  });

  it("reads the sealed Hopper break", () => {
    const c = commentOf(JSON.parse(readFileSync(join(RUNS, "hopper.json"), "utf8")) as Bundle);
    expect(c.verdict).toBe("BROKEN");
    expect(c.breaks).toHaveLength(1);
    expect(c.breaks[0]).toMatchObject({ where: "src/physics.js:109", fix: "re-proved" });
    expect(c.breaks[0].diff).toMatch(/^--- a\/src\/physics\.js/);
    expect(c.seal).toHaveLength(16);
  });
});
