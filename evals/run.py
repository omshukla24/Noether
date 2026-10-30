"""Run the eval cases through the real pipeline and report hit and false-alarm rates.

    python -m evals.run --runs 3 --runner contree [--cases hopper,tiny-cart] [--workers 3] [--budget 1.5]

Writes evals/results/<stamp>.json and <stamp>.md (bundles go to evals/results/<stamp>/, not committed).
Runs are round-robin by run number, so a budget stop leaves every case with about the same number of runs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.cases import Case, load_cases
from evals.score import outcome, percent, summarize

RESULTS = Path(__file__).resolve().parent / "results"
FIRST_RUN_GUESS_USD = 0.03  # until a run has finished, plan with this per run


def make_runner(kind: str) -> Any:
    from noether.runner import ContreeRunner, LocalRunner

    return LocalRunner() if kind == "local" else ContreeRunner()


def check_once(case: Case, run_no: int, runner_kind: str, bundles: Path, env_file: str | None) -> dict[str, Any]:
    """One pipeline run of one case, as a result row. Whatever goes wrong becomes verdict ERROR (counted inconclusive)."""
    from noether.bundle import cost_estimate
    from noether.ingest import from_local
    from noether.nemotron import Client
    from noether.pipeline import Caps, run_check

    row: dict[str, Any] = {"case": case.name, "expected": case.expected, "run": run_no, "verdict": "ERROR",
                           "reason": "", "cost_usd": 0.0}
    started = time.monotonic()
    runner = None
    try:
        change = from_local(str(case.fixture))
        runner = make_runner(runner_kind)
        run = run_check(change, Client.from_env(env_file), runner, None, Caps(fix=False), out_dir=str(bundles))
        base_done = next((e.data for e in run.timeline if e.stage == "base" and e.type == "done"), {})
        added = [n for e in run.timeline if e.stage == "base" and e.type == "done" and e.data.get("probe") for n in e.data.get("added", [])]
        row.update(
            verdict=run.verdict, reason=run.reason, run_id=run.run_id,
            silent=[f.invariant.name for f in run.flips if f.kind == "silent"],
            intended=[f.invariant.name for f in run.flips if f.kind == "intended"],
            pinned=len(run.invariants), repaired=len(base_done.get("repaired", [])), dropped=len(run.dropped),
            probed=added,
            cost_usd=cost_estimate(run.models), sandbox_seconds=round(run.sandbox_seconds, 1),
            bundle=f"{run.run_id}/bundle.json",
        )
    except Exception as exc:  # process boundary: the row records it and the run counts as inconclusive
        row["reason"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        close = getattr(runner, "close", None)
        if close:
            close()
    row["seconds"] = round(time.monotonic() - started, 1)
    return row


def schedule(cases: list[Case], runs: int) -> deque[tuple[Case, int]]:
    """Run 1 of every case, then run 2 of every case, and so on."""
    return deque((case, n) for n in range(1, runs + 1) for case in cases)


def run_all(cases: list[Case], runs: int, runner_kind: str, workers: int, budget: float, bundles: Path,
            env_file: str | None, log=print, run_one=check_once) -> tuple[list[dict], list[dict]]:
    """(rows, skipped). Stops starting new runs once spent + the runs in flight + one more, each at the dearest
    cost seen so far, would pass the budget."""
    queue = schedule(cases, runs)
    total = len(queue)
    rows: list[dict] = []
    skipped: list[dict] = []
    costs: list[float] = []
    spent = 0.0
    pending: dict[Any, tuple[Case, int]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        while queue or pending:
            while queue and len(pending) < workers:
                estimate = max(costs, default=FIRST_RUN_GUESS_USD)
                if spent + (len(pending) + 1) * estimate > budget:
                    skipped = [{"case": c.name, "run": n} for c, n in queue]
                    queue.clear()
                    log(f"budget: stopping, {len(skipped)} runs not started (spent ${spent:.3f} of ${budget:.2f})")
                    break
                case, n = queue.popleft()
                pending[pool.submit(run_one, case, n, runner_kind, bundles, env_file)] = (case, n)
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                case, n = pending.pop(future)
                row = future.result()
                rows.append(row)
                costs.append(row["cost_usd"])
                spent += row["cost_usd"]
                log(f"[{len(rows)}/{total}] {case.name} run {n}: {row['verdict']} "
                    f"({outcome(case.expected, row['verdict'])}) ${row['cost_usd']:.3f} {row['seconds']:.0f}s")
    rows.sort(key=lambda r: (r["case"], r["run"]))
    return rows, skipped


def duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    notes = {c["case"]: c["note"] for c in report["cases"]}
    lines = [
        f"# Noether eval results {report['stamp']}",
        "",
        f"Runner `{report['runner']}`, {report['runs_per_case']} runs per case, {len(s['cases'])} cases, "
        f"{report['workers']} in parallel, commit `{report['commit']}`. Runs are not deterministic, so each case is "
        "run several times and reported as rates; fix proposals were not run (detection only).",
        "",
        "## Totals",
        "",
        "| Measure | Result |",
        "| --- | --- |",
        f"| Hit rate on silent-break cases | {s['silent_break_caught']}/{s['silent_break_runs']} = {percent(s['hit_rate'])} "
        f"(not counting inconclusive runs: {percent(s['hit_rate_decided'])}) |",
        f"| False-alarm rate on announced-only cases | {s['announced_false_alarms']}/{s['announced_runs']} = "
        f"{percent(s['false_alarm_rate'])} (not counting inconclusive runs: {percent(s['false_alarm_rate_decided'])}) |",
        f"| Inconclusive runs | {s['inconclusive']} of {s['runs']} |",
        f"| Estimated model cost | ${s['cost_usd']:.2f} (model tokens only; sandbox time is not priced) |",
        f"| Time | {duration(report['wall_seconds'])} wall clock, {duration(s['run_seconds'])} summed over runs |",
    ]
    if any("probed" in r for r in report["rows"]):
        caught = [r for r in report["rows"] if outcome(r["expected"], r["verdict"]) == "caught"]
        by_probe = [r for r in caught if r.get("silent") and set(r["silent"]) <= set(r.get("probed", []))]
        lines.append(f"| Hits that only the diff-guided probe round found | {len(by_probe)} of {len(caught)} |")
    if report["skipped"]:
        lines += ["", f"The ${report['budget_usd']:.2f} budget stopped the run early: "
                      f"{len(report['skipped'])} planned runs were not started."]
    lines += ["", "## Per case", "", "| Case | Expected | Verdicts | Result | Note |", "| --- | --- | --- | --- | --- |"]
    for c in s["cases"]:
        good = c["caught"] if c["expected"] == "BROKEN" else c["ok"]
        bad = c["missed"] if c["expected"] == "BROKEN" else c["false_alarm"]
        label = "caught" if c["expected"] == "BROKEN" else "correct"
        result = f"{good}/{c['runs']} {label}" + (f", {c['inconclusive']} inconclusive" if c["inconclusive"] else "")
        if bad:
            result += f", {bad} {'missed' if c['expected'] == 'BROKEN' else 'false alarm'}"
        lines.append(f"| {c['case']} | {c['expected']} | {', '.join(v.lower() for v in c['verdicts'])} | {result} | "
                     f"{notes.get(c['case'], '')} |")
    wrong = [r for r in report["rows"] if outcome(r["expected"], r["verdict"]) in ("missed", "false_alarm", "inconclusive")]
    if wrong:
        lines += ["", "## Misses, false alarms and inconclusive runs", ""]
        for r in wrong:
            kind = outcome(r["expected"], r["verdict"]).replace("_", " ")
            detail = f"pinned {r.get('pinned', '?')}, repaired {r.get('repaired', '?')}, dropped {r.get('dropped', '?')}"
            if "probed" in r:
                detail += f", {len(r['probed'])} of them pinned by the probe round"
            lines.append(f"- {r['case']} run {r['run']}: {kind}, verdict {r['verdict']}. {r['reason']} ({detail})")
    return "\n".join(lines) + "\n"


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_report(cases: list[Case], rows: list[dict], skipped: list[dict], args: argparse.Namespace, stamp: str,
                 wall_seconds: float) -> dict[str, Any]:
    return {
        "stamp": stamp, "runner": args.runner, "runs_per_case": args.runs, "workers": args.workers,
        "budget_usd": args.budget, "commit": git_commit(), "wall_seconds": round(wall_seconds, 1),
        "summary": summarize(rows), "skipped": skipped,
        "cases": [{"case": c.name, "expected": c.expected, "note": c.note} for c in cases], "rows": rows,
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m evals.run", description="Measure Noether on the eval cases.")
    p.add_argument("--runs", type=int, default=3, help="runs per case (default 3)")
    p.add_argument("--runner", choices=("contree", "local"), default="contree")
    p.add_argument("--cases", help="comma-separated case names (default: all)")
    p.add_argument("--workers", type=int, default=3, help="runs in parallel (default 3)")
    p.add_argument("--budget", type=float, default=1.5, help="stop starting runs past this estimated USD (default 1.5)")
    p.add_argument("--env-file", help="env file with NEBIUS_* keys")
    p.add_argument("--out", default=str(RESULTS), help="results folder")
    args = p.parse_args(argv)
    if args.runs < 1 or args.workers < 1:
        p.error("--runs and --workers must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from noether.cli import load_env

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the Windows console is cp1252
    load_env(args.env_file)
    cases = load_cases([n.strip() for n in args.cases.split(",")] if args.cases else None)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out)
    bundles = out / stamp
    bundles.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rows, skipped = run_all(cases, args.runs, args.runner, args.workers, args.budget, bundles, args.env_file)
    report = build_report(cases, rows, skipped, args, stamp, time.monotonic() - started)
    (out / f"{stamp}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / f"{stamp}.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"wrote {out / (stamp + '.json')} and {out / (stamp + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
