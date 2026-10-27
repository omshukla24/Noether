// The two flips the visitor judges, each from a real sealed run of the same pull request.
import type { Bundle } from "./bundle";
import { failureLine } from "./story";

export type Truth = "intended" | "silent";

export interface JudgeCase {
  runId: string;
  bundleFile: string;
  name: string;
  claim: string;
  failure: string;
  truth: Truth;
  /** Nemotron Ultra's reason, as recorded in the judge stage of the bundle */
  reason: string;
  model: string;
}

/** One case per flip the run's judge ruled on. Null when the run has no ruling for it. */
export function judgeCase(bundle: Bundle, kind: Truth, bundleFile: string): JudgeCase | null {
  const flip = bundle.invariants.find((i) => i.kind === kind);
  const ruling = bundle.timeline.find((e) => e.stage === "judge" && e.type === "progress" && e.data.name === flip?.name);
  const model = bundle.models.find((m) => m.role === "judge")?.model;
  if (!flip || !ruling || ruling.data.kind !== kind || !model) return null;
  return {
    runId: bundle.run_id,
    bundleFile,
    name: flip.name,
    claim: flip.claim,
    failure: failureLine(flip.output),
    truth: kind,
    reason: String(ruling.data.reason),
    model,
  };
}
