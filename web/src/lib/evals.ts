// The newest eval round, as evals/run.py wrote it (copied in by `npm run sync:noether`).
import data from "../content/evals.json";

export type Expected = "BROKEN" | "CONSERVED";
export type Outcome = "caught" | "missed" | "ok" | "false_alarm" | "inconclusive";

export interface EvalCase {
  case: string;
  expected: Expected;
  runs: number;
  verdicts: string[];
  outcomes: Outcome[];
  caught: number;
  missed: number;
  ok: number;
  false_alarm: number;
  inconclusive: number;
}

export interface EvalRow {
  case: string;
  expected: Expected;
  run: number;
  verdict: string;
  reason: string;
  cost_usd: number;
  run_id: string;
  pinned: number;
  repaired: number;
  dropped: number;
  sandbox_seconds: number;
  seconds: number;
}

export interface EvalRound {
  stamp: string;
  runner: string;
  runs_per_case: number;
  workers: number;
  commit: string;
  wall_seconds: number;
  budget_usd: number;
  summary: {
    cases: EvalCase[];
    silent_break_runs: number;
    silent_break_caught: number;
    hit_rate: number;
    announced_runs: number;
    announced_false_alarms: number;
    false_alarm_rate: number;
    inconclusive: number;
    runs: number;
    cost_usd: number;
    run_seconds: number;
  };
  cases: { case: string; expected: Expected; note: string }[];
  rows: EvalRow[];
}

export const EVAL = data as EvalRound;

/** "20261027-123720" -> "27 October 2026" */
export function stampDate(stamp: string): string {
  const [, y, m, d] = /^(\d{4})(\d{2})(\d{2})/.exec(stamp) ?? [];
  if (!y) return stamp;
  const month = new Date(Date.UTC(+y, +m - 1, 1)).toLocaleString("en-GB", { month: "long", timeZone: "UTC" });
  return `${+d} ${month} ${y}`;
}

export const percent = (part: number, whole: number) => (whole ? `${Math.round((100 * part) / whole)} %` : "n/a");

/** The same wording as the markdown report: "2/3 caught, 1 missed". */
export function caseResult(c: EvalCase): string {
  const broken = c.expected === "BROKEN";
  const good = broken ? c.caught : c.ok;
  const bad = broken ? c.missed : c.false_alarm;
  let out = `${good}/${c.runs} ${broken ? "caught" : "correct"}`;
  if (c.inconclusive) out += `, ${c.inconclusive} inconclusive`;
  if (bad) out += `, ${bad} ${broken ? "missed" : "false alarm"}`;
  return out;
}

/** Runs that did not end where they should, in case order. */
export const wrongRuns = (round: EvalRound) =>
  round.rows.filter((r) => {
    const v = r.verdict;
    return v === "INCONCLUSIVE" || (r.expected === "BROKEN" ? v !== "BROKEN" : v !== "CONSERVED");
  });
