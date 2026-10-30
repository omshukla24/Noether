import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from noether import model as m
from noether.ingest import from_local
from noether.nemotron import ModelError
from noether.pipeline import Caps, run_check
from noether.runner import LocalRunner
from tests.tiny_cart import (DISCOUNT, FIXTURE, LINE_TOTAL, SHIPPING, FakeClient, ScriptedRunner, invariant,
                             make_stages)

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
    assert set(base_done) == {"pinned", "flaky", "repaired", "own_suite", "checkpoint"} and set(base_done["own_suite"]) == suite
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


def test_run_id_is_used_when_given_and_made_up_otherwise(tmp_path):
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


def reading_again(inv):
    return replace(inv, claim=inv.claim + " (read again)")


def test_repair_goes_to_the_model_in_small_batches_and_a_failed_batch_is_on_the_record(tmp_path):
    runner = ScriptedRunner(plan={"base": [{LINE_TOTAL.name: False, DISCOUNT.name: False, SHIPPING.name: False},
                                           {}]})
    batches = []

    def repair(client, change, failures):
        batches.append([inv.name for inv, _ in failures])
        if SHIPPING.name in batches[-1]:
            raise ModelError("repair: the reply was still not valid after one repair")
        return [reading_again(inv) for inv, _ in failures], []

    run, events, _ = run_scripted(runner, caps=Caps(repair_batch=2, repair_rounds=1),
                                  stages=make_stages(repair_invariants=repair), tmp=tmp_path)

    assert batches == [[LINE_TOTAL.name, DISCOUNT.name], [SHIPPING.name]]
    asked = {tuple(e["asked"]): e for e in of(events, "base", "progress") if "asked" in e}
    assert asked[(LINE_TOTAL.name, DISCOUNT.name)]["returned"] == [LINE_TOTAL.name, DISCOUNT.name]
    assert "still not valid" in asked[(SHIPPING.name,)]["error"]
    assert asked[(LINE_TOTAL.name, DISCOUNT.name)]["why"] == {LINE_TOTAL.name: "boom", DISCOUNT.name: "boom"}
    assert of(events, "base", "done")[0]["repaired"] == sorted([LINE_TOTAL.name, DISCOUNT.name])
    assert SHIPPING.name not in [i.name for i in run.invariants]  # the original stays red and is dropped


def test_a_second_repair_round_takes_only_the_checks_still_red(tmp_path):
    # round 1 fixes line_total only; round 2 is asked about discount alone and fixes it
    runner = ScriptedRunner(plan={"base": [{LINE_TOTAL.name: False, DISCOUNT.name: False},
                                           {DISCOUNT.name: False}, {}]})
    batches = []

    def repair(client, change, failures):
        batches.append([inv.name for inv, _ in failures])
        return [reading_again(inv) for inv, _ in failures if inv.name == LINE_TOTAL.name or len(batches) == 2], []

    run, events, _ = run_scripted(runner, stages=make_stages(repair_invariants=repair), tmp=tmp_path)

    assert batches == [[LINE_TOTAL.name, DISCOUNT.name], [DISCOUNT.name]]
    assert of(events, "base", "done")[0]["repaired"] == sorted([LINE_TOTAL.name, DISCOUNT.name])
    assert {LINE_TOTAL.name, DISCOUNT.name} <= {i.name for i in run.invariants}


def test_repair_rounds_are_capped_and_a_check_that_stays_red_fails_closed(tmp_path):
    runner = ScriptedRunner(plan={"base": [{DISCOUNT.name: False}]})  # red on every base run
    rounds = []

    def repair(client, change, failures):
        rounds.append(1)
        return [reading_again(inv) for inv, _ in failures], []

    run, events, _ = run_scripted(runner, caps=Caps(repair_rounds=2), stages=make_stages(repair_invariants=repair),
                                  tmp=tmp_path)

    assert len(rounds) == 2
    assert DISCOUNT.name not in [i.name for i in run.invariants]
    assert any(d["name"] == DISCOUNT.name and d["reason"].startswith("red on base") for d in run.dropped)


def test_an_empty_repair_reply_is_reported_instead_of_vanishing(tmp_path):
    runner = ScriptedRunner(plan={"base": [{DISCOUNT.name: False}]})

    run, events, _ = run_scripted(runner, caps=Caps(repair_rounds=1),
                                  stages=make_stages(repair_invariants=lambda c, ch, f: ([], [])), tmp=tmp_path)

    note = next(e for e in of(events, "base", "progress") if "asked" in e)
    assert note["asked"] == [DISCOUNT.name] and note["missing"] == [DISCOUNT.name]
    assert "no repaired checks" in note["error"]


def test_a_check_red_on_base_gets_one_repair_and_is_pinned_when_it_then_holds(tmp_path):
    # First base run: SHIPPING is red. The repaired version is green on the re-run and on run 2.
    runner = ScriptedRunner(plan={"base": [{SHIPPING.name: False}, {SHIPPING.name: True}, {SHIPPING.name: True}]})
    seen = []

    def repair(client, change, failures):
        seen.extend(inv.name for inv, _ in failures)
        return [replace(inv, claim=inv.claim + " (read again)") for inv, _ in failures], []

    run, events, _ = run_scripted(runner, stages=make_stages(repair_invariants=repair), tmp=tmp_path)

    assert seen == [SHIPPING.name]
    assert of(events, "base", "done")[0]["repaired"] == [SHIPPING.name]
    assert SHIPPING.name in [i.name for i in run.invariants]
    assert next(i for i in run.invariants if i.name == SHIPPING.name).claim.endswith("(read again)")


# --------------------------------------------------------------- the diff-guided probe round

PROBE = invariant("discount_just_under_half_a_cent", "discountAmount", "15 percent of 9.99 rounds to 1.50",
                  "assert.equal(discountAmount(9.99, 15), 1.5);")


def probing(*found, asked=None):
    def probe(client, change, pinned, max_items=6):
        if asked is not None:
            asked.append(([i.name for i in pinned], max_items))
        return list(found), []
    return probe


def test_the_probe_round_is_skipped_once_round_one_has_a_silent_flip(tmp_path):
    asked = []
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False}]})

    run, _, _ = run_scripted(runner, stages=make_stages(probe_invariants=probing(PROBE, asked=asked)), tmp=tmp_path)

    assert asked == [] and run.verdict == "BROKEN"


def test_the_probe_round_catches_what_round_one_missed_and_reuses_the_stages(tmp_path):
    # Round one: only SHIPPING flips, and the judge calls it announced. The probe check flips silently.
    asked = []
    runner = ScriptedRunner(plan={"head": [{SHIPPING.name: False, PROBE.name: False}]})
    stages = make_stages(probe_invariants=probing(PROBE, asked=asked))

    run, events, _ = run_scripted(runner, caps=Caps(max_probes=4), stages=stages, tmp=tmp_path)

    assert asked == [([LINE_TOTAL.name, DISCOUNT.name, SHIPPING.name], 4)]
    assert run.verdict == "BROKEN"
    assert {f.invariant.name: f.kind for f in run.flips} == {SHIPPING.name: "intended", PROBE.name: "silent"}
    assert [i.name for i in run.invariants][-1] == PROBE.name and len(run.base_results[PROBE.name]) == 2
    # the same stage names, marked probe, with no second start: the cockpit and stage spans need no change
    assert all(len(of(events, s, "start")) == 1 for s in STAGE_ORDER[:6])
    probe_base = [d for d in of(events, "base", "done") if d.get("probe")]
    assert probe_base[0]["added"] == [PROBE.name] and probe_base[0]["pinned"][-1] == PROBE.name
    assert [d["name"] for d in of(events, "pin", "progress") if d.get("probe")] == [PROBE.name]
    assert of(events, "judge", "done")[-1] == {"probe": True, "silent": [PROBE.name], "intended": [SHIPPING.name]}


def test_a_probe_check_that_fails_on_base_is_dropped_never_surfaced(tmp_path):
    # A check that encodes HEAD behaviour is red on BASE: it must not reach head or the verdict.
    runner = ScriptedRunner(plan={"base": [{}, {}, {PROBE.name: False}], "head": [{PROBE.name: False}]})

    run, events, runner = run_scripted(runner, stages=make_stages(probe_invariants=probing(PROBE)), tmp=tmp_path)

    assert run.verdict == "CONSERVED" and run.flips == []
    assert PROBE.name not in [i.name for i in run.invariants]
    assert {"name": PROBE.name, "reason": "red on base: boom"} in run.dropped
    assert runner.calls.count("run_tests") == 5  # base x2, head, probe on base x2, never on head
    assert not [d for d in of(events, "head", "done") if d.get("probe")]


def test_probe_checks_are_capped_and_may_not_reuse_a_round_one_name(tmp_path):
    other = invariant("discount_of_zero_percent", "discountAmount", "0 percent takes nothing off",
                      "assert.equal(discountAmount(9.99, 0), 0);")
    stages = make_stages(probe_invariants=probing(replace(LINE_TOTAL, claim="again"), PROBE, other))

    run, _, _ = run_scripted(caps=Caps(max_probes=1), stages=stages, tmp=tmp_path)

    assert [i.name for i in run.invariants] == [LINE_TOTAL.name, DISCOUNT.name, SHIPPING.name, PROBE.name]
    assert run.dropped[-2:] == [{"name": LINE_TOTAL.name, "reason": "duplicate test name"},
                                {"name": other.name, "reason": "over the cap of 1 tests"}]


def test_a_failed_probe_round_is_logged_and_the_first_round_stands(tmp_path):
    def broken(client, change, pinned, max_items=6):
        raise ModelError("pin: HTTP 500")

    run, events, _ = run_scripted(stages=make_stages(probe_invariants=broken), tmp=tmp_path)

    assert run.verdict == "CONSERVED" and len(run.invariants) == 3
    assert {"probe": True, "error": "the probe round stopped: pin: HTTP 500"} in of(events, "pin", "progress")
    assert not of(events, "pin", "error")


def test_max_probes_zero_turns_the_round_off(tmp_path):
    asked = []

    run_scripted(caps=Caps(max_probes=0), stages=make_stages(probe_invariants=probing(PROBE, asked=asked)), tmp=tmp_path)

    assert asked == []


# --------------------------------------------------------------- the record-on-base round

REC_META = {"claim": "a price with a half cent", "target_file": "src/cart.js", "target_symbol": "discountAmount"}
REC_MODULE = "import { discountAmount } from '../../src/cart.js';\nexport const cases = {};\n"


def recording(**cases):
    return "@@NOETHER-RECORD " + json.dumps({n: {"ok": True, "value": v} for n, v in cases.items()})


def recorder(*proposals, asked=None):
    queue = list(proposals)

    def record(client, change, max_cases, taken, previous="", feedback=""):
        if asked is not None:
            asked.append((max_cases, sorted(taken), previous, feedback))
        return queue.pop(0)
    return record


def proposal(*names):
    from noether.record import Proposal

    return Proposal(REC_MODULE, [{"name": n, **REC_META} for n in names])


def test_the_record_round_pins_recorded_inputs_and_a_silent_flip_makes_it_broken(tmp_path):
    # Round one flips only the announced shipping check. The recorded check is red on head: nothing announces it.
    asked = []
    runner = ScriptedRunner(plan={"head": [{SHIPPING.name: False, "half-cent": False}]})
    runner.recordings = [recording(**{"half-cent": "3"})]
    stages = make_stages(record_cases=recorder(proposal("half-cent"), asked=asked))

    run, events, runner = run_scripted(runner, stages=stages, tmp=tmp_path)

    assert run.verdict == "BROKEN"
    assert asked[0][0] == 16 and asked[0][1] == sorted([DISCOUNT.name, LINE_TOTAL.name, SHIPPING.name])
    assert {f.invariant.name: f.kind for f in run.flips} == {SHIPPING.name: "intended", "half-cent": "silent"}
    assert runner.modules == [("base", ["_record.mjs", "_record_run.mjs"], "_record_run.mjs")]
    assert 'const __expected = "3";' in next(i for i in run.invariants if i.name == "half-cent").test_code
    record_base = [d for d in of(events, "base", "done") if d.get("record")]
    assert record_base[0]["added"] == ["half-cent"] and record_base[0]["probe"] is True
    assert runner.calls.count("run_tests") == 6  # round one: base x2, head; record: base x2, head


def test_a_case_that_threw_on_base_is_asked_again_with_the_failure(tmp_path):
    asked = []
    runner = ScriptedRunner()
    runner.recordings = [
        "@@NOETHER-RECORD " + json.dumps({"a-case": {"ok": False, "error": "ReferenceError: level is not defined"}}),
        recording(**{"a-case-fixed": "1"})]
    stages = make_stages(record_cases=recorder(proposal("a-case"), proposal("a-case-fixed"), asked=asked))

    run, _, _ = run_scripted(runner, stages=stages, tmp=tmp_path)

    assert "ReferenceError: level is not defined" in asked[1][3] and asked[1][2] == REC_MODULE
    assert "a-case-fixed" in [i.name for i in run.invariants]
    assert {"name": "a-case", "reason": "record failed on base: ReferenceError: level is not defined"} in run.dropped


def test_a_module_that_did_not_load_is_retried_once_and_then_the_round_ends(tmp_path):
    runner = ScriptedRunner()
    runner.recordings = ["SyntaxError: Unexpected token"]
    stages = make_stages(record_cases=recorder(proposal("a-case"), proposal("b-case")))

    run, _, runner = run_scripted(runner, stages=stages, tmp=tmp_path)

    assert run.verdict == "CONSERVED" and len(run.invariants) == 3 and len(runner.modules) == 2


def test_the_record_round_is_skipped_after_a_silent_flip_and_when_max_records_is_zero(tmp_path):
    asked = []
    stages = make_stages(record_cases=recorder(proposal("half-cent"), asked=asked))

    run_scripted(ScriptedRunner(plan={"head": [{DISCOUNT.name: False}]}), stages=stages, tmp=tmp_path)
    run_scripted(caps=Caps(max_records=0), stages=stages, tmp=tmp_path)

    assert asked == []


def test_a_failed_record_round_is_logged_and_the_first_round_stands(tmp_path):
    def broken(client, change, max_cases, taken, previous="", feedback=""):
        raise ModelError("pin: HTTP 500")

    run, events, _ = run_scripted(stages=make_stages(record_cases=broken), tmp=tmp_path)

    assert run.verdict == "CONSERVED" and len(run.invariants) == 3
    assert {"probe": True, "record": True, "error": "the record round stopped: pin: HTTP 500"} in of(events, "pin", "progress")
