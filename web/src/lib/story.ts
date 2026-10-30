// Pure helpers the story sections share: reading a unified diff, matching changed
// lines to what the pull request announced, slicing source around a line.
// Relative imports only, so vitest can load this without the app's path alias.
import pr from "../hopper/pr.json";

export type DiffKind = "hunk" | "ctx" | "add" | "del";

export interface DiffLine {
  kind: DiffKind;
  text: string;
  oldNo: number | null;
  newNo: number | null;
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$/;

/** Reads the hunks of a unified diff into numbered lines. File headers before the first hunk are skipped. */
export function parseDiff(diff: string): DiffLine[] {
  const out: DiffLine[] = [];
  let oldNo = 0;
  let newNo = 0;
  let inHunk = false;
  const rows = diff.split("\n");
  if (rows[rows.length - 1] === "") rows.pop();
  for (const row of rows) {
    const hunk = HUNK.exec(row);
    if (hunk) {
      oldNo = Number(hunk[1]);
      newNo = Number(hunk[2]);
      inHunk = true;
      out.push({ kind: "hunk", text: hunk[3], oldNo: null, newNo: null });
      continue;
    }
    if (!inHunk || row.startsWith("\\")) continue;
    const mark = row[0];
    const text = row.slice(1);
    if (mark === "+") out.push({ kind: "add", text, oldNo: null, newNo: newNo++ });
    else if (mark === "-") out.push({ kind: "del", text, oldNo: oldNo++, newNo: null });
    else out.push({ kind: "ctx", text, oldNo: oldNo++, newNo: newNo++ });
  }
  return out;
}

export interface Announcement {
  /** the number or value change shown in the margin, e.g. "4 → 6" */
  change: string;
}

const CONSTANT = /^\s*export const ([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\s*=/;
const VALUE = /=\s*(-?\d+(?:\.\d+)?)/;

/**
 * Changed constant declarations the pull request said it was changing: the name's first word
 * ("COYOTE_FRAMES" -> "coyote") appears in what Nano read as the intent. Keyed by line index.
 * The added line carries the margin note; its removed twin is underlined without one.
 */
export function announcedLines(lines: DiffLine[], intended: string[]): Map<number, Announcement | null> {
  const said = intended.join(" ").toLowerCase();
  const marks = new Map<number, Announcement | null>();
  lines.forEach((line, i) => {
    if (line.kind !== "add") return;
    const id = CONSTANT.exec(line.text)?.[1];
    if (!id || !said.includes(id.split("_")[0].toLowerCase())) return;
    const twin = lines.findIndex((l, j) => l.kind === "del" && j < i && i - j <= 3 && l.text.includes(id));
    const was = twin >= 0 ? VALUE.exec(lines[twin].text)?.[1] : undefined;
    const now = VALUE.exec(line.text)?.[1];
    if (twin >= 0) marks.set(twin, null);
    marks.set(i, { change: was && now ? `${was} → ${now}` : "" });
  });
  return marks;
}

export interface SourceLine {
  no: number;
  text: string;
}

/** `radius` lines either side of 1-based `line`, clamped to the file. */
export function sliceAround(source: string, line: number, radius: number): SourceLine[] {
  const rows = source.split("\n");
  const from = Math.max(1, line - radius);
  const to = Math.min(rows.length, line + radius);
  return rows.slice(from - 1, to).map((text, i) => ({ no: from + i, text }));
}

/** The assertion message of a failed pinned check, without the stack. */
export function failureLine(output: string): string {
  // A test file that died on its first assertion: node's own crash report, with the message after the last marker.
  const crash = output.includes("node printed:") ? output.slice(output.lastIndexOf("AssertionError [ERR_ASSERTION]: ") + 32).split("\n    at ")[0] : null;
  if (crash) return crash.replace(/\s+/g, " ").trim();
  const body = output.replace(/^\[Error \[[A-Z_]+\]: /, "").split("\n] {")[0];
  return body.replace(/\s+/g, " ").trim();
}

export const prFile = pr.files[0];
export const prDiff = parseDiff(prFile.hunks);
export const prCounts = {
  added: prDiff.filter((l) => l.kind === "add").length,
  removed: prDiff.filter((l) => l.kind === "del").length,
};
