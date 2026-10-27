"""Pin stage: Nemotron Super writes characterization tests of the BASE behaviour.

The model never decides anything here. It proposes tests; this module throws out any that could do harm
outside the sandboxed assertion (network, files, clock, randomness) or that do not test what they claim.
"""
from __future__ import annotations

import posixpath
import re

from noether.model import Change, Invariant
from noether.nemotron import Client
from noether.prompt_util import clip, file_diff, hunk_ranges, js_sources

PINNED_DIR = ".noether/pinned"
MAX_TEST_CHARS = 6000
MAX_SOURCE_CHARS = 12000
MAX_DIFF_CHARS = 4000
MAX_PROMPT_CHARS = 50000
NAME_RE = re.compile(r"[a-z0-9-]{3,60}")

# The test runs inside the sandbox next to repo code we did not write: keep it a pure function check.
FORBIDDEN = {
    "child_process": re.compile(r"child_process"),
    "fs": re.compile(r"""['"](?:node:)?fs(?:/promises)?['"]"""),
    "network module": re.compile(r"""['"](?:node:)?(?:net|http|https|http2|dgram|dns|tls)['"]"""),
    "worker_threads": re.compile(r"worker_threads"),
    "fetch": re.compile(r"\bfetch\s*\("),
    "process.env": re.compile(r"\bprocess\.env\b"),
    "eval": re.compile(r"\beval\s*\("),
    "Function constructor": re.compile(r"\bFunction\s*\("),
    "require": re.compile(r"\brequire\s*\("),
    "dynamic import": re.compile(r"\bimport\s*\("),
    "clock or randomness": re.compile(r"Math\.random|Date\.now|performance\.now|new\s+Date\s*\(\s*\)"),
}
_IMPORTED = re.compile(r"""(?:\bfrom\s*|\bimport\s*)['"]([^'"]+)['"]""")
_ASSERT_CALL = re.compile(r"\bassert(?:\.\w+)?\s*\(([^)]*)\)")
_NODE_TEST = re.compile(r"""\bfrom\s*['"]node:test['"]""")
_NODE_ASSERT = re.compile(r"""\bfrom\s*['"]node:assert/strict['"]""")
_EXPORT_DECL = re.compile(r"^\s*export\s+(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.M)
_EXPORT_LIST = re.compile(r"^\s*export\s*\{([^}]*)\}", re.M)

INVARIANT_SCHEMA = {
    "type": "object",
    "properties": {
        "invariants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},  # kebab-case [a-z0-9-]{3,60}, checked per item so one bad name drops one test
                    "claim": {"type": "string"},
                    "target_file": {"type": "string"},
                    "target_symbol": {"type": "string"},
                    "test_code": {"type": "string"},
                },
                "required": ["name", "claim", "target_file", "target_symbol", "test_code"],
            },
        }
    },
    "required": ["invariants"],
}

SYSTEM = """You write characterization tests for JavaScript code. A characterization test records what the BASE version of the code does today, so that a later change which silently alters it can be caught.

Rules:
- Describe BASE behaviour exactly as the BASE source shows it. The pull request title is context only: do not test the new behaviour it announces.
- Prefer behaviours the diff touches, but always assert what the BASE code does, with expected values you worked out by reading the BASE source. Never guess a value.
- One behavioural claim per test, one to three asserts, small inputs, no snapshots of large outputs.
- Each test is its own ESM file run by node:test. Start it with exactly:
  import test from 'node:test';
  import assert from 'node:assert/strict';
- Import the code under test only by a relative path from .noether/pinned/<name>.test.mjs, so a file src/x.js is imported as '../../src/x.js'. Use exported symbols only; the list of exports is given for each file.
- Deterministic and pure: no network, no file system, no clock, no randomness, no environment, no child processes, no require, no dynamic import.
- name: kebab-case, 3 to 60 characters, only a-z, 0-9 and '-'. Names must be unique.
- claim: one plain sentence a code reviewer understands, such as "formatPrice rounds half up to two decimals".
- target_file is the repo-relative path of the file under test, target_symbol the exported symbol it exercises.
- Fewer good tests beat many weak ones. Return only the JSON object {"invariants": [...]}."""


def exports_of(source: str) -> list[str]:
    names = _EXPORT_DECL.findall(source)
    for group in _EXPORT_LIST.findall(source):
        names += [part.split(" as ")[-1].strip() for part in group.split(",") if part.strip()]
    if re.search(r"^\s*export\s+default\b", source, re.M):
        names.append("default")
    return sorted(set(names))


def pinnable_paths(change: Change) -> dict[str, str]:
    """path -> BASE source for every changed JavaScript file with behaviour to describe."""
    return {f.path: f.base_source for f in js_sources(change, "base")}


def build_pin_messages(change: Change, max_items: int = 12) -> list[dict]:
    parts = [f"Pull request title (context only, do not test what it announces; describe BASE): {change.title or '(none)'}",
             f"Write at most {max_items} tests.", "", "Changed files with their BASE source:"]
    room = MAX_PROMPT_CHARS
    for f in js_sources(change, "base"):
        source = clip(f.base_source, min(MAX_SOURCE_CHARS, max(room, 0)))
        exports = ", ".join(exports_of(f.base_source)) or ("none found as ES exports; if the file uses "
                                                           "module.exports, import its default and read properties")
        diff = clip(file_diff(change.diff, f.path), MAX_DIFF_CHARS)
        parts += ["", f"### {f.path} ({f.status})", f"Exports: {exports}",
                  f"Changed line ranges on the head side: {hunk_ranges(f)}"]
        if diff:
            parts += ["Diff:", "```diff", diff, "```"]
        parts += ["BASE source:", "```js", source, "```"]
        room -= len(source) + len(diff)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def _norm_path(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


def validate_invariant(item: dict, change: Change, seen: set[str] | None = None) -> str | None:
    """Why this proposed test must be dropped, or None when it can go to the sandbox."""
    if not isinstance(item, dict):
        return "not an object"
    fields = {}
    for key in ("name", "claim", "target_file", "target_symbol", "test_code"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"missing {key}"
        fields[key] = value
    name, code = fields["name"], fields["test_code"]
    if not NAME_RE.fullmatch(name):
        return "bad name (need kebab-case, 3 to 60 characters)"
    if seen is not None and name in seen:
        return "duplicate name"
    target = _norm_path(fields["target_file"])
    base = pinnable_paths(change).get(target)
    if base is None:
        return f"unknown target file {fields['target_file']}"
    symbol = fields["target_symbol"]
    if symbol != "default" and not re.search(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])", base):
        return f"symbol {symbol} is not in the base source"
    if len(code) > MAX_TEST_CHARS:
        return f"test code over {MAX_TEST_CHARS} characters"
    for label, pattern in FORBIDDEN.items():
        if pattern.search(code):
            return f"forbidden API: {label}"
    if not _NODE_TEST.search(code):
        return "missing node:test import"
    if not _NODE_ASSERT.search(code):
        return "missing node:assert/strict import"
    for spec in _IMPORTED.findall(code):
        if spec in ("node:test", "node:assert/strict"):
            continue
        if posixpath.normpath(posixpath.join(PINNED_DIR, spec)) != target:
            return f"imports {spec}, only the target module is allowed"
    if not any(args.strip() not in ("", "true", "1") for args in _ASSERT_CALL.findall(code)):
        return "empty or missing assert"
    return None


def pin_invariants(client: Client, change: Change, max_items: int = 12) -> tuple[list[Invariant], list[dict]]:
    """Ask Super for tests; return (kept, dropped). dropped items are {"name", "reason"}."""
    if not pinnable_paths(change):
        return [], []
    data = client.chat_json("pin", build_pin_messages(change, max_items), INVARIANT_SCHEMA)
    kept: list[Invariant] = []
    dropped: list[dict] = []
    seen: set[str] = set()
    for item in data["invariants"]:
        name = item.get("name", "?") if isinstance(item, dict) else "?"
        if len(kept) >= max_items:
            dropped.append({"name": name, "reason": f"over the cap of {max_items} tests"})
            continue
        reason = validate_invariant(item, change, seen)
        if reason:
            dropped.append({"name": name, "reason": reason})
            continue
        seen.add(item["name"])
        kept.append(Invariant(name=item["name"], claim=item["claim"].strip(),
                              target_file=_norm_path(item["target_file"]), target_symbol=item["target_symbol"],
                              test_code=item["test_code"]))
    return kept, dropped
