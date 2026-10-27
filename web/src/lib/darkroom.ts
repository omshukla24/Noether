// What ran in each sandbox snapshot, read from a sealed bundle's timeline.
// Nothing here is measured again: every row is an event the pipeline recorded.
import type { Bundle, Stage, StageEvent } from "./bundle";
import { shortId, stageSpans } from "./run";

export type Tone = "ok" | "bad" | "mute";
export interface Cell {
  text: string;
  tone: Tone;
}
export interface PlateRow {
  name: string;
  cells: Cell[];
}
export interface PlateData {
  key: "base" | "head" | "fix";
  title: string;
  role: string;
  short: string;
  full: string;
  /** wall-clock seconds of the pipeline stage that used this snapshot */
  stageSeconds: number | null;
  columns: string[];
  rows: PlateRow[];
  notes: string[];
}

const verdict = (passed: unknown): Cell => ({ text: passed ? "pass" : "fail", tone: passed ? "ok" : "bad" });

function events(b: Bundle, stage: Stage, type: StageEvent["type"]) {
  return b.timeline.filter((e) => e.stage === stage && e.type === type);
}

const suiteNote = (label: string, s: Bundle["own_suite"]["base"]) =>
  s ? `the repo's own suite on ${label}: ${s.passed} passed, ${s.failed} failed` : `the repo's own suite did not run on ${label}`;

export function darkroomPlates(b: Bundle): { plates: PlateData[]; seconds: number } {
  const spans = new Map(stageSpans(b.timeline).map((s) => [s.stage, (s.endMs - s.startMs) / 1000]));
  const snap = (prefix: string) => b.sandbox.snapshots.find((s) => s.label.startsWith(prefix));
  const pinnedOnBase = new Set((events(b, "base", "done")[0]?.data.pinned as string[] | undefined) ?? []);
  const plates: PlateData[] = [];

  const baseImage = snap("base");
  if (baseImage) {
    const candidates = events(b, "pin", "progress").map((e) => String(e.data.name));
    const runs = events(b, "base", "progress");
    const result = (name: string, run: number) => runs.filter((e) => e.data.name === name && e.data.run === run).at(-1);
    plates.push({
      key: "base",
      title: "Base checkpoint",
      role: "the code before the pull request, run twice",
      short: shortId(baseImage.image),
      full: baseImage.image,
      stageSeconds: spans.get("base") ?? null,
      columns: ["run 1", "run 2", "pinned"],
      rows: candidates.map((name) => ({
        name,
        cells: [
          verdict(result(name, 1)?.data.passed),
          verdict(result(name, 2)?.data.passed),
          pinnedOnBase.has(name) ? { text: "pinned", tone: "ok" } : { text: "red on base", tone: "bad" },
        ],
      })),
      notes: [suiteNote("base", b.own_suite.base)],
    });
  }

  const headImage = snap("head");
  if (headImage) {
    const headRuns = events(b, "head", "progress");
    plates.push({
      key: "head",
      title: "Head branch",
      role: "the code with the pull request, same pinned checks",
      short: shortId(headImage.image),
      full: headImage.image,
      stageSeconds: spans.get("head") ?? null,
      columns: ["base", "head", "judged"],
      rows: headRuns.map((e) => {
        const inv = b.invariants.find((i) => i.name === e.data.name);
        return {
          name: String(e.data.name),
          cells: [verdict(inv?.base === "pass"), verdict(e.data.passed), { text: inv?.kind ?? "held", tone: inv?.kind === "silent" ? "bad" : "mute" }],
        };
      }),
      notes: [suiteNote("head", b.own_suite.head)],
    });
  }

  const fixImage = snap("fix");
  if (fixImage) {
    plates.push({
      key: "fix",
      title: "Fix branch",
      role: "head with the proposed fix applied, run again",
      short: shortId(fixImage.image),
      full: fixImage.image,
      stageSeconds: spans.get("fix") ?? null,
      columns: ["file", "line", "proved"],
      rows: events(b, "fix", "progress").map((e) => ({
        name: String(e.data.name),
        cells: [
          { text: String(e.data.file), tone: "mute" },
          { text: String(e.data.line), tone: "mute" },
          { text: e.data.proved ? "proved" : "not proved", tone: e.data.proved ? "ok" : "bad" },
        ],
      })),
      notes: [snapFixNote(b)],
    });
  }

  return { plates, seconds: b.sandbox.seconds };
}

function snapFixNote(b: Bundle) {
  const proved = (events(b, "fix", "done")[0]?.data.proved as string[] | undefined)?.length ?? 0;
  return `${proved} fix proved on this branch`;
}
