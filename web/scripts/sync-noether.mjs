// The Python function in web/api can only see files inside web/, but the noether package lives at
// the repository root. This copies it to web/py/noether so the deployed function can import it.
//
//   node scripts/sync-noether.mjs          write the copy
//   node scripts/sync-noether.mjs --check  exit 1 if the copy is out of date
import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(WEB, "..", "noether");
const OUT = join(WEB, "py", "noether");
const CHECK = process.argv.includes("--check");

const sources = readdirSync(SOURCE).filter((name) => name.endsWith(".py")).sort();
const stale = [];

for (const name of sources) {
  const want = readFileSync(join(SOURCE, name));
  const target = join(OUT, name);
  const have = existsSync(target) ? readFileSync(target) : null;
  if (have && have.equals(want)) continue;
  stale.push(name);
  if (!CHECK) {
    mkdirSync(OUT, { recursive: true });
    writeFileSync(target, want);
  }
}

if (existsSync(OUT)) {
  for (const name of readdirSync(OUT).filter((n) => n.endsWith(".py") && !sources.includes(n))) {
    stale.push(name);
    if (!CHECK) rmSync(join(OUT, name));
  }
}

if (CHECK && stale.length) {
  console.error(`web/py/noether is out of date (${stale.join(", ")}). Run: npm run sync:noether`);
  process.exit(1);
}
console.log(stale.length ? `synced ${stale.length} file(s) into web/py/noether` : "web/py/noether is up to date");
