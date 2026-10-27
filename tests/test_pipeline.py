import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from noether import model as m
from noether.ingest import from_local
from noether.pipeline import Caps, run_check
from noether.runner import LocalRunner
from tests.tiny_cart import (DISCOUNT, FIXTURE, LINE_TOTAL, SHIPPING, FakeClient, ScriptedRunner, make_stages)

STAGE_ORDER = ["ingest", "intent", "pin", "base", "head", "judge", "fix", "seal"]


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """One real end-to-end run on tiny-cart: LocalRunner (real node), fake model stages."""
    events: list[m.Event] = []
    runner = LocalRunner()
    client = FakeClient()
    client.calls.append(m.ModelCall("judge", "fake-model", 10, 5, 1.0))
    out = tmp_path_factory.mktemp("runs")
    try:
        run = run_check(from_local(str(FIXTURE)), client, runner, events.append, stages=make_stages(), out_dir=str(out))
    finally:
        runner.close()
    return run, events, runner


def run_scripted(runner=None, caps=None, stages=None, client=None, tmp=None):
    events: list[m.Event] = []
    runner = runner or ScriptedRunner()
    run = run_check(from_local(str(FIXTURE)), client or FakeClient(), runner, events.append, caps or Caps(),
                    stages or make_stages(), out_dir=str(tmp))
    return run, events, runner


def of(events, stage, kind):
    return [e.data for e in events if e.stage == stage and e.type == kind]


# --------------------------------------------------------------- end to end


def test_tiny_cart_has_two_flips_one_intended_and_one_silent(tiny):
    run, _, _ = tiny
    flips = {f.invariant.name: f for f in run.flips}

    assert set(flips) == {DISCOUNT.name, SHIPPING.name}
    assert (flips[SHIPPING.name].kind, flips[DISCOUNT.name].kind) == ("intended", "silent")
    assert "2.99 !== 3" in flips[DISCOUNT.name].head_output


def test_tiny_cart_is_broken(tiny):
    run, _, _ = tiny

    assert run.verdict == "BROKEN" and "silent" in run.reason


def test_tiny_cart_fix_is_proven_and_only_for_the_silent_flip(tiny):
    run, _, _ = tiny
    flips = {f.invariant.name: f for f in run.flips}
    fix = flips[DISCOUNT.name].fix

    assert fix.proved and fix.file == "src/cart.js" and "Math.round" in fix.new_source
    assert fix.evidence["target_green"] is True
    assert fix.evidence["green_tests"] == sorted([LINE_TOTAL.name, DISCOUNT.name])
    assert fix.evidence["own_suite"]["exit_code"] == 0
    assert flips[SHIPPING.name].fix is None
    assert flips[DISCOUNT.name].location.file == "src/cart.js"


def test_tiny_cart_proves_on_base_twice_and_keeps_the_own_suites(tiny):
    run, _, _ = tiny

    assert [i.name for i in run.invariants] == [LINE_TOTAL.name, DISCOUNT.name, SHIPPING.name]
    assert all(len(runs) == 2 and all(r.passed for r in runs) for runs in run.base_results.values())
    assert run.dropped == [{"name": "vague_total", "reason": "asserts nothing about behaviour"}]
    assert (run.own_suite_base.exit_code, run.own_suite_head.exit_code) == (0, 0)
    assert [s.label for s in run.snapshots] == ["base", "head", "fix:src/cart.js"]


def test_tiny_cart_bundle_is_written_and_hashed(tiny):
    run, events, _ = tiny
    sealed = events[-1].data
    path = Path(sealed["bundle"])

    assert path.name == f"{run.run_id}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["verdict"] == "BROKEN"
    assert sealed["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_run_records_sandbox_seconds_and_model_calls(tiny):
    run, _, runner = tiny

    assert run.sandbox_seconds == runner.seconds > 0
    assert [c.role for c in run.models] == ["judge"]


# --------------------------------------------------------------- event contract


def test_events_arrive_in_stage_order_and_are_all_on_the_timeline(tiny):
    run, events, _ = tiny
    stages = [e.stage for e in events]

    assert [s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]] == STAGE_ORDER
    assert run.timeline == events
    assert [e.t_ms for e in events] == sorted(e.t_ms for e in events)
    assert {e.type for e in events} <= {"start", "progress", "done", "error"}


def test_every_stage_starts_and_finishes(tiny):
    _, events, _ = tiny

    for stage in STAGE_ORDER:
        assert len(of(events, stage, "start")) == 1, stage
        assert len(of(events, stage, "done")) == 1, stage


def test_event_data_keys_match_the_contract_exactly(tiny):
    _, events, _ = tiny
    suite = {"ran", "exit_code", "passed", "failed"}

    assert set(of(events, "ingest", "done")[0]) == {"repo", "base_sha", "head_sha", "title", "files"}
    assert of(events, "ingest", "done")[0]["files"] == ["src/cart.js", "test/cart.test.js"]
    assert set(of(events, "intent", "done")[0]) == {"summary", "intended_changes", "dependency_bumps"}
    assert all(set(d) == {"name", "claim", "target_file", "target_symbol"} for d in of(events, "pin", "progress"))
    assert len(of(events, "pin", "progress")) == 3
    assert of(events, "pin", "done") == [{"kept": 3, "dropped": [
        {"name": "vague_total", "reason": "asserts nothing about behaviour"}]}]
    base_progress = of(events, "base", "progress")
    assert all(set(d) == {"name", "run", "passed"} for d in base_progress)
    assert sorted((d["name"], d["run"]) for d in base_progress) == sorted(
        (n, r) for n in (LINE_TOTAL.name, DISCOUNT.name, SHIPPING.name) for r in (1, 2))
    base_done = of(events, "base", "done")[0]
    assert set(base_done) == {"pinned", "flaky", "own_suite", "checkpoint"} and set(base_done["own_suite"]) == suite
    assert base_done["flaky"] == [] and len(base_done["pinned"]) == 3
    assert all(set(d) == {"name", "passed"} for d in of(events, "head", "progress"))
    head_done = of(events, "head", "done")[0]
    assert set(head_done) == {"flips", "own_suite", "branch"} and set(head_done["own_suite"]) == suite
    assert sorted(head_done["flips"]) == sorted([DISCOUNT.name, SHIPPING.name])
    assert {d["name"]: d["kind"] for d in of(events, "judge", "progress")} == {DISCOUNT.name: "silent", SHIPPING.name: "intended"}
    assert all(set(d) == {"name", "kind", "reason"} for d in of(events, "judge", "progress"))
    head_cart = (FIXTURE / "head" / "src" / "cart.js").read_text(encoding="utf-8").splitlines()
    floor_line = next(i for i, text in enumerate(head_cart, 1) if "Math.floor" in text)
    assert of(events, "fix", "progress") == [{"name": DISCOUNT.name, "file": "src/cart.js", "line": floor_line, "proved": True}]
    assert set(of(events, "seal", "done")[0]) == {"verdict", "reason", "sha256", "bundle"}


def test_dependency_bumps_are_sent_as_plain_dicts(tmp_path):
    bumped = m.Intent("bump", ["a"], [m.DepBump("left-pad", "1.0.0", "2.0.0", ["breaking: drops node 8"])])
    stages = make_stages(read_intent=lambda client, change: bumped)

    _, events, _ = run_scripted(stages=stages, tmp=tmp_path)

    assert of(events, "intent", "done")[0]["dependency_bumps"] == [
        {"name": "left-pad", "old": "1.0.0", "new": "2.0.0", "notes": ["breaking: drops node 8"]}]


# --------------------------------------------------------------- proving on base


def test_flaky_and_red_tests_are_not_pinned(tmp_path):
    runner = ScriptedRunner(plan={"base": [{DISCOUNT.name: True, SHIPPING.name: False},
                                           {DISCOUNT.name: False, SHIPPING.name: False}]})

    run, events, runner = run_scripted(runner, tmp=tmp_path)

    assert [i.name for i in run.invariants] == [LINE_TOTAL.name]
    assert of(events, "base", "done")[0]["pinned"] == [LINE_TOTAL.name]
    assert of(events, "base", "done")[0]["flaky"] == [DISCOUNT.name]
    reasons = {d["name"]: d["reason"] for d in run.dropped}
    assert reasons[DISCOUNT.name].startswith("flaky on base")
    assert reasons[SHIPPING.name] == "red on base: boom"
    assert [d["name"] for d in of(events, "head", "progress")] == [LINE_TOTAL.name]
    assert run.verdict == "CONSERVED"


def test_no_pinned_test_is_inconclusive_but_the_own_suite_still_runs_on_head(tmp_path):
    runner = ScriptedRunner(plan={"base": [{LINE_TOTAL.name: False, DISCOUNT.name: False, SHIPPING.name: False}]})

    run, events, runner = run_scripted(runner, tmp=tmp_path)

    assert run.verdict == "INCONCLUSIVE" and "no invariant" in run.reason
    assert runner.calls == ["prepare", "run_tests", "run_tests", "run_own_suite", "checkout_head", "run_own_suite"]
    assert not of(events, "fix", "start") and not of(events, "judge", "progress")


def test_an_own_suite_regression_is_caught_even_with_no_pinned_test(tmp_path):
    runner = ScriptedRunner(plan={"base": [{LINE_TOTAL.name: False, DISCOUNT.name: False, SHIPPING.name: False}]},
                            own={"head": m.SuiteResult(True, 1, 5, 1)})

    run, _, _ = run_scripted(runner, tmp=tmp_path)

    assert run.verdict == "BROKEN" and "own suite" in run.reason


def test_a_change_that_flips_nothing_is_conserved(tmp_path):
    run, events, _ = run_scripted(tmp=tmp_path)

    assert run.verdict == "CONSERVED" and run.flips == []
    assert of(events, "head", "done")[0]["flips"] == []
    assert not of(events, "judge", "progress") and not of(events, "fix", "start")


def test_too_many_or_duplicate_tests_are_dropped_with_a_reason(tmp_path):
    twin = replace(LINE_TOTAL, claim="same name again")
    stages = make_stages(pin_invariants=lambda client, change, max_items=12: ([LINE_TOTAL, twin, DISCOUNT, SHIPPING], []))

    run, events, _ = run_scripted(stages=stages, caps=Caps(max_invariants=2), tmp=tmp_path)

    assert [i.name for i in run.invariants] == [LINE_TOTAL.name, DISCOUNT.name]
    assert run.dropped == [{"name": LINE_TOTAL.name, "reason": "duplicate test name"},
                           {"name": SHIPPING.name, "reason": "over the cap of 2 tests"}]
    assert of(events, "pin", "done")[0]["kept"] == 2


# --------------------------------------------------------------- failing closed


def test_a_sandbox_failure_is_inconclusive_and_still_sealed(tmp_path):
    run, events, _ = run_scripted(ScriptedRunner(fail_on={"prepare"}), tmp=tmp_path)

    assert run.verdict == "INCONCLUSIVE"
    assert run.reason == "sandbox failed during base: prepare failed in the sandbox"
    assert of(events, "base", "error") == [{"message": run.reason}]
    sealed = of(events, "seal", "done")[0]
    assert sealed["verdict"] == "INCONCLUSIVE"
    assert json.loads(Path(sealed["bundle"]).read_text(encoding="utf-8"))["verdict"] == "INCONCLUSIVE"
    assert not of(events, "head", "start")


def test_a_head_checkout_failure_is_inconclusive_not_conserved(tmp_path):
    run, _, _ = run_scripted(ScriptedRunner(fail_on={"checkout_head"}), tmp=tmp_path)

    assert run.verdict == "INCONCLUSIVE" and "during head" in run.reason


def test_the_token_cap_stops_the_run_before_any_work(tmp_path):
    runner = ScriptedRunner()

    run, events, _ = run_scripted(runner, client=FakeClient(tokens_used=250_001), tmp=tmp_path)

    assert run.verdict == "INCONCLUSIVE" and "model token cap hit" in run.reason
    assert runner.calls == [] and of(events, "intent", "error")


def test_the_sandbox_time_cap_stops_the_run(tmp_path):
    runner = ScriptedRunner(tick=400)

    run, events, _ = run_scripted(runner, caps=Caps(max_sandbox_seconds=600), tmp=tmp_path)

    assert run.verdict == "INCONCLUSIVE" and "sandbox time cap hit" in run.reason
    assert of(events, "base", "error")
    assert runner.calls == ["prepare", "run_tests"]


def test_unexpected_bugs_are_not_swallowed(tmp_path):
    def broken(client, change):
        raise ValueError("a bug, not a cap")

    with pytest.raises(ValueError, match="a bug"):
        run_scripted(stages=make_stages(read_intent=broken), tmp=tmp_path)


def test_a_judge_that_skips_a_flip_leaves_it_silent(tmp_path):
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False}]})
    stages = make_stages(judge_flips=lambda client, intent, change, flips: [])

    run, events, _ = run_scripted(runner, stages=stages, tmp=tmp_path)

    assert run.verdict == "BROKEN"
    assert run.flips[0].kind == "silent" and run.flips[0].reason == "the judge gave no verdict"
    assert of(events, "judge", "progress")[0]["kind"] == "silent"


# --------------------------------------------------------------- fixes


def test_a_fix_that_breaks_another_test_is_not_proven(tmp_path):
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False, SHIPPING.name: False}],
                                  "fix": [{DISCOUNT.name: True, SHIPPING.name: False, LINE_TOTAL.name: False}]})

    run, events, _ = run_scripted(runner, tmp=tmp_path)

    fix = next(f for f in run.flips if f.invariant.name == DISCOUNT.name).fix
    assert run.verdict == "BROKEN" and fix.proved is False
    assert of(events, "fix", "progress")[0]["proved"] is False


def test_a_fix_that_also_flips_an_intended_test_back_is_not_proven(tmp_path):
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False, SHIPPING.name: False}],
                                  "fix": [{DISCOUNT.name: True, SHIPPING.name: True}]})

    run, _, _ = run_scripted(runner, tmp=tmp_path)

    assert next(f for f in run.flips if f.invariant.name == DISCOUNT.name).fix.proved is False


def test_no_fix_flag_skips_the_fix_stage(tmp_path):
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False}]})

    run, events, runner = run_scripted(runner, caps=Caps(fix=False), tmp=tmp_path)

    assert run.verdict == "BROKEN" and not any(e.stage == "fix" for e in events)
    assert "apply_files" not in runner.calls and run.flips[0].fix is None


def test_only_max_fixes_flips_get_a_fix_attempt(tmp_path):
    asked = []

    def locate(client, change, flip):
        asked.append(flip.invariant.name)
        return None, None

    runner = ScriptedRunner(plan={"head": [{LINE_TOTAL.name: False, DISCOUNT.name: False, SHIPPING.name: False}]})
    stages = make_stages(judge_flips=lambda c, i, ch, flips: [replace(f, kind="silent") for f in flips],
                         locate_and_propose=locate)

    run, events, _ = run_scripted(runner, caps=Caps(max_fixes=2), stages=stages, tmp=tmp_path)

    assert asked == [LINE_TOTAL.name, DISCOUNT.name]
    assert [d["proved"] for d in of(events, "fix", "progress")] == [False, False]
    assert run.verdict == "BROKEN"


def test_a_fix_that_cannot_be_applied_is_logged_and_the_verdict_stands(tmp_path):
    runner = LocalRunner()
    stages = make_stages(locate_and_propose=lambda client, change, flip: (None, m.Fix("../evil.js", "x", "", False)))
    try:
        run, events, _ = run_scripted(runner, stages=stages, tmp=tmp_path)
    finally:
        runner.close()

    assert run.verdict == "BROKEN"
    assert "unsafe path" in of(events, "fix", "error")[0]["message"]
    assert not any(f.fix and f.fix.proved for f in run.flips)


def test_a_cap_hit_while_fixing_keeps_the_broken_verdict(tmp_path):
    # Seven sandbox calls come before the fix stage (700s), the eighth call crosses the 750s cap.
    runner = ScriptedRunner(tick=100, plan={"head": [{DISCOUNT.name: False}]})

    run, events, _ = run_scripted(runner, caps=Caps(max_sandbox_seconds=750), tmp=tmp_path)

    assert run.verdict == "BROKEN"
    assert "sandbox time cap hit" in of(events, "fix", "error")[0]["message"]
    assert run.flips[0].fix.proved is False


# --------------------------------------------------------------- ids and real modules


def test_run_id_is_used_or_generated(tmp_path):
    named = run_check(from_local(str(FIXTURE)), FakeClient(), ScriptedRunner(), stages=make_stages(), run_id="abc",
                      out_dir=str(tmp_path))
    auto = run_check(from_local(str(FIXTURE)), FakeClient(), ScriptedRunner(), stages=make_stages(), out_dir=str(tmp_path))

    assert named.run_id == "abc" and (tmp_path / "abc.json").exists()
    assert auto.run_id and auto.run_id != "abc"


def test_real_verdict_and_bundle_modules_agree_with_the_pipeline(tmp_path):
    verdict = pytest.importorskip("noether.verdict")
    bundle = pytest.importorskip("noether.bundle")
    stages = make_stages(decide=verdict.decide, fix_is_proven=verdict.fix_is_proven, write_bundle=bundle.write_bundle)
    runner = LocalRunner()
    try:
        run = run_check(from_local(str(FIXTURE)), FakeClient(), runner, stages=stages, out_dir=str(tmp_path))
    finally:
        runner.close()

    assert run.verdict == "BROKEN"
    assert next(f for f in run.flips if f.invariant.name == DISCOUNT.name).fix.proved
    assert Path(run.timeline[-1].data["bundle"]).exists()
