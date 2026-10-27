"""Pin stage: Nemotron Super writes characterization tests of the BASE behaviour.

The model never decides anything here. It proposes tests; this module throws out any that could do harm
outside the sandboxed assertion (network, files, clock, randomness) or that do not test what they claim.
"""
from __future__ import annotations

import posixpath
import re

from noether.model import Change, Invariant
from noether.nemotron import Client
from noether.prompt_util import clip, file_diff, js_sources, numbered

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
- Pin BEHAVIOUR, not configuration. Every test must call the code and observe what it does. Never write a test that only reads a constant or an exported value and compares it to a literal: that checks a number, not a behaviour, and such tests are rejected.
- Aim at what the changed lines influence, including through the related modules shown (callers, data, recorded inputs). A change is often only visible after many calls: drive the public API over several steps or inputs and assert on the outcome.
- Prefer properties the BASE code guarantees over exact numbers you cannot compute by hand: conserved quantities (a value that stays the same across steps), bounds, monotonic trends, round trips, symmetry, idempotence, and the outcomes of any recorded inputs, examples or fixtures the repo ships (for example, a recorded run that finishes). Use exact values only when you can derive them from the BASE source with certainty.
- Cover every range listed under "BASE lines this pull request rewrites". For each range, find what the code there decides (a branch, a guard, a default, an ordering, a clamp, which of several candidates wins) and drive BOTH sides of that decision: the input where a guard holds and the input where it does not. A rewrite that drops or flips a guard is the change a repo's own tests miss, and only a check that reaches the other side of the guard sees it.
- The title names the change the author knows about, and an announced change cannot be a silent one. Spend at most a third of the checks on what the title mentions; put the rest on the other behaviour of the rewritten ranges and of the code around them.
- Probe edges, not only typical values: just below, at and just above every limit, unit boundary or cap; the far end of every option (the largest attempt number, the empty input, a page past the end); and options used together. Where code rounds, floors, ceils or truncates, use inputs that land just below, on and just above the half-way or whole point (a price like 19.99 at 15 percent), because round numbers hide the difference. A guarantee stated in a BASE comment or docstring ("never", "always", "at most", "is empty rather than an error") is a contract: write a check that tries to break it at its edge.
- Make candidates distinguishable. When the code picks one of several (the first or the last duplicate, the smaller or the larger, which side wins a tie), give the candidates different identities (objects with other fields, strings that differ in case) so an assertion can tell which one was picked.
- A change often touches only some inputs, and one hand-picked example misses it. A test may loop over a small table of 5 to 12 varied inputs (short and long, with digits, with capitals, with repeats, with the odd second letter) as long as it asserts one claim.
- Mix: at least half of the tests must exercise behaviour across several calls or steps; the rest may be single-call checks of changed functions.
- One behavioural claim per test, small inputs, no snapshots of large outputs.
- Each test is its own ESM file run by node:test. Start it with exactly:
  import test from 'node:test';
  import assert from 'node:assert/strict';
- Import code only from the files shown (changed or related), by a relative path from .noether/pinned/<name>.test.mjs, so a file src/x.js is imported as '../../src/x.js'. Use exported symbols only; the exports are listed for each file.
- Deterministic and pure: no network, no file system, no clock, no randomness, no environment, no child processes, no require, no dynamic import.
- name: kebab-case, 3 to 60 characters, only a-z, 0-9 and '-'. Names must be unique.
- claim: one plain sentence a code reviewer understands, such as "formatPrice rounds half up to two decimals".
- target_file is the repo-relative path of the file under test, target_symbol the exported symbol it exercises.
- Write as many distinct checks as the cap allows when the code supports them (at least 6 for any function with branches); each should probe a different class of input, and none should repeat another. Return only the JSON object {"invariants": [...]}."""


def exports_of(source: str) -> list[str]:
    names = _EXPORT_DECL.findall(source)
    for group in _EXPORT_LIST.findall(source):
        names += [part.split(" as ")[-1].strip() for part in group.split(",") if part.strip()]
    if re.search(r"^\s*export\s+default\b", source, re.M):
        names.append("default")
    return sorted(set(names))


def pinnable_paths(change: Change) -> dict[str, str]:
    """path -> BASE source for every file a check may import: changed JS files plus their related files."""
    paths = {f.path: f.base_source for f in js_sources(change, "base")}
    for path, source in change.related.items():
        paths.setdefault(path, source)
    return paths


_IMPORT_CLAUSE = re.compile(r"""\bimport\s+([^'";]+?)\s+from\s*['"](?!node:)[^'"]+['"]""")


def _imported_names(code: str) -> tuple[set[str], set[str]]:
    """(plain names, namespace names) bound by imports of repo modules."""
    names, namespaces = set(), set()
    for clause in _IMPORT_CLAUSE.findall(code):
        if m := re.search(r"\*\s+as\s+([A-Za-z_$][\w$]*)", clause):
            namespaces.add(m.group(1))
        if m := re.search(r"\{([^}]*)\}", clause):
            names |= {part.split(" as ")[-1].strip() for part in m.group(1).split(",") if part.strip()}
        if m := re.match(r"\s*([A-Za-z_$][\w$]*)\s*(?:,|$)", clause):
            names.add(m.group(1))
    return names, namespaces


def _calls_imported_code(code: str) -> bool:
    """A check that never calls repo code is only comparing a value it read, not a behaviour."""
    names, namespaces = _imported_names(code)
    for n in names:
        if re.search(rf"(?<![\w$.]){re.escape(n)}(?:\.[\w$]+)*\s*\(", code):
            return True
    return any(re.search(rf"(?<![\w$.]){re.escape(n)}(?:\.[\w$]+)+\s*\(", code) for n in namespaces)


def build_pin_messages(change: Change, max_items: int | None = 12) -> list[dict]:
    parts = [f"Pull request title (context only, do not test what it announces; describe BASE): {change.title or '(none)'}",
             *([f"Write at most {max_items} tests."] if max_items else []), "", "Changed files with their BASE source:"]
    room = MAX_PROMPT_CHARS
    for f in js_sources(change, "base"):
        source = clip(f.base_source, min(MAX_SOURCE_CHARS, max(room, 0)))
        exports = ", ".join(exports_of(f.base_source)) or ("none found as ES exports; if the file uses "
                                                           "module.exports, import its default and read properties")
        # Only BASE text goes in: with the head side in view, models describe the new behaviour.
        ranges = base_ranges(file_diff(change.diff, f.path)) or "unknown"
        parts += ["", f"### {f.path} ({f.status})", f"Exports: {exports}",
                  f"BASE lines this pull request rewrites: {ranges}",
                  "BASE source (line numbers on the left are not part of the code):", "```js", numbered(source), "```"]
        room -= len(source)
    if change.related:
        parts += ["", "Related unchanged files (BASE source). The change is felt through these: callers, data, recorded inputs."]
        for path, text in change.related.items():
            if room <= 0:
                break
            source = clip(text, min(MAX_SOURCE_CHARS, room))
            exports = ", ".join(exports_of(text)) or "none found as ES exports"
            parts += ["", f"### {path} (unchanged)", f"Exports: {exports}", "BASE source:", "```js", source, "```"]
            room -= len(source)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def _norm_path(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


_BASE_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? ", re.M)


def base_ranges(file_patch: str) -> str:
    """'12-18, 40' style list of the BASE lines each hunk of one file's diff replaces."""
    out = []
    for start, length in _BASE_HUNK.findall(file_patch):
        a, n = int(start), int(length or 1)
        if n:
            out.append(f"{a}-{a + n - 1}" if n > 1 else str(a))
    return ", ".join(out)


def _add_missing_imports(code: str, change: Change, target: str) -> str:
    """Models often call an export of the target file without importing it; add the import line."""
    source = pinnable_paths(change).get(target)
    if source is None:
        return code
    names, namespaces = _imported_names(code)
    missing = [e for e in exports_of(source) if e != "default" and e not in names
               and re.search(rf"(?<![\w$.]){re.escape(e)}\b", code)
               and not re.search(rf"\b(?:const|let|var|function|class)\s+{re.escape(e)}\b", code)]
    if not missing or namespaces:
        return code
    line = f"import {{ {', '.join(missing)} }} from '../../{target}';\n"
    anchor = _NODE_ASSERT.search(code)
    if not anchor:
        return line + code
    end = code.find("\n", anchor.end())
    end = len(code) if end < 0 else end + 1
    return code[:end] + line + code[end:]


def _tidy(item: dict, change: Change | None = None) -> dict:
    """Undo the two slips models make most: a name that is not kebab-case, and a target_file written
    as the import path ('../../src/x.js') instead of the repo path ('src/x.js')."""
    out = dict(item)
    if isinstance(out.get("name"), str):
        out["name"] = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", out["name"].lower())).strip("-")[:60]
    target = out.get("target_file")
    if isinstance(target, str) and target.startswith("."):
        resolved = posixpath.normpath(posixpath.join(PINNED_DIR, target.replace("\\", "/")))
        if not resolved.startswith(".."):
            out["target_file"] = resolved
    if change is not None and isinstance(out.get("test_code"), str) and isinstance(out.get("target_file"), str):
        out["test_code"] = _add_missing_imports(out["test_code"], change, _norm_path(out["target_file"]))
    return out


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
    allowed = pinnable_paths(change)
    for spec in _IMPORTED.findall(code):
        if spec in ("node:test", "node:assert/strict"):
            continue
        if posixpath.normpath(posixpath.join(PINNED_DIR, spec)) not in allowed:
            return f"imports {spec}, only the changed and related files are allowed"
    if not any(args.strip() not in ("", "true", "1") for args in _ASSERT_CALL.findall(code)):
        return "empty or missing assert"
    if not _calls_imported_code(code):
        return "only reads a value; a check must call the code"
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
        if isinstance(item, dict):
            item = _tidy(item, change)
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


# Do not offer a way out ("leave a check out") or a cap ("at most N tests") here: given either, Super answered
# {"invariants": []} to every repair on Hopper (8 tokens), and every red check was dropped unread.
REPAIR_NOTE = """These checks ran against the BASE code in a sandbox and failed. A characterization check must pass on BASE, so each failure means the check is wrong, not the code.
Return a corrected version of EVERY check below, each with the SAME name. Read the failure output to see what BASE really does, then fix imports, how state or inputs are built, the expected value, or the claim.
When the output shows the value BASE produced and it is a stable result of BASE (not time or randomness), the expected value may adopt it. Keep the check aimed at the behaviour its name describes, and rewrite the claim so it is true of what the assertion now checks.
Return only {"invariants": [...]} with exactly one entry per check below."""


def repair_invariants(client: Client, change: Change, failures: list[tuple[Invariant, str]],
                      max_output: int = 1500) -> tuple[list[Invariant], list[dict]]:
    """One repair call for checks that were red on BASE. Returns (fixed, dropped); fixed keep their names."""
    if not failures:
        return [], []
    wanted = {inv.name for inv, _ in failures}
    messages = build_pin_messages(change, None)
    lines = [REPAIR_NOTE, ""]
    for inv, output in failures:
        lines += [f"### {inv.name}", f"claim: {inv.claim}", f"target_file: {inv.target_file}",
                  "```js", inv.test_code, "```", "Failure on BASE:", "```", clip(output.strip(), max_output), "```", ""]
    messages[1]["content"] += "\n\n" + "\n".join(lines)
    data = client.chat_json("pin", messages, INVARIANT_SCHEMA)
    fixed: list[Invariant] = []
    dropped: list[dict] = []
    for item in data["invariants"]:
        if not isinstance(item, dict):
            continue
        item = _tidy(item, change)
        name = item.get("name", "?")
        if name not in wanted or any(f.name == name for f in fixed):
            continue
        reason = validate_invariant(item, change)
        if reason:
            dropped.append({"name": name, "reason": f"repair rejected: {reason}"})
            continue
        fixed.append(Invariant(name=name, claim=item["claim"].strip(), target_file=_norm_path(item["target_file"]),
                               target_symbol=item["target_symbol"], test_code=item["test_code"]))
    return fixed, dropped
