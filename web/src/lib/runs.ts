// Sealed runs that ship with the site: every JSON file in public/runs. Read at build time only.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Bundle } from "./bundle";

const DIR = join(process.cwd(), "public", "runs");

// The id of a run made by the API, as the pipeline names it.
export const LIVE_RUN_ID = /^\d{8}-\d{6}-[0-9a-f]{6}$/;

export function listRunIds(): string[] {
  const ids = readdirSync(DIR).filter((f) => f.endsWith(".json")).map((f) => f.slice(0, -".json".length));
  return ids.sort((a, b) => (a === "hopper" ? -1 : b === "hopper" ? 1 : a < b ? -1 : 1));
}

/** Only names that exist in the folder are ever opened, so an id from a URL cannot reach another path. */
export function loadRun(id: string): Bundle | null {
  if (!listRunIds().includes(id)) return null;
  return JSON.parse(readFileSync(join(DIR, `${id}.json`), "utf8")) as Bundle;
}
