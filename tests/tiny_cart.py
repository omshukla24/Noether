"""Shared test helpers: the tiny-cart invariants and stand-ins for the model side.

The fakes follow the verdict rules in the spec so the pipeline can be tested on
its own; the real modules are exercised once they are merged.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from noether import model as m
from noether.pipeline import Stages
from noether.runner import RunnerError

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "tiny-cart"
PRELUDE = "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"


def invariant(name: str, symbol: str, claim: str, check: str) -> m.Invariant:
    code = PRELUDE + f"import {{ {symbol} }} from '../../src/cart.js';\ntest('{claim}', () => {{ {check} }});\n"
    return m.Invariant(name, claim, "src/cart.js", symbol, code)


LINE_TOTAL = invariant("line_total_multiplies", "lineTotal", "line total is price times qty",
                       "assert.equal(lineTotal({ price: 9.99, qty: 3 }), 29.97);")
DISCOUNT = invariant("discount_rounds_half_up", "discountAmount", "15 percent of 19.99 rounds to 3.00",
                     "assert.equal(discountAmount(19.99, 15), 3);")
SHIPPING = invariant("sixty_ships_free", "shippingFor", "an order of 60 ships free",
                     "assert.equal(shippingFor(60), 0);")


class FakeClient:
    """Just the two attributes the pipeline reads."""

    def __init__(self, tokens_used: int = 0):
        self.calls: list[m.ModelCall] = []
        self.tokens_used = tokens_used


def decide(run: m.Run) -> tuple[str, str]:
    silent = [f for f in run.flips if f.kind == "silent"]
    base, head = run.own_suite_base, run.own_suite_head
    regressed = bool(base and head and base.ran and head.ran and base.exit_code == 0 and head.exit_code != 0)
    if silent:
        return "BROKEN", f"{len(silent)} silent flip(s)"
    if regressed:
        return "BROKEN", "the repo's own suite went from green to red"
    if not run.invariants:
        return "INCONCLUSIVE", "no invariant was green twice on base"
    return "CONSERVED", "no silent flips"


def fix_is_proven(target, head_results, intended_names, fix_results, own_head, own_fix) -> bool:
    if not fix_results[target].passed:
        return False
    if any(head_results[n].passed and not r.passed for n, r in fix_results.items()):
        return False
    if any(fix_results[n].passed != head_results[n].passed for n in intended_names):
        return False
    return not (own_head.exit_code == 0 and own_fix.exit_code != 0)


def write_bundle(run: m.Run, root: str = "runs") -> Path:
    path = Path(root) / f"{run.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"run_id": run.run_id, "verdict": run.verdict, "reason": run.reason,
            "flips": [{"name": f.invariant.name, "kind": f.kind, "proved": bool(f.fix and f.fix.proved)} for f in run.flips]}
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def read_intent(client, change) -> m.Intent:
    return m.Intent("Raises the free shipping threshold.", ["free-shipping threshold 50 -> 75"])


def pin_invariants(client, change, max_items: int = 12):
    return [LINE_TOTAL, DISCOUNT, SHIPPING], [{"name": "vague_total", "reason": "asserts nothing about behaviour"}]


def judge_flips(client, intent, change, flips):
    return [replace(f, kind="intended" if f.invariant is SHIPPING else "silent", reason="judged by the fake")
            for f in flips]


def locate_and_propose(client, change, flip):
    if flip.invariant is not DISCOUNT:
        return None, None
    source = next(f.head_source for f in change.files if f.path == "src/cart.js")
    line = source.splitlines().index(next(s for s in source.splitlines() if "Math.floor" in s)) + 1
    where = m.Location("src/cart.js", line, "Math.floor", "rounding changed from round to floor")
    return where, m.Fix("src/cart.js", source.replace("Math.floor", "Math.round"), "", False)


def make_stages(**overrides) -> Stages:
    stages = Stages(read_intent=read_intent, pin_invariants=pin_invariants, judge_flips=judge_flips,
                    locate_and_propose=locate_and_propose, decide=decide, fix_is_proven=fix_is_proven,
                    write_bundle=write_bundle)
    return replace(stages, **overrides)


class ScriptedRunner:
    """A Runner whose answers are written in the test. `plan[label]` is a list of
    {name: passed} dicts, one per call of run_tests for snapshots with that label
    (the last one repeats); names not listed pass."""

    def __init__(self, plan=None, own=None, fail_on=(), tick: float = 0.0):
        self.plan = plan or {}
        self.own = own or {}
        self.fail_on = set(fail_on)
        self.tick = tick
        self.seconds = 0.0
        self.calls: list[str] = []
        self._counts: dict[str, int] = {}

    def _step(self, what: str) -> None:
        self.calls.append(what)
        self.seconds += self.tick
        if what in self.fail_on:
            raise RunnerError(f"{what} failed in the sandbox")

    def prepare(self, change):
        self._step("prepare")
        return m.Snapshot("img-base", "base")

    def checkout_head(self, base, change):
        self._step("checkout_head")
        return m.Snapshot("img-head", "head")

    def apply_files(self, snap, files):
        self._step("apply_files")
        return m.Snapshot("img-fix", "fix:" + ",".join(files))

    def run_tests(self, snap, tests):
        self._step("run_tests")
        label = snap.label.split(":")[0]
        calls = self._counts[label] = self._counts.get(label, -1) + 1
        plan = self.plan.get(label) or [{}]
        answers = plan[min(calls, len(plan) - 1)]
        return [m.TestResult(t.name, answers.get(t.name, True), "" if answers.get(t.name, True) else "boom") for t in tests]

    def run_own_suite(self, snap):
        self._step("run_own_suite")
        return self.own.get(snap.label.split(":")[0], m.SuiteResult(True, 0, 6, 0))
