// The /check cockpit as a pure reducer: stage events in, what the screen shows out.
// The live API stream and the replay of a sealed bundle feed the very same reducer.
import type { Bundle, Stage, StageEvent, Verdict } from "./bundle";

export type RailKey = "observe" | "pin" | "expose" | "measure" | "judge" | "reprove" | "seal";

export const RAIL: { key: RailKey; label: string; stages: Stage[] }[] = [
  { key: "observe", label: "Observe", stages: ["ingest", "intent"] },
  { key: "pin", label: "Pin", stages: ["pin"] },
  { key: "expose", label: "Expose", stages: ["base"] },
  { key: "measure", label: "Measure", stages: ["head"] },
  { key: "judge", label: "Judge", stages: ["judge"] },
  { key: "reprove", label: "Re-prove", stages: ["fix"] },
  { key: "seal", label: "Seal", stages: ["seal"] },
];

const RAIL_OF = new Map<Stage, RailKey>(RAIL.flatMap((r) => r.stages.map((s) => [s, r.key] as const)));

export interface RailRow {
  key: RailKey;
  label: string;
  status: "idle" | "running" | "done" | "error";
  startMs: number | null;
  endMs: number | null;
  note: string;
}

export type BaseState = "pending" | "green1" | "locked" | "red" | "dropped";
export type HeadState = "pending" | "pass" | "flip";

export interface SpectralLine {
  name: string;
  claim: string;
  file: string;
  symbol: string;
  base: BaseState;
  head: HeadState;
  kind: "intended" | "silent" | null;
  reason: string;
  location: { file: string; line: number | null } | null;
  proved: boolean | null;
}

export interface RunError {
  code: string;
  message: string;
  retryAfter?: number;
}

export interface CockpitState {
  phase: "idle" | "running" | "done" | "failed";
  source: "live" | "replay" | null;
  rail: RailRow[];
  lines: SpectralLine[];
  lastMs: number;
  intent: string;
  verdict: Verdict | null;
  reason: string;
  runId: string | null;
  sha256: string | null;
  stored: boolean;
  error: RunError | null;
}

export const initialState: CockpitState = {
  phase: "idle",
  source: null,
  rail: RAIL.map((r) => ({ key: r.key, label: r.label, status: "idle", startMs: null, endMs: null, note: "" })),
  lines: [],
  lastMs: 0,
  intent: "",
  verdict: null,
  reason: "",
  runId: null,
  sha256: null,
  stored: false,
  error: null,
};

export interface ResultPayload {
  run_id: string;
  verdict: Verdict;
  reason: string;
  sha256: string;
  stored: boolean;
}

export type Action =
  | { type: "begin"; source: "live" | "replay" }
  | { type: "stage"; event: StageEvent }
  | { type: "result"; result: ResultPayload }
  | { type: "fail"; error: RunError }
  | { type: "reset" };

const str = (v: unknown) => (typeof v === "string" ? v : "");
const names = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : str((x as { name?: unknown })?.name))) : []);

function patchLines(lines: SpectralLine[], pick: (name: string) => boolean, patch: (l: SpectralLine) => Partial<SpectralLine>) {
  return lines.map((l) => (pick(l.name) ? { ...l, ...patch(l) } : l));
}

function applyLine(lines: SpectralLine[], ev: StageEvent): SpectralLine[] {
  const d = ev.data;
  const name = str(d.name);
  const only = (n: string) => n === name;
  if (ev.stage === "pin" && ev.type === "progress" && name) {
    if (lines.some((l) => l.name === name)) return lines;
    const blank: SpectralLine = {
      name, claim: str(d.claim), file: str(d.target_file), symbol: str(d.target_symbol),
      base: "pending", head: "pending", kind: null, reason: "", location: null, proved: null,
    };
    return [...lines, blank];
  }
  if (ev.stage === "pin" && ev.type === "done") {
    const dropped = new Set(names(d.dropped));
    return patchLines(lines, (n) => dropped.has(n), () => ({ base: "dropped" }));
  }
  if (ev.stage === "base" && ev.type === "progress") {
    const run = Number(d.run);
    return patchLines(lines, only, (l) => {
      if (d.passed !== true) return { base: "red" };
      return { base: run === 2 && l.base === "green1" ? "locked" : run === 2 ? "dropped" : "green1" };
    });
  }
  if (ev.stage === "base" && ev.type === "done") {
    const pinned = new Set(names(d.pinned));
    return lines.map((l) => (pinned.has(l.name) ? { ...l, base: "locked" as const } : { ...l, base: "dropped" as const }));
  }
  if (ev.stage === "head" && ev.type === "progress") {
    return patchLines(lines, only, () => ({ head: d.passed === true ? "pass" : "flip" }));
  }
  if (ev.stage === "judge" && ev.type === "progress") {
    return patchLines(lines, only, () => ({ kind: d.kind === "intended" ? "intended" : "silent", reason: str(d.reason) }));
  }
  if (ev.stage === "fix" && ev.type === "progress") {
    return patchLines(lines, only, () => ({
      location: { file: str(d.file), line: typeof d.line === "number" ? d.line : null },
      proved: d.proved === true,
    }));
  }
  return lines;
}

function applyRail(rail: RailRow[], ev: StageEvent): RailRow[] {
  const key = RAIL_OF.get(ev.stage);
  if (!key) return rail;
  return rail.map((row) => {
    if (row.key !== key) return row;
    if (ev.type === "start") return { ...row, status: "running", startMs: row.startMs ?? ev.t_ms };
    if (ev.type === "error") return { ...row, status: "error", endMs: ev.t_ms, note: str(ev.data.message) || row.note };
    // intent follows ingest inside one rail row: it only finishes with the last of its stages
    const last = RAIL.find((r) => r.key === key)!.stages.at(-1);
    if (ev.type === "done" && ev.stage === last) return { ...row, status: row.status === "error" ? "error" : "done", endMs: ev.t_ms };
    if (ev.type === "done" && ev.stage === "seal") return { ...row, status: "done", endMs: ev.t_ms };
    return row;
  });
}

export function reduce(state: CockpitState, action: Action): CockpitState {
  switch (action.type) {
    case "reset":
      return initialState;
    case "begin":
      return { ...initialState, phase: "running", source: action.source };
    case "stage": {
      const ev = action.event;
      // an earlier stage that never reported "done" is over once a later one starts
      let rail = applyRail(state.rail, ev);
      if (ev.type === "start") {
        const at = rail.findIndex((r) => r.key === RAIL_OF.get(ev.stage));
        rail = rail.map((r, i) => (i < at && r.status === "running" ? { ...r, status: "done", endMs: ev.t_ms } : r));
      }
      return {
        ...state,
        rail,
        lines: applyLine(state.lines, ev),
        lastMs: Math.max(state.lastMs, ev.t_ms),
        intent: ev.stage === "intent" && ev.type === "done" ? str(ev.data.summary) : state.intent,
      };
    }
    case "result":
      return {
        ...state,
        phase: "done",
        verdict: action.result.verdict,
        reason: action.result.reason,
        runId: action.result.run_id,
        sha256: action.result.sha256,
        stored: action.result.stored,
        rail: state.rail.map((r) => (r.status === "running" ? { ...r, status: "done", endMs: state.lastMs } : r)),
      };
    case "fail":
      return { ...state, phase: "failed", error: action.error, rail: state.rail.map((r) => (r.status === "running" ? { ...r, status: "error" } : r)) };
  }
}

/** Replay a sealed bundle: the timeline as stage actions with their real delays, then the result. */
export function replaySteps(bundle: Pick<Bundle, "timeline" | "run_id" | "verdict" | "reason" | "sha256">): { delayMs: number; action: Action }[] {
  let last = 0;
  const steps = bundle.timeline.map((event) => {
    const step = { delayMs: Math.max(0, event.t_ms - last), action: { type: "stage", event } as Action };
    last = event.t_ms;
    return step;
  });
  const result: ResultPayload = { run_id: bundle.run_id, verdict: bundle.verdict, reason: bundle.reason, sha256: bundle.sha256, stored: true };
  return [...steps, { delayMs: 0, action: { type: "result", result } }];
}

export function lineCounts(lines: SpectralLine[]) {
  const live = lines.filter((l) => l.base !== "dropped");
  return {
    total: lines.length,
    locked: live.filter((l) => l.base === "locked").length,
    flips: live.filter((l) => l.head === "flip").length,
    dropped: lines.length - live.length,
  };
}

const MESSAGES: Record<string, string> = {
  invalid_url: "That is not a public GitHub pull request URL. Use the form https://github.com/owner/repo/pull/12.",
  api_unreachable: "The Noether API could not be reached. Check your connection, or replay the sealed Hopper run.",
  timeout: "The run did not finish inside its 270 second limit, so it was stopped and nothing was sealed.",
  not_configured: "Live runs are not switched on for this deployment. Replay the sealed Hopper run to watch a real one.",
  bad_stream: "The stream ended before the run was sealed. Nothing was sealed; try again.",
};

export function describeError(code: string, message: string, retryAfter?: number): RunError {
  let text = MESSAGES[code] ?? message;
  if (code === "rate_limited" || code === "busy") {
    const mins = retryAfter ? Math.max(1, Math.ceil(retryAfter / 60)) : null;
    text = `${message}${mins ? ` Try again in about ${mins} min.` : ""}`;
  }
  return { code, message: text, retryAfter };
}

export const formatMs = (ms: number | null) => (ms === null ? "--" : `${(ms / 1000).toFixed(1)}s`);
