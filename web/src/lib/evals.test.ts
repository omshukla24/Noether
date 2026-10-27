import { describe, expect, it } from "vitest";
import { EVAL, caseResult, percent, stampDate, wrongRuns, type EvalCase } from "./evals";

const base: EvalCase = {
  case: "x",
  expected: "BROKEN",
  runs: 3,
  verdicts: [],
  outcomes: [],
  caught: 2,
  missed: 1,
  ok: 0,
  false_alarm: 0,
  inconclusive: 0,
};

describe("eval round helpers", () => {
  it("words a case like the markdown report", () => {
    expect(caseResult(base)).toBe("2/3 caught, 1 missed");
    expect(caseResult({ ...base, caught: 0, missed: 2, inconclusive: 1 })).toBe("0/3 caught, 1 inconclusive, 2 missed");
    expect(caseResult({ ...base, expected: "CONSERVED", caught: 0, missed: 0, ok: 2, false_alarm: 1 })).toBe(
      "2/3 correct, 1 false alarm",
    );
  });

  it("reads the stamp as a date and rounds rates", () => {
    expect(stampDate("20261027-123720")).toBe("27 October 2026");
    expect(percent(12, 24)).toBe("50 %");
    expect(percent(1, 18)).toBe("6 %");
    expect(percent(0, 0)).toBe("n/a");
  });

  it("lists exactly the runs the summary counts as wrong", () => {
    const s = EVAL.summary;
    const wrongCount = s.cases.reduce((n, c) => n + c.missed + c.false_alarm + c.inconclusive, 0);
    expect(wrongRuns(EVAL)).toHaveLength(wrongCount);
    expect(s.cases.reduce((n, c) => n + c.caught, 0)).toBe(s.silent_break_caught);
  });
});
