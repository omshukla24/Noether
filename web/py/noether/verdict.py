"""Verdict rules. They live in code so a model can never decide the outcome.

BROKEN        at least one silent flip, or the repo's own suite went from exit 0 on base to non-zero on head.
CONSERVED     no silent flip, own suite not worse, at least one pinned test.
INCONCLUSIVE  nothing pinned, or the pipeline already recorded why it could not finish. Always with a reason.
"""
from __future__ import annotations

from noether.model import Run, SuiteResult, TestResult


def base_status(run: Run, name: str) -> str:
    """"pass" | "fail" | "flaky" from the base runs. A test with no recorded base runs is taken as pinned,
    for pipelines that only keep the tests that survived the base stage in run.invariants."""
    results = run.base_results.get(name)
    if not results:
        return "pass"
    passed = {r.passed for r in results}
    return "pass" if passed == {True} else "fail" if passed == {False} else "flaky"


def pinned_names(run: Run) -> list[str]:
    return [i.name for i in run.invariants if base_status(run, i.name) == "pass"]


def _own_suite_regressed(run: Run) -> bool:
    base, head = run.own_suite_base, run.own_suite_head
    return bool(base and head and base.ran and head.ran and base.exit_code == 0 and head.exit_code != 0)


def decide(run: Run) -> tuple[str, str]:
    """(verdict, one-sentence reason)."""
    if run.verdict == "INCONCLUSIVE" and run.reason:
        return "INCONCLUSIVE", run.reason
    silent = [f.invariant.name for f in run.flips if f.kind == "silent"]
    if silent:
        names = ", ".join(silent[:3]) + (f" and {len(silent) - 3} more" if len(silent) > 3 else "")
        if len(silent) == 1:
            return "BROKEN", f"The pinned behaviour {names} held on base, fails on head, and the pull request does not announce it."
        return "BROKEN", f"{len(silent)} pinned behaviours held on base and fail on head without the pull request announcing them: {names}."
    if _own_suite_regressed(run):
        return "BROKEN", f"The repo's own tests pass on base but fail on head (exit code {run.own_suite_head.exit_code})."
    pinned = pinned_names(run)
    if not pinned:
        return "INCONCLUSIVE", "No test could be pinned to the base behaviour, so there was nothing to compare."
    base = run.own_suite_base
    if base and base.ran and run.own_suite_head is None:
        return "INCONCLUSIVE", "The repo's own tests ran on base but not on head, so the comparison is incomplete."
    intended = sum(1 for f in run.flips if f.kind == "intended")
    held = len(pinned) - intended
    tail = f", and {intended} changed exactly as the pull request announced" if intended else ""
    return "CONSERVED", f"All {len(pinned)} pinned behaviours were checked: {held} still hold on head{tail}."


def _suite_not_worse(head: SuiteResult | None, fix: SuiteResult | None) -> bool:
    if head is None or not head.ran:
        return fix is None or not fix.ran or fix.exit_code == 0
    if fix is None or not fix.ran:
        return False
    if head.exit_code == 0:
        return fix.exit_code == 0
    return fix.failed <= head.failed


def fix_is_proven(target: str, head_results: dict[str, TestResult], intended: set[str],
                  fix_results: dict[str, TestResult], own_head: SuiteResult | None,
                  own_fix: SuiteResult | None) -> bool:
    """A fix is shown only when the re-run on its branch shows all of this:
    the target flip is green, every test that was green on head still is, intended flips stay as they were
    on head, and the own suite is not worse than on head."""
    result = fix_results.get(target)
    if result is None or not result.passed:
        return False
    for name, on_head in head_results.items():
        if name == target:
            continue
        after = fix_results.get(name)
        if after is None:
            return False
        if on_head.passed and not after.passed:
            return False
        if name in intended and after.passed != on_head.passed:
            return False
    if any(name not in head_results or name not in fix_results for name in intended):
        return False
    return _suite_not_worse(own_head, own_fix)
