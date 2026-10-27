"""Scoring for the eval harness. Pure functions over result rows, so it is tested offline.

A case is either a silent break (expected BROKEN) or a change the pull request text fully announces
(expected CONSERVED). Runs are not deterministic, so every case is run N times and reported as rates.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

EXPECTED = ("BROKEN", "CONSERVED")

# What one run of a case amounts to, by (expected, verdict).
OUTCOMES = {
    ("BROKEN", "BROKEN"): "caught",
    ("BROKEN", "CONSERVED"): "missed",
    ("CONSERVED", "CONSERVED"): "ok",
    ("CONSERVED", "BROKEN"): "false_alarm",
}


def outcome(expected: str, verdict: str) -> str:
    """caught | missed | ok | false_alarm | inconclusive. Anything but BROKEN or CONSERVED is inconclusive."""
    if expected not in EXPECTED:
        raise ValueError(f"expected must be one of {EXPECTED}, got {expected!r}")
    return OUTCOMES.get((expected, verdict), "inconclusive")


def rate(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-case and overall numbers from rows shaped {case, expected, verdict, cost_usd, seconds, ...}.

    hit_rate counts an inconclusive run as a miss (the strict number); hit_rate_decided leaves them out.
    """
    by_case: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_case[row["case"]].append(row)

    cases = []
    for name, runs in by_case.items():
        outcomes = [outcome(r["expected"], r["verdict"]) for r in runs]
        cases.append({
            "case": name,
            "expected": runs[0]["expected"],
            "runs": len(runs),
            "verdicts": [r["verdict"] for r in runs],
            "outcomes": outcomes,
            "caught": outcomes.count("caught"),
            "missed": outcomes.count("missed"),
            "ok": outcomes.count("ok"),
            "false_alarm": outcomes.count("false_alarm"),
            "inconclusive": outcomes.count("inconclusive"),
        })

    def total(kind: str, expected: str) -> int:
        return sum(c[kind] for c in cases if c["expected"] == expected)

    def runs_of(expected: str) -> int:
        return sum(c["runs"] for c in cases if c["expected"] == expected)

    silent_runs, announced_runs = runs_of("BROKEN"), runs_of("CONSERVED")
    caught, missed = total("caught", "BROKEN"), total("missed", "BROKEN")
    false_alarms, ok = total("false_alarm", "CONSERVED"), total("ok", "CONSERVED")
    return {
        "cases": cases,
        "silent_break_runs": silent_runs,
        "silent_break_caught": caught,
        "hit_rate": rate(caught, silent_runs),
        "hit_rate_decided": rate(caught, caught + missed),
        "announced_runs": announced_runs,
        "announced_false_alarms": false_alarms,
        "false_alarm_rate": rate(false_alarms, announced_runs),
        "false_alarm_rate_decided": rate(false_alarms, false_alarms + ok),
        "inconclusive": sum(c["inconclusive"] for c in cases),
        "runs": len(rows),
        "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in rows), 4),
        "run_seconds": round(sum(r.get("seconds", 0.0) for r in rows), 1),
    }


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"
