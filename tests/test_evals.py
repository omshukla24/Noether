"""Offline tests for the eval harness: scoring, scheduling, the budget stop, the report, and the fixtures themselves."""
import json
import shutil
import subprocess
from argparse import Namespace

import pytest

from evals.cases import CASES_DIR, Case, load_cases
from evals.run import build_report, render_markdown, run_all, schedule
from evals.score import outcome, percent, summarize

NODE = shutil.which("node")


def row(case, expected, verdict, run=1, cost=0.02, seconds=60.0, **extra):
    return {"case": case, "expected": expected, "run": run, "verdict": verdict, "reason": "r", "cost_usd": cost,
            "seconds": seconds, **extra}


# ------------------------------------------------------------------ scoring


@pytest.mark.parametrize("expected,verdict,want", [
    ("BROKEN", "BROKEN", "caught"),
    ("BROKEN", "CONSERVED", "missed"),
    ("BROKEN", "INCONCLUSIVE", "inconclusive"),
    ("BROKEN", "ERROR", "inconclusive"),
    ("CONSERVED", "CONSERVED", "ok"),
    ("CONSERVED", "BROKEN", "false_alarm"),
    ("CONSERVED", "INCONCLUSIVE", "inconclusive"),
])
def test_outcome_of_one_run(expected, verdict, want):
    assert outcome(expected, verdict) == want


def test_an_unknown_expectation_is_an_error():
    with pytest.raises(ValueError):
        outcome("MAYBE", "BROKEN")


def test_hit_and_false_alarm_rates():
    rows = [
        row("a", "BROKEN", "BROKEN", 1), row("a", "BROKEN", "CONSERVED", 2), row("a", "BROKEN", "BROKEN", 3),
        row("b", "BROKEN", "BROKEN", 1), row("b", "BROKEN", "INCONCLUSIVE", 2), row("b", "BROKEN", "ERROR", 3),
        row("c", "CONSERVED", "CONSERVED", 1), row("c", "CONSERVED", "BROKEN", 2), row("c", "CONSERVED", "CONSERVED", 3),
        row("d", "CONSERVED", "CONSERVED", 1), row("d", "CONSERVED", "INCONCLUSIVE", 2), row("d", "CONSERVED", "CONSERVED", 3),
    ]

    s = summarize(rows)

    assert (s["silent_break_runs"], s["silent_break_caught"]) == (6, 3)
    assert s["hit_rate"] == 0.5 and s["hit_rate_decided"] == 0.75  # 3 of 6, and 3 of the 4 that reached a verdict
    assert (s["announced_runs"], s["announced_false_alarms"]) == (6, 1)
    assert s["false_alarm_rate"] == pytest.approx(0.1667, abs=1e-4) and s["false_alarm_rate_decided"] == 0.2
    assert s["inconclusive"] == 3 and s["runs"] == 12
    assert s["cost_usd"] == pytest.approx(0.24) and s["run_seconds"] == 720.0


def test_per_case_counts_keep_the_verdicts_in_order():
    s = summarize([row("a", "BROKEN", "BROKEN", 1), row("a", "BROKEN", "CONSERVED", 2)])

    case = s["cases"][0]
    assert case["verdicts"] == ["BROKEN", "CONSERVED"] and case["caught"] == 1 and case["missed"] == 1


def test_no_runs_of_a_kind_gives_no_rate_instead_of_a_division_error():
    s = summarize([row("a", "BROKEN", "BROKEN")])

    assert s["false_alarm_rate"] is None and percent(s["false_alarm_rate"]) == "n/a"
    assert summarize([])["hit_rate"] is None


# ------------------------------------------------------------------ scheduling and the budget


def fake_cases(n=3):
    return [Case(f"case{i}", "BROKEN" if i % 2 == 0 else "CONSERVED", "note", CASES_DIR) for i in range(n)]


def test_runs_go_round_robin_so_a_stop_leaves_every_case_even():
    order = [(c.name, n) for c, n in schedule(fake_cases(2), 2)]

    assert order == [("case0", 1), ("case1", 1), ("case0", 2), ("case1", 2)]


def runner_with(cost, verdict="BROKEN"):
    return lambda case, n, kind, bundles, env: row(case.name, case.expected, verdict, n, cost=cost)


def test_the_budget_stops_new_runs_before_it_is_passed():
    rows, skipped = run_all(fake_cases(3), 2, "local", 1, 1.0, None, None, log=lambda m: None, run_one=runner_with(0.4))

    # 0.4 + 0.4 = 0.8 spent; a third run at 0.4 would pass 1.0
    assert len(rows) == 2 and len(skipped) == 4
    assert sum(r["cost_usd"] for r in rows) <= 1.0
    assert skipped[0] == {"case": "case2", "run": 1}


def test_in_flight_runs_count_against_the_budget():
    # two workers, 0.4 each: the second run starts (0 + 2 x guess is fine), after the first ends 0.4 + 2 x 0.4 > 1.0
    rows, skipped = run_all(fake_cases(3), 1, "local", 2, 1.0, None, None, log=lambda m: None, run_one=runner_with(0.4))

    assert sum(r["cost_usd"] for r in rows) <= 1.0 and len(rows) + len(skipped) == 3


def test_without_a_stop_every_planned_run_happens_and_rows_are_sorted():
    rows, skipped = run_all(fake_cases(3), 2, "local", 3, 5.0, None, None, log=lambda m: None, run_one=runner_with(0.01))

    assert skipped == [] and len(rows) == 6
    assert [(r["case"], r["run"]) for r in rows] == sorted((r["case"], r["run"]) for r in rows)


# ------------------------------------------------------------------ the report


def test_markdown_carries_the_numbers_and_names_the_misses():
    cases = fake_cases(2)
    rows = [row("case0", "BROKEN", "CONSERVED", pinned=4, repaired=1, dropped=7), row("case1", "CONSERVED", "CONSERVED")]
    args = Namespace(runner="contree", runs=1, workers=2, budget=1.5)

    report = build_report(cases, rows, [], args, "20261027-120000", 125.0)
    text = render_markdown(report)

    assert "0/1 = 0%" in text and "Hit rate on silent-break cases" in text
    assert "False-alarm rate on announced-only cases | 0/1 = 0%" in text
    assert "2m 05s wall clock" in text
    assert "case0 run 1: missed, verdict CONSERVED" in text and "pinned 4, repaired 1, dropped 7" in text
    assert json.loads(json.dumps(report))["summary"]["runs"] == 2


def test_markdown_counts_the_hits_only_the_probe_round_found():
    rows = [row("case0", "BROKEN", "BROKEN", silent=["p1"], probed=["p1", "p2"]),
            row("case0", "BROKEN", "BROKEN", run=2, silent=["a", "p1"], probed=["p1"]),
            row("case0", "BROKEN", "CONSERVED", run=3, pinned=9, repaired=0, dropped=1, probed=["p3"])]
    text = render_markdown(build_report(fake_cases(1), rows, [], Namespace(runner="contree", runs=3, workers=1,
                                                                           budget=1.5), "s", 1.0))

    assert "| Hits that only the diff-guided probe round found | 1 of 2 |" in text
    assert "pinned 9, repaired 0, dropped 1, 1 of them pinned by the probe round" in text


def test_markdown_says_when_the_budget_stopped_the_run():
    report = build_report(fake_cases(1), [row("case0", "BROKEN", "BROKEN")], [{"case": "case0", "run": 2}],
                          Namespace(runner="local", runs=2, workers=1, budget=0.05), "s", 1.0)

    assert "budget stopped the run early: 1 planned runs" in render_markdown(report)


# ------------------------------------------------------------------ the committed cases


def test_the_committed_cases_are_a_mix_of_silent_breaks_and_announced_changes():
    cases = load_cases()
    kinds = [c.expected for c in cases]

    assert 12 <= len(cases) <= 15
    assert kinds.count("BROKEN") >= 5 and kinds.count("CONSERVED") >= 5
    assert {"hopper", "tiny-cart"} <= {c.name for c in cases}
    assert all(c.note and "—" not in c.note for c in cases)


def test_a_case_can_be_picked_by_name_and_an_unknown_name_is_refused():
    assert [c.name for c in load_cases(["hopper"])] == ["hopper"]
    with pytest.raises(ValueError, match="unknown case"):
        load_cases(["nope"])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.name)
def test_the_repos_own_suite_passes_on_base_and_on_head(case):
    # a silent break is only silent when the repo's own tests do not see it
    for side in ("base", "head"):
        done = subprocess.run([NODE, "--test"], cwd=case.fixture / side, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, f"{case.name} {side}: {done.stdout[-600:]}"


# What each fixture is built to do, probed directly: (case, module, expression) -> (base value, head value).
PROBES = {
    "duration-cut-to-round": ("duration.js", "formatDuration(59999)", "59.9s", "60s"),
    "duration-rounding-announced": ("duration.js", "formatDuration(1999)", "1.9s", "2s"),
    "slug-acronym-plurals": ("slug.js", "slugify('APIUser')", "api-user", "apiuser"),
    "camel-short-numbers": ("camel.js", "camelCase('e2e')", "e2e", "e2E"),
    "camel-long-numbers-announced": ("camel.js", "camelCase('e2e')", "e2e", "e2e"),
    "uniq-keeps-last": ("uniq.js", "uniqBy(['a', 'A'], (s) => s.toLowerCase())", ["a"], ["A"]),
    "uniq-filter-refactor": ("uniq.js", "uniqBy(['a', 'A'], (s) => s.toLowerCase())", ["a"], ["a"]),
    "backoff-jitter-at-cap": ("backoff.js", "retryDelay(20, { jitter: 0.5 })", 15000, 30000),
    "backoff-cap-announced": ("backoff.js", "retryDelay(5)", 1600, 1600),
    "paginate-past-the-end": ("paginate.js", "paginate(25, { page: 5 }).start", 25, 40),
}


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name", sorted(PROBES))
def test_each_fixture_does_what_its_case_says(name):
    module, expression, want_base, want_head = PROBES[name]
    case = next(c for c in load_cases() if c.name == name)
    names = {"duration.js": "formatDuration", "slug.js": "slugify", "camel.js": "camelCase", "uniq.js": "uniqBy",
             "backoff.js": "retryDelay", "paginate.js": "paginate"}
    code = f"import {{ {names[module]} }} from './src/{module}'; console.log(JSON.stringify({expression}));"
    got = {}
    for side in ("base", "head"):
        done = subprocess.run([NODE, "--input-type=module", "-e", code], cwd=case.fixture / side,
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr[-400:]
        got[side] = json.loads(done.stdout)

    assert (got["base"], got["head"]) == (want_base, want_head)
