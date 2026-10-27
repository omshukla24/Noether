// The sealed Hopper run the home page tells the story of. Imported at build time
// by server components, which hand each section only the slice it draws.
import hopper from "../../public/runs/hopper.json";
import type { Bundle, Stage, StageEvent } from "./bundle";

export const RUN = hopper as unknown as Bundle;

export const shortId = (uuid: string) => uuid.slice(0, 8);

export interface StageSpan {
  stage: Stage;
  startMs: number;
  endMs: number;
}

/** Wall-clock span of each stage, from its start event to the next stage's start (or its own done). */
export function stageSpans(timeline: StageEvent[]): StageSpan[] {
  const starts = timeline.filter((e) => e.type === "start");
  return starts.map((s, i) => {
    const done = timeline.find((e) => e.stage === s.stage && (e.type === "done" || e.type === "error"));
    const next = starts[i + 1];
    return { stage: s.stage, startMs: s.t_ms, endMs: done?.t_ms ?? next?.t_ms ?? s.t_ms };
  });
}

export function tokensByRole(bundle: Bundle) {
  const out = new Map<string, { model: string; calls: number; tokensIn: number; tokensOut: number; ms: number }>();
  for (const m of bundle.models) {
    const row = out.get(m.role) ?? { model: m.model, calls: 0, tokensIn: 0, tokensOut: 0, ms: 0 };
    row.calls += 1;
    row.tokensIn += m.tokens_in;
    row.tokensOut += m.tokens_out;
    row.ms += m.ms;
    out.set(m.role, row);
  }
  return [...out].map(([role, row]) => ({ role, ...row }));
}
