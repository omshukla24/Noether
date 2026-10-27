// Copies the Hopper game from fixtures/hopper into web/src/hopper so the site runs
// the exact code Noether checked. Three builds come out:
//   base   the game before the pull request
//   head   the game after it (the silent break)
//   fixed  head with the fix from the sealed run applied, the one the sandbox re-proved
// It also writes pr.json: the pull request text and its diff, for the PR card.
//
//   node scripts/sync-hopper.mjs          write the copies
//   node scripts/sync-hopper.mjs --check  exit 1 if the copies are out of date
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURE = join(WEB, "..", "fixtures", "hopper");
const OUT = join(WEB, "src", "hopper");
const BUNDLE = join(WEB, "public", "runs", "hopper.json");
const CHECK = process.argv.includes("--check");

/** Apply a unified diff to a text; every context and removed line must match. */
function applyUnifiedDiff(text, diff) {
  const lines = text.split("\n");
  const hunks = [...diff.matchAll(/^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@.*\n((?:[ +\-\\].*(?:\n|$))*)/gm)];
  if (!hunks.length) throw new Error("fix diff has no hunks");
  let shift = 0;
  for (const [, start, body] of hunks) {
    let at = Number(start) - 1 + shift;
    const out = [];
    let removed = 0;
    for (const raw of body.split("\n")) {
      if (raw === "" || raw.startsWith("\\")) continue;
      const mark = raw[0];
      const line = raw.slice(1);
      if (mark === "+") {
        out.push(line);
        continue;
      }
      if (lines[at + removed] !== line) {
        throw new Error(`fix diff does not match line ${at + removed + 1}: ${JSON.stringify(line)}`);
      }
      if (mark === " ") out.push(line);
      removed++;
    }
    lines.splice(at, removed, ...out);
    shift += out.length - removed;
  }
  return lines.join("\n");
}

function sources(version) {
  const dir = join(FIXTURE, version, "src");
  return Object.fromEntries(
    readdirSync(dir)
      .filter((f) => f.endsWith(".js"))
      .map((f) => [f, readFileSync(join(dir, f), "utf8")]),
  );
}

function provedFix(bundle) {
  const fixes = bundle.breaks.map((b) => b.fix).filter((f) => f && f.proved);
  if (fixes.length !== 1) throw new Error(`expected one proved fix in the bundle, found ${fixes.length}`);
  return fixes[0];
}

function prDiff() {
  // git prints the diff with a/ b/ prefixes; keep the paths the repo uses
  const run = spawnSync(
    "git",
    ["diff", "--no-index", "--no-color", "-U3", "base", "head"],
    { encoding: "utf8", cwd: FIXTURE },
  );
  if (run.status !== 1) throw new Error(`git diff failed: ${run.stderr}`);
  const files = [];
  for (const chunk of run.stdout.split(/^diff --git .*\n/m).slice(1)) {
    const path = chunk.match(/^\+\+\+ b\/head\/(.+)$/m)?.[1];
    const body = chunk.slice(chunk.indexOf("@@"));
    const added = body.split("\n").filter((l) => l.startsWith("+")).length;
    const removed = body.split("\n").filter((l) => l.startsWith("-")).length;
    files.push({ path, added, removed, hunks: body.trimEnd() });
  }
  return files;
}

function build() {
  const bundle = JSON.parse(readFileSync(BUNDLE, "utf8"));
  const fix = provedFix(bundle);
  const base = sources("base");
  const head = sources("head");
  const fixed = { ...head, [fix.file.replace(/^src\//, "")]: applyUnifiedDiff(head[fix.file.replace(/^src\//, "")], fix.diff) };
  const change = JSON.parse(readFileSync(join(FIXTURE, "change.json"), "utf8"));
  const pr = { title: change.title, body: change.body, files: prDiff() };
  return { base, head, fixed, pr: `${JSON.stringify(pr, null, 2)}\n`, runId: bundle.run_id };
}

const out = build();
let stale = 0;
const write = (path, text) => {
  if (CHECK) {
    if (!existsSync(path) || readFileSync(path, "utf8") !== text) {
      console.log(`stale: ${path}`);
      stale++;
    }
    return;
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
};
for (const version of ["base", "head", "fixed"]) {
  for (const [file, text] of Object.entries(out[version])) write(join(OUT, version, file), text);
}
write(join(OUT, "pr.json"), out.pr);
if (CHECK && stale) process.exit(1);
console.log(CHECK ? "hopper copies are current" : `hopper synced (fix from run ${out.runId})`);
