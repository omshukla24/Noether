"""Load eval cases from evals/cases/<name>/.

A case folder holds case.json {"expected": "BROKEN" | "CONSERVED", "note": "...", "fixture": optional}.
Without "fixture" the folder itself is the fixture (base/, head/, change.json). With it, the path (relative to the
case folder) points at a shared fixture such as fixtures/hopper.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evals.score import EXPECTED

CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    note: str
    fixture: Path


def load_case(folder: Path) -> Case:
    meta = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    if meta.get("expected") not in EXPECTED:
        raise ValueError(f"{folder.name}: expected must be one of {EXPECTED}")
    if not str(meta.get("note", "")).strip():
        raise ValueError(f"{folder.name}: a case needs a one-line note")
    fixture = (folder / meta["fixture"]).resolve() if meta.get("fixture") else folder
    for part in ("base", "head", "change.json"):
        if not (fixture / part).exists():
            raise ValueError(f"{folder.name}: fixture {fixture} is missing {part}")
    return Case(folder.name, meta["expected"], meta["note"].strip(), fixture)


def load_cases(names: list[str] | None = None, root: Path = CASES_DIR) -> list[Case]:
    folders = sorted(p for p in root.iterdir() if (p / "case.json").is_file())
    cases = [load_case(p) for p in folders]
    if names:
        unknown = sorted(set(names) - {c.name for c in cases})
        if unknown:
            raise ValueError(f"unknown case(s): {', '.join(unknown)}")
        cases = [c for c in cases if c.name in names]
    return cases
