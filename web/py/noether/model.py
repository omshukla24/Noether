"""Data passed between pipeline stages, and the shape of the proof bundle.

Every stage takes and returns these plain dataclasses. `bundle.py` turns a
finished `Run` into canonical JSON; the web cockpit reads the same JSON, so a
field renamed here must be renamed in `web/` too.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

Verdict = Literal["BROKEN", "CONSERVED", "INCONCLUSIVE"]
Stage = Literal["ingest", "intent", "pin", "base", "head", "judge", "fix", "seal"]


@dataclass
class Hunk:
    """Head-side line range of one diff hunk (1-based, inclusive start)."""
    start: int
    length: int


@dataclass
class ChangedFile:
    path: str
    status: Literal["added", "modified", "removed", "renamed"]
    hunks: list[Hunk] = field(default_factory=list)
    base_source: str | None = None
    head_source: str | None = None


@dataclass
class Change:
    """One base..head change to check. `source` says where the code comes from:
    "github" (owner/name tarballs) or "local" (a fixture folder with base/ and head/)."""
    repo: str
    base_ref: str
    head_ref: str
    title: str = ""
    body: str = ""
    diff: str = ""
    files: list[ChangedFile] = field(default_factory=list)
    base_sha: str = ""
    head_sha: str = ""
    pr_url: str = ""
    source: Literal["github", "local"] = "github"
    local_dir: str = ""
    related: dict[str, str] = field(default_factory=dict)  # unchanged path -> BASE source, see related.py


@dataclass
class DepBump:
    name: str
    old: str
    new: str
    notes: list[str] = field(default_factory=list)  # Tavily findings, one line each


@dataclass
class Intent:
    summary: str
    intended_changes: list[str]
    dependency_bumps: list[DepBump] = field(default_factory=list)


@dataclass
class Invariant:
    name: str
    claim: str
    target_file: str
    target_symbol: str
    test_code: str


@dataclass
class TestResult:
    name: str
    passed: bool
    output: str = ""  # failure message, truncated to a few KB
    ms: float = 0.0


@dataclass
class SuiteResult:
    """The repo's own test suite. `ran` is False when the repo has none.
    `exit_code` decides pass/fail; the counts are best effort from the output."""
    ran: bool
    exit_code: int = 0
    passed: int = 0
    failed: int = 0
    output: str = ""


@dataclass
class Location:
    file: str
    line: int
    code: str
    why: str


@dataclass
class Fix:
    file: str
    new_source: str
    diff: str  # unified diff against head, for display only
    proved: bool
    evidence: dict[str, Any] = field(default_factory=dict)


FlipKind = Literal["intended", "silent"]


@dataclass
class Flip:
    """A pinned invariant that was green on base and red on head."""
    invariant: Invariant
    head_output: str
    kind: FlipKind = "silent"  # fail closed until the judge says otherwise
    reason: str = ""
    location: Location | None = None
    fix: Fix | None = None


@dataclass
class ModelCall:
    role: str
    model: str
    tokens_in: int
    tokens_out: int
    ms: float


@dataclass
class Snapshot:
    """A saved sandbox state. For Nebius Sandboxes `image` is the image uuid of
    the checkpoint; branches are new runs started from it."""
    image: str
    label: str
    workdir: str = "/w/repo"


@dataclass
class Event:
    """One stage event. Streamed to the CLI, the API (SSE) and kept in the bundle."""
    t_ms: int
    stage: Stage
    type: Literal["start", "progress", "done", "error"]
    data: dict[str, Any] = field(default_factory=dict)


Emit = Callable[[Event], None]


class Runner(Protocol):
    """Executes repo code. Real repos only ever run in `ContreeRunner`."""

    def prepare(self, change: Change) -> Snapshot:
        """Fetch BASE, install dependencies once, return the checkpoint."""

    def checkout_head(self, base: Snapshot, change: Change) -> Snapshot:
        """Branch from the base checkpoint and move the working tree to HEAD."""

    def apply_files(self, snap: Snapshot, files: dict[str, str]) -> Snapshot:
        """Branch from `snap` with whole files replaced (repo-relative path -> text).
        Whole files, not a diff: the sandbox image has neither git nor patch."""

    def run_tests(self, snap: Snapshot, tests: list[Invariant]) -> list[TestResult]:
        """Write each invariant to `.noether/pinned/<name>.test.mjs` and run them."""

    def run_module(self, snap: Snapshot, files: dict[str, str], entry: str) -> str:
        """Write `files` to `.noether/pinned/` and run `entry` with node; the combined output."""

    def run_own_suite(self, snap: Snapshot) -> SuiteResult:
        """Run the repo's own `npm test` (or nothing if it has no test script)."""


@dataclass
class Run:
    """Everything a run learned. `bundle.to_bundle` serialises this."""
    run_id: str
    change: Change
    verdict: Verdict = "INCONCLUSIVE"
    reason: str = ""
    intent: Intent | None = None
    invariants: list[Invariant] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)  # {name, reason}
    base_results: dict[str, list[TestResult]] = field(default_factory=dict)  # name -> 2 runs
    head_results: dict[str, TestResult] = field(default_factory=dict)
    flips: list[Flip] = field(default_factory=list)
    own_suite_base: SuiteResult | None = None
    own_suite_head: SuiteResult | None = None
    snapshots: list[Snapshot] = field(default_factory=list)
    sandbox_seconds: float = 0.0
    models: list[ModelCall] = field(default_factory=list)
    timeline: list[Event] = field(default_factory=list)
