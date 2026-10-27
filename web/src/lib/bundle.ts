// Shape of a sealed proof bundle, as written by noether/bundle.py.
// The Python side is the source of truth; keep the two in step.

export type Verdict = "BROKEN" | "CONSERVED" | "INCONCLUSIVE";
export type Stage = "ingest" | "intent" | "pin" | "base" | "head" | "judge" | "fix" | "seal";
export type InvariantKind = "held" | "intended" | "silent" | "dropped";

export interface BundleInvariant {
  name: string;
  claim: string;
  target_file: string;
  target_symbol: string;
  test_code: string;
  base: "pass" | "fail" | "flaky";
  head: "pass" | "fail" | null;
  kind: InvariantKind;
  output: string;
}

export interface BundleBreak {
  invariant: string;
  file: string;
  line: number;
  code: string;
  why: string;
  fix: { file: string; diff: string; proved: boolean } | null;
}

export interface SuiteSummary {
  ran: boolean;
  exit_code: number;
  passed: number;
  failed: number;
}

export interface StageEvent {
  t_ms: number;
  stage: Stage;
  type: "start" | "progress" | "done" | "error";
  data: Record<string, unknown>;
}

export interface Bundle {
  noether: string;
  run_id: string;
  repo: string;
  pr: { url: string; title: string };
  base: { ref: string; sha: string };
  head: { ref: string; sha: string };
  verdict: Verdict;
  reason: string;
  intent: {
    summary: string;
    intended_changes: string[];
    dependency_bumps: { name: string; old: string; new: string; notes: string[] }[];
  } | null;
  invariants: BundleInvariant[];
  dropped: { name: string; reason: string }[];
  breaks: BundleBreak[];
  own_suite: { base: SuiteSummary | null; head: SuiteSummary | null };
  sandbox: { snapshots: { label: string; image: string }[]; seconds: number };
  models: { role: string; model: string; tokens_in: number; tokens_out: number; ms: number }[];
  cost_est_usd: number;
  timeline: StageEvent[];
  sha256: string;
}

// Same canonical form as bundle.py: sorted keys, no spaces, sha256 field removed.
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

export async function verifySeal(bundle: Bundle): Promise<boolean> {
  const { sha256, ...rest } = bundle;
  const bytes = new TextEncoder().encode(canonicalJson(rest));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  return hex === sha256;
}
