"""Seal stage: turn a finished Run into the proof bundle (canonical JSON + sha256) the web cockpit reads."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from noether import __version__
from noether.model import ModelCall, Run, SuiteResult
from noether.nemotron import MODELS
from noether.verdict import base_status

# USD per 1M tokens: (input, output).
# shortcut: estimate, confirm on the pricing page (tokenfactory.nebius.com/organization/prices needs a
# signed-in browser, so these could not be read). Only the cost line in the bundle depends on them.
PRICES_PER_M: dict[str, tuple[float, float]] = {
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
}
_SECRET_ENV = ("NEBIUS_API_KEY", "TAVILY_API_KEY", "GITHUB_TOKEN", "CONTREE_TOKEN")
_RUN_ID = re.compile(r"[\w.-]+")


def cost_estimate(calls: list[ModelCall]) -> float:
    total = 0.0
    for c in calls:
        price_in, price_out = PRICES_PER_M.get(c.model, PRICES_PER_M[MODELS["judge"]])  # unknown model: priciest
        total += (c.tokens_in * price_in + c.tokens_out * price_out) / 1_000_000
    return round(total, 6)


def _canonical(bundle: dict) -> bytes:
    return json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(bundle: dict) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in bundle.items() if k != "sha256"})).hexdigest()


def _suite(s: SuiteResult | None) -> dict | None:
    return None if s is None else {"ran": s.ran, "exit_code": s.exit_code, "passed": s.passed, "failed": s.failed}


def _invariants(run: Run) -> list[dict]:
    flips = {f.invariant.name: f for f in run.flips}
    out = []
    for inv in run.invariants:
        base = base_status(run, inv.name)
        head = run.head_results.get(inv.name)
        flip = flips.get(inv.name)
        if base != "pass":
            kind = "dropped"
            failed = next((r for r in run.base_results.get(inv.name, []) if not r.passed), None)
            output = failed.output if failed else ""
        else:
            kind = flip.kind if flip else "held"
            output = flip.head_output if flip else (head.output if head and not head.passed else "")
        out.append({"name": inv.name, "claim": inv.claim, "target_file": inv.target_file,
                    "target_symbol": inv.target_symbol, "test_code": inv.test_code, "base": base,
                    "head": None if head is None else ("pass" if head.passed else "fail"),
                    "kind": kind, "output": output})
    return out


def _dropped(run: Run, invariants: list[dict]) -> list[dict]:
    late = [{"name": i["name"], "reason": f"{i['base']} on base"} for i in invariants if i["kind"] == "dropped"]
    return [dict(d) for d in run.dropped] + late


def _breaks(run: Run) -> list[dict]:
    out = []
    for f in run.flips:
        if f.kind != "silent":
            continue
        loc, fix = f.location, f.fix
        out.append({"invariant": f.invariant.name,
                    "file": loc.file if loc else f.invariant.target_file,
                    "line": loc.line if loc else None,
                    "code": loc.code if loc else "",
                    "why": loc.why if loc else f.reason,
                    # A fix that was not proven on its own branch is never shown.
                    "fix": {"file": fix.file, "diff": fix.diff, "proved": True} if fix and fix.proved else None})
    return out


def _intent(run: Run) -> dict | None:
    i = run.intent
    if i is None:
        return None
    return {"summary": i.summary, "intended_changes": list(i.intended_changes),
            "dependency_bumps": [{"name": b.name, "old": b.old, "new": b.new, "notes": list(b.notes)}
                                 for b in i.dependency_bumps]}


def _redact(bundle: dict) -> dict:
    """Belt and braces: no secret from this process's environment may reach a file."""
    text = json.dumps(bundle, ensure_ascii=False)
    for name in _SECRET_ENV:
        secret = os.environ.get(name, "")
        if len(secret) >= 8:
            text = text.replace(secret, "[redacted]")
    return json.loads(text)


def to_bundle(run: Run) -> dict:
    c = run.change
    invariants = _invariants(run)
    bundle = {
        "noether": __version__,
        "run_id": run.run_id,
        "repo": c.repo,
        "pr": {"url": c.pr_url, "title": c.title},
        "base": {"ref": c.base_ref, "sha": c.base_sha},
        "head": {"ref": c.head_ref, "sha": c.head_sha},
        "verdict": run.verdict,
        "reason": run.reason,
        "intent": _intent(run),
        "invariants": invariants,
        "dropped": _dropped(run, invariants),
        "breaks": _breaks(run),
        "own_suite": {"base": _suite(run.own_suite_base), "head": _suite(run.own_suite_head)},
        "sandbox": {"snapshots": [{"label": s.label, "image": s.image} for s in run.snapshots],
                    "seconds": run.sandbox_seconds},
        "models": [{"role": m.role, "model": m.model, "tokens_in": m.tokens_in, "tokens_out": m.tokens_out,
                    "ms": m.ms} for m in run.models],
        "cost_est_usd": cost_estimate(run.models),
        "timeline": [{"t_ms": e.t_ms, "stage": e.stage, "type": e.type,
                      "data": json.loads(json.dumps(e.data, default=str))} for e in run.timeline],
    }
    bundle = _redact(bundle)
    bundle["sha256"] = _digest(bundle)
    return bundle


def verify_bundle(bundle: dict) -> bool:
    return isinstance(bundle.get("sha256"), str) and bundle["sha256"] == _digest(bundle)


def write_bundle(run: Run, root: str = "runs") -> Path:
    if not _RUN_ID.fullmatch(run.run_id) or run.run_id in (".", ".."):
        raise ValueError(f"run id {run.run_id!r} is not safe to use as a folder name")
    path = Path(root) / run.run_id / "bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_bundle(run), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path
