"""Intent stage: what does this pull request say it changes?

Dependency bumps come from package.json in code. Tavily release notes are an extra input only: a failed
search never fails a run.
"""
from __future__ import annotations

import json
import re

import httpx

from noether.model import Change, DepBump, Intent
from noether.nemotron import Client
from noether.prompt_util import clip

TAVILY_URL = "https://api.tavily.com/search"
DEP_SECTIONS = ("dependencies", "devDependencies", "peerDependencies")
MAX_BUMPS_SEARCHED = 5
MAX_BODY_CHARS = 6000

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "intended_changes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "intended_changes"],
}

SYSTEM = """You read a pull request and state which behaviour changes it announces.

Return a JSON object with:
- summary: at most two plain sentences on what the pull request does.
- intended_changes: the concrete, observable behaviour changes the title, body or release notes say or clearly imply, one sentence each, written about this pull request's own code (never copy wording from these instructions). Leave out refactors that keep behaviour. Use an empty list when the pull request claims no behaviour change.

Use only the text you are given. Never invent a change the text does not support."""


def _versions(source: str | None) -> dict[str, str]:
    """name -> version over all dependency sections; {} when the file is missing or not valid JSON
    (an unreadable package.json is the runner's problem: install will fail and the run ends INCONCLUSIVE)."""
    if not source:
        return {}
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for section in DEP_SECTIONS:
        deps = data.get(section) if isinstance(data, dict) else None
        if isinstance(deps, dict):
            out.update({k: v for k, v in deps.items() if isinstance(v, str)})
    return out


def detect_dep_bumps(change: Change) -> list[DepBump]:
    bumps: list[DepBump] = []
    for f in change.files:
        if f.path != "package.json" and not f.path.endswith("/package.json"):
            continue
        old, new = _versions(f.base_source), _versions(f.head_source)
        bumps += [DepBump(name, old[name], new[name]) for name in sorted(old.keys() & new.keys())
                  if old[name] != new[name]]
    return bumps


def tavily_notes(bump: DepBump, api_key: str, http: httpx.Client | None = None) -> list[str]:
    body = {"query": f"{bump.name} {bump.new} changelog breaking changes", "max_results": 5,
            "search_depth": "basic"}
    client = http or httpx.Client(timeout=20.0)
    try:
        resp = client.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return []
    finally:
        if http is None:
            client.close()
    notes = []
    for r in results[:5]:
        if not isinstance(r, dict):
            continue
        snippet = re.sub(r"\s+", " ", str(r.get("content", ""))).strip()[:240]
        notes.append(f"{str(r.get('title', '')).strip()}: {snippet} ({r.get('url', '')})")
    return notes


def build_intent_messages(change: Change, bumps: list[DepBump]) -> list[dict]:
    parts = [f"Title: {change.title or '(none)'}", "", "Body:", clip(change.body or "(empty)", MAX_BODY_CHARS)]
    for b in bumps:
        parts += ["", f"Dependency bump: {b.name} {b.old} -> {b.new}"] + [f"  note: {n}" for n in b.notes]
    # No diff: shown the code, Nano listed what the diff does as announced, and the judge then excused it.
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def read_intent(client: Client, change: Change, tavily_key: str | None = None,
                http: httpx.Client | None = None) -> Intent:
    bumps = detect_dep_bumps(change)
    if tavily_key:
        for bump in bumps[:MAX_BUMPS_SEARCHED]:
            bump.notes = tavily_notes(bump, tavily_key, http)
    data = client.chat_json("intent", build_intent_messages(change, bumps), INTENT_SCHEMA)
    return Intent(summary=data["summary"].strip(),
                  intended_changes=[c.strip() for c in data["intended_changes"] if c.strip()],
                  dependency_bumps=bumps)
