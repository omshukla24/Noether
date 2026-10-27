import pytest

from noether.model import Flip, Invariant, Run, SuiteResult
from noether.model import TestResult as Result  # a name starting with "Test" makes pytest try to collect it
from noether.verdict import base_status, decide, fix_is_proven, pinned_names


def inv(name):
    return Invariant(name, f"{name} claim", "src/a.js", "a", "// code")


def flip(name, kind="silent"):
    return Flip(inv(name), "failed", kind=kind)


def suite(exit_code=0, ran=True, failed=0):
    return SuiteResult(ran=ran, exit_code=exit_code, failed=failed)


def make_run(change, names=("t1", "t2"), flips=(), base=None, head=None, **kw):
    return Run("r1", change, invariants=[inv(n) for n in names], flips=list(flips), own_suite_base=base,
               own_suite_head=head, **kw)


def passed(name="t", ok=True):
    return Result(name, ok)


# --- decide -----------------------------------------------------------------------------------------------

def test_one_silent_flip_is_broken(change):
    verdict, reason = decide(make_run(change, flips=[flip("t1")]))
    assert verdict == "BROKEN" and "t1" in reason and reason.endswith(".")


def test_several_silent_flips_are_named_and_counted(change):
    names = [f"t{i}" for i in range(5)]
    verdict, reason = decide(make_run(change, names=names, flips=[flip(n) for n in names]))
    assert verdict == "BROKEN" and reason.startswith("5 pinned behaviours") and "and 2 more" in reason


def test_intended_flips_alone_conserve(change):
    verdict, reason = decide(make_run(change, flips=[flip("t1", "intended")], base=suite(), head=suite()))
    assert verdict == "CONSERVED" and "announced" in reason and "1 still hold" in reason


def test_a_silent_flip_beats_intended_ones(change):
    assert decide(make_run(change, flips=[flip("t1", "intended"), flip("t2")]))[0] == "BROKEN"


def test_no_flips_and_a_pinned_test_is_conserved(change):
    verdict, reason = decide(make_run(change, base=suite(), head=suite()))
    assert verdict == "CONSERVED" and "2 pinned" in reason


def test_own_suite_regression_is_broken_even_without_flips(change):
    verdict, reason = decide(make_run(change, base=suite(0), head=suite(1)))
    assert verdict == "BROKEN" and "exit code 1" in reason


@pytest.mark.parametrize("base,head", [
    (suite(1), suite(1)),                 # already red on base: not a regression
    (suite(1), suite(0)),
    (suite(0), suite(0)),
    (suite(ran=False), suite(ran=False)),  # no own tests at all
    (suite(0), suite(1, ran=False)),
])
def test_own_suite_that_is_not_worse_does_not_break(change, base, head):
    assert decide(make_run(change, base=base, head=head))[0] == "CONSERVED"


def test_nothing_pinned_is_inconclusive(change):
    verdict, reason = decide(make_run(change, names=()))
    assert verdict == "INCONCLUSIVE" and "No test could be pinned" in reason


def test_tests_that_were_not_green_twice_on_base_are_not_pinned(change):
    run = make_run(change, names=("ok", "flaky", "red"))
    run.base_results = {"ok": [passed("ok"), passed("ok")], "flaky": [passed("flaky"), passed("flaky", False)],
                        "red": [passed("red", False), passed("red", False)]}
    assert pinned_names(run) == ["ok"]
    assert [base_status(run, n) for n in ("ok", "flaky", "red", "unrecorded")] == ["pass", "flaky", "fail", "pass"]
    run.invariants = [i for i in run.invariants if i.name != "ok"]
    assert decide(run)[0] == "INCONCLUSIVE"


def test_a_reason_set_by_the_pipeline_is_kept(change):
    run = make_run(change, flips=[flip("t1")], verdict="INCONCLUSIVE", reason="Install failed on base.")
    assert decide(run) == ("INCONCLUSIVE", "Install failed on base.")


def test_inconclusive_without_a_reason_is_decided_from_the_evidence(change):
    run = make_run(change, flips=[flip("t1")], verdict="INCONCLUSIVE", reason="")
    assert decide(run)[0] == "BROKEN"


def test_head_suite_missing_after_base_ran_is_inconclusive(change):
    verdict, reason = decide(make_run(change, base=suite(), head=None))
    assert verdict == "INCONCLUSIVE" and "not on head" in reason


# --- fix_is_proven ----------------------------------------------------------------------------------------

def results(**kw):
    return {name: Result(name, ok) for name, ok in kw.items()}


HEAD = results(target=False, steady=True, announced=False)
GOOD_FIX = results(target=True, steady=True, announced=False)


def proven(head=HEAD, intended=frozenset({"announced"}), fix=GOOD_FIX, own_head=None, own_fix=None):
    return fix_is_proven("target", head, set(intended), fix, own_head, own_fix)


def test_a_clean_fix_is_proven():
    assert proven()
    assert proven(own_head=suite(0), own_fix=suite(0))


def test_target_must_turn_green():
    assert not proven(fix=results(target=False, steady=True, announced=False))
    assert not proven(fix=results(steady=True, announced=False))


def test_a_test_green_on_head_must_stay_green():
    assert not proven(fix=results(target=True, steady=False, announced=False))
    assert not proven(fix=results(target=True, announced=False))  # steady not re-run


def test_intended_flips_stay_as_they_were_on_head():
    assert not proven(fix=results(target=True, steady=True, announced=True))
    assert not proven(fix=results(target=True, steady=True))  # announced not re-run
    assert not proven(head=results(target=False, steady=True), intended={"announced"}, fix=results(target=True, steady=True))


def test_own_suite_must_not_get_worse():
    assert not proven(own_head=suite(0), own_fix=suite(1))
    assert not proven(own_head=suite(0), own_fix=None)
    assert not proven(own_head=suite(0), own_fix=suite(ran=False))
    assert not proven(own_head=suite(1, failed=1), own_fix=suite(1, failed=3))
    assert proven(own_head=suite(1, failed=2), own_fix=suite(1, failed=2))
    assert proven(own_head=suite(1, failed=2), own_fix=suite(0))
    assert proven(own_head=suite(ran=False), own_fix=suite(ran=False))
    assert not proven(own_head=None, own_fix=suite(1))
