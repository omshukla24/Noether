"""The eight stages, in order: ingest, intent, pin, base, head, judge, fix, seal.

Each stage emits `Event`s (the CLI prints them, the web cockpit animates on them)
and fills in the `Run`. Models only write and judge; every verdict comes from
`noether.verdict`. Anything that goes wrong before the verdict ends the run as
INCONCLUSIVE with a reason, and a bundle is still sealed.

Model-side modules are imported lazily so this file can be tested with fakes.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from noether.junit import pinned_filename
from noether.model import Change, Emit, Event, Fix, Flip, Invariant, Run, Snapshot, Stage, SuiteResult, TestResult
from noether.runner import RunnerError


@dataclass
class Caps:
    max_invariants: int = 12
    max_run_tokens: int = 250_000
    max_sandbox_seconds: int = 600
    max_fixes: int = 3
    fix: bool = True


def _lazy(module: str, attr: str) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        return getattr(importlib.import_module(module), attr)(*args, **kwargs)

    call.__name__ = attr
    return call


def _read_intent(client: Any, change: Change) -> Any:
    from noether.intent import read_intent

    return read_intent(client, change, tavily_key=os.environ.get("TAVILY_API_KEY"))


@dataclass
class Stages:
    """The model-side functions the pipeline calls. Defaults are the real ones."""
    read_intent: Callable[..., Any] = _read_intent
    pin_invariants: Callable[..., Any] = _lazy("noether.pin", "pin_invariants")
    judge_flips: Callable[..., Any] = _lazy("noether.judge", "judge_flips")
    locate_and_propose: Callable[..., Any] = _lazy("noether.fix", "locate_and_propose")
    decide: Callable[..., Any] = _lazy("noether.verdict", "decide")
    fix_is_proven: Callable[..., Any] = _lazy("noether.verdict", "fix_is_proven")
    write_bundle: Callable[..., Any] = _lazy("noether.bundle", "write_bundle")


class CapHit(Exception):
    """A run cap (model tokens or sandbox seconds) was exceeded."""


def _nemotron_errors(*names: str) -> tuple[type[Exception], ...]:
    try:
        module = importlib.import_module("noether.nemotron")
    except ImportError:
        return ()
    return tuple(getattr(module, n) for n in names if hasattr(module, n))


def _cap_errors() -> tuple[type[Exception], ...]:
    return (CapHit, *_nemotron_errors("TokenCapHit", "BudgetExhausted"))


def _model_errors() -> tuple[type[Exception], ...]:
    return _nemotron_errors("ModelError")


def suite_data(suite: SuiteResult | None) -> dict[str, Any]:
    s = suite or SuiteResult(ran=False)
    return {"ran": s.ran, "exit_code": s.exit_code, "passed": s.passed, "failed": s.failed}


def run_check(
    change: Change,
    client: Any,
    runner: Any,
    emit: Emit | None = None,
    caps: Caps = Caps(),
    stages: Stages | None = None,
    run_id: str | None = None,
    out_dir: str = "runs",
) -> Run:
    """Check one change end to end. Always returns a sealed `Run`; never raises for
    a failed sandbox, model or cap (those end the run as INCONCLUSIVE)."""
    return _Check(change, client, runner, emit, caps, stages or Stages(), run_id, out_dir).execute()


class _Check:
    def __init__(self, change, client, runner, emit, caps, stages, run_id, out_dir):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.run = Run(run_id=run_id or f"{stamp}-{uuid.uuid4().hex[:6]}", change=change)
        self.client, self.runner, self.emit = client, runner, emit
        self.caps, self.stages, self.out_dir = caps, stages, out_dir
        self.started = time.monotonic()
        self.stage: Stage = "ingest"
        self.aborted = False
        self.base_snap: Snapshot | None = None
        self.head_snap: Snapshot | None = None

    # ------------------------------------------------------------ plumbing

    def event(self, stage: Stage, type_: str, /, **data: Any) -> None:
        # positional-only: a data key may legitimately be called "kind" or "type"
        ev = Event(int((time.monotonic() - self.started) * 1000), stage, type_, data)  # type: ignore[arg-type]
        self.run.timeline.append(ev)
        if self.emit:
            self.emit(ev)

    def guard(self) -> None:
        used = getattr(self.client, "tokens_used", 0)
        if used > self.caps.max_run_tokens:
            raise CapHit(f"model token cap hit ({used} > {self.caps.max_run_tokens})")
        spent = getattr(self.runner, "seconds", 0.0)
        if spent > self.caps.max_sandbox_seconds:
            raise CapHit(f"sandbox time cap hit ({spent:.0f}s > {self.caps.max_sandbox_seconds}s)")

    def begin(self, stage: Stage) -> None:
        self.stage = stage
        self.event(stage, "start")

    def abort(self, reason: str) -> None:
        self.aborted = True
        self.run.verdict, self.run.reason = "INCONCLUSIVE", reason
        self.event(self.stage, "error", message=reason)

    def tests(self, stage: Stage, snap: Snapshot, tests: list[Invariant], run_no: int | None = None,
              progress: bool = True) -> dict[str, TestResult]:
        self.guard()
        got = {r.name: r for r in self.runner.run_tests(snap, tests)}
        for t in tests:
            result = got.setdefault(t.name, TestResult(t.name, False, "the runner returned no result"))
            if progress:
                extra = {"run": run_no} if run_no else {}
                self.event(stage, "progress", name=t.name, **extra, passed=result.passed)
        return got

    # ------------------------------------------------------------ run

    def execute(self) -> Run:
        try:
            self.do_ingest()
            self.do_intent()
            self.do_pin()
            self.do_base()
            self.do_head()
            self.do_judge()
        except _cap_errors() as exc:
            self.abort(f"cap hit during {self.stage}: {exc}")
        except RunnerError as exc:
            self.abort(f"sandbox failed during {self.stage}: {exc}")
        except _model_errors() as exc:
            self.abort(f"model call failed during {self.stage}: {exc}")
        else:
            self.do_fix()
        self.do_seal()
        return self.run

    def do_ingest(self) -> None:
        c = self.run.change
        self.begin("ingest")
        self.event("ingest", "done", repo=c.repo, base_sha=c.base_sha, head_sha=c.head_sha,
                   title=c.title, files=[f.path for f in c.files])

    def do_intent(self) -> None:
        self.begin("intent")
        self.guard()
        intent = self.stages.read_intent(self.client, self.run.change)
        self.run.intent = intent
        self.guard()
        self.event("intent", "done", summary=intent.summary, intended_changes=list(intent.intended_changes),
                   dependency_bumps=[asdict(b) for b in intent.dependency_bumps])

    def do_pin(self) -> None:
        self.begin("pin")
        self.guard()
        got, dropped = self.stages.pin_invariants(self.client, self.run.change, max_items=self.caps.max_invariants)
        kept, dropped = self.unique(list(got), list(dropped))
        self.guard()
        for inv in kept:
            self.event("pin", "progress", name=inv.name, claim=inv.claim,
                       target_file=inv.target_file, target_symbol=inv.target_symbol)
        self.event("pin", "done", kept=len(kept), dropped=dropped)
        self.run.invariants, self.run.dropped = kept, dropped

    def unique(self, invariants: list[Invariant], dropped: list[dict[str, str]]):
        """Enforce the invariant cap and one pinned file per name."""
        kept: list[Invariant] = []
        seen: set[str] = set()
        for inv in invariants:
            file = pinned_filename(inv.name)
            if file in seen:
                dropped.append({"name": inv.name, "reason": "duplicate test name"})
            elif len(kept) >= self.caps.max_invariants:
                dropped.append({"name": inv.name, "reason": f"over the cap of {self.caps.max_invariants} tests"})
            else:
                seen.add(file)
                kept.append(inv)
        return kept, dropped

    def do_base(self) -> None:
        self.begin("base")
        self.guard()
        snap = self.base_snap = self.runner.prepare(self.run.change)
        self.run.snapshots.append(snap)
        candidates = self.run.invariants
        pinned: list[Invariant] = []
        flaky: list[str] = []
        if candidates:
            first = self.tests("base", snap, candidates, 1)
            second = self.tests("base", snap, candidates, 2)
            for inv in candidates:
                a, b = first[inv.name], second[inv.name]
                self.run.base_results[inv.name] = [a, b]
                if a.passed and b.passed:
                    pinned.append(inv)
                elif a.passed or b.passed:
                    flaky.append(inv.name)
                    self.run.dropped.append({"name": inv.name, "reason": "flaky on base: green in only one of two runs"})
                else:
                    why = (a.output or b.output or "no output").strip().splitlines()[0][:200]
                    self.run.dropped.append({"name": inv.name, "reason": f"red on base: {why}"})
        # From here on run.invariants holds only tests proven green twice on base.
        self.run.invariants = pinned
        self.guard()
        self.run.own_suite_base = self.runner.run_own_suite(snap)
        self.event("base", "done", pinned=[i.name for i in pinned], flaky=flaky,
                   own_suite=suite_data(self.run.own_suite_base), checkpoint=snap.image)

    def do_head(self) -> None:
        self.begin("head")
        self.guard()
        snap = self.head_snap = self.runner.checkout_head(self.base_snap, self.run.change)
        self.run.snapshots.append(snap)
        pinned = self.run.invariants
        results = self.tests("head", snap, pinned) if pinned else {}
        self.run.head_results = results
        self.guard()
        self.run.own_suite_head = self.runner.run_own_suite(snap)
        self.run.flips = [Flip(inv, results[inv.name].output) for inv in pinned if not results[inv.name].passed]
        self.event("head", "done", flips=[f.invariant.name for f in self.run.flips],
                   own_suite=suite_data(self.run.own_suite_head), branch=snap.image)

    def do_judge(self) -> None:
        self.begin("judge")
        flips = self.run.flips
        if flips:
            try:
                judged = self.stages.judge_flips(self.client, self.run.intent, self.run.change, flips)
            except _cap_errors():
                raise
            except _model_errors() as exc:
                judged = [replace(f, kind="silent", reason=f"the judge was unavailable ({exc})") for f in flips]
            by_name = {f.invariant.name: f for f in judged}
            # A flip the judge did not answer for stays silent: fail closed.
            self.run.flips = [by_name.get(f.invariant.name) or replace(f, kind="silent", reason="the judge gave no verdict")
                              for f in flips]
            for f in self.run.flips:
                self.event("judge", "progress", name=f.invariant.name, kind=f.kind, reason=f.reason)
            self.guard()
        self.event("judge", "done", silent=[f.invariant.name for f in self.run.flips if f.kind == "silent"],
                   intended=[f.invariant.name for f in self.run.flips if f.kind == "intended"])

    def do_fix(self) -> None:
        targets = [f for f in self.run.flips if f.kind == "silent"][: self.caps.max_fixes]
        if not self.caps.fix or not targets:
            return
        self.begin("fix")
        intended = {f.invariant.name for f in self.run.flips if f.kind == "intended"}
        stop = _cap_errors()
        # A fix only adds to a verdict the evidence already decided, so a failure here is logged, not fatal.
        for flip in targets:
            name = flip.invariant.name
            try:
                self.guard()
                flip.location, flip.fix = self.stages.locate_and_propose(self.client, self.run.change, flip)
                if flip.fix is not None:
                    self.prove(flip, flip.fix, intended)
            except (RunnerError, *stop, *_model_errors()) as exc:
                self.event("fix", "error", name=name, message=str(exc))
                if isinstance(exc, stop):
                    break
                continue
            loc, fix = flip.location, flip.fix
            self.event("fix", "progress", name=name, file=fix.file if fix else (loc.file if loc else None),
                       line=loc.line if loc else None, proved=bool(fix and fix.proved))
        self.event("fix", "done", proved=[f.invariant.name for f in self.run.flips if f.fix and f.fix.proved])

    def prove(self, flip: Flip, fix: Fix, intended: set[str]) -> None:
        self.guard()
        snap = self.runner.apply_files(self.head_snap, {fix.file: fix.new_source})
        self.run.snapshots.append(snap)
        results = self.tests("fix", snap, self.run.invariants, progress=False)
        own = self.runner.run_own_suite(snap)
        name = flip.invariant.name
        fix.proved = bool(self.stages.fix_is_proven(name, self.run.head_results, intended, results,
                                                    self.run.own_suite_head, own))
        fix.evidence.update({"snapshot": snap.image, "target_green": results[name].passed,
                             "green_tests": sorted(n for n, r in results.items() if r.passed),
                             "own_suite": suite_data(own)})

    def do_seal(self) -> None:
        self.begin("seal")
        run = self.run
        run.sandbox_seconds = float(getattr(self.runner, "seconds", 0.0))
        run.models = list(getattr(self.client, "calls", []))
        if not self.aborted:
            run.verdict, run.reason = self.stages.decide(run)
        path = Path(self.stages.write_bundle(run, root=self.out_dir))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.event("seal", "done", verdict=run.verdict, reason=run.reason, sha256=digest, bundle=str(path))
