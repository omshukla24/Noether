"""Record stage: Nemotron Super picks INPUTS, the sandbox says what BASE does with them.

A predicted expected value is the weak point of a pinned check: one wrong guess drops a check even when its
input was the useful one. Here the model only writes a module of cases (inputs in, JSON-safe value out, no
assertions). The module runs on BASE in the sandbox, whatever BASE returns is recorded, and one pinned check
per input is generated with the recorded value as expected. Each still has to pass twice on BASE, so a case that
reads shared state or the clock is dropped like any flaky check; HEAD is measured the same way and a flip goes
to the judge. The model never decides anything: the values come from BASE.
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field

from noether.model import Change, Invariant
from noether.nemotron import Client, ModelError, extract_json
from noether.pin import (FORBIDDEN, MAX_PROMPT_CHARS, NAME_RE, PINNED_DIR, _add_missing_imports, base_ranges,
                         build_pin_messages, fix_import_paths, pinnable_paths)
from noether.prompt_util import clip, file_diff, js_sources

MAX_MODULE_CHARS = 12000
MAX_DIFF_CHARS = 4000
MARK = "@@NOETHER-RECORD "
MODULE_FILE = "_record.mjs"
HARNESS_FILE = "_record_run.mjs"

# Same canonical form on both sides: sorted keys, so a reordered object is not a change; NaN and Infinity read as null.
CANON = """const __canon = (v) => JSON.stringify(v, (_k, x) => x && typeof x === 'object' && !Array.isArray(x)
  ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x);"""

HARNESS = f"""import * as mod from './{MODULE_FILE}';
{CANON}
const out = {{}};
const list = Array.isArray(mod.cases) ? mod.cases.map((c, i) => [c.name ?? String(i), c.run ?? c.fn]) : Object.entries(mod.cases ?? {{}});
for (const [name, fn] of list) {{
  try {{
    const v = __canon(await fn());
    out[name] = v === undefined ? {{ ok: false, error: 'returned undefined, not a JSON-safe value' }} : {{ ok: true, value: v }};
  }} catch (e) {{
    out[name] = {{ ok: false, error: `${{e && e.name}}: ${{String((e && e.message) || e).slice(0, 300)}}` }};
  }}
}}
console.log({json.dumps(MARK)} + JSON.stringify(out));
"""

CASE_KEYS = ("name", "claim", "target_file", "target_symbol")
_FENCE = re.compile(r"```[ \t]*(?:js|javascript|mjs)?[ \t]*\n(.*?)```", re.S)


def parse_reply(text: str) -> tuple[str, list]:
    """(module, cases) from a reply made of a fenced code block and then a JSON list of case descriptions.
    Code in a fence, not in a JSON string, because models garble long escaped strings."""
    fence = _FENCE.search(text)
    if fence is None:
        raise ModelError("record: no ```js block with the module in the reply")
    rest = text[fence.end():]
    cases = extract_json(rest) if re.search(r"[\[{]", rest) else None
    if isinstance(cases, dict):
        cases = cases.get("cases")
    if not isinstance(cases, list):
        raise ModelError("record: no JSON list of cases after the module")
    return fence.group(1), cases


SYSTEM = """You choose test INPUTS for JavaScript code. You do not write expected values and you do not write assertions. Your cases are run on the BASE version of the code in a sandbox, whatever BASE returns is recorded, and the recording becomes a check: a later change that alters the result at one of your inputs is caught. So all that matters is that your inputs reach the behaviour a change could alter.

Reply with exactly two parts and nothing else: first the module in one ```js code block; then, after it, one JSON list in a ```json block with an entry {"name", "claim", "target_file", "target_symbol"} per case.

The module is one ES module:
- It may start with import statements from the files shown (changed or related), by a relative path from .noether/pinned/_record.mjs, so a file src/x.js is imported as '../../src/x.js'. Use exported symbols only; the exports are listed for each file. Do not import node:test or node:assert.
- It may define small helper functions and constants above the cases.
- It must end with `export const cases = { "<name>": () => <value>, ... };` One entry per input. Each entry is a function with no arguments that builds its own fresh inputs (never share mutable objects between entries), calls the code under test, and returns a JSON-safe value: numbers, strings, booleans, null, arrays, plain objects. Return only the few fields or numbers the input is meant to exercise, not a whole large state object.
- Put shared setup (a level, a config, a table) in helper functions above the cases that return a FRESH object on every call, and call them from the cases. Never paste the same large literal into several cases: the module is limited to 12000 characters.
- Behaviour that only shows after several calls or steps: loop inside the function and return the value after the last step, or a short list sampled along the way.
- Deterministic and pure: no network, no file system, no clock, no randomness, no environment, no child processes, no require, no dynamic import.
- The cases array lists one entry per key of `cases` with the same name: kebab-case, 3 to 60 characters, only a-z, 0-9 and '-', unique. claim: one plain sentence saying which input and what it exercises, such as "a price of 19.99 with a 15 percent discount". target_file is the repo-relative path of the file under test, target_symbol the exported symbol it exercises.

How to choose inputs:
- Cover every range listed under "BASE lines this pull request rewrites". For each range find what the code there decides (a branch, a guard, a default, an ordering, a clamp, which of several candidates wins) and give inputs on BOTH sides of that decision: where a guard holds and where it does not, in every state the guard looks at (on the ground and in the air, first and last item, empty and full).
- The unified diff of each changed file is shown: '-' lines are BASE, '+' lines are HEAD. For every hunk, find inputs on which the BASE lines and the HEAD lines could give different results: a guard that moved, vanished or changed side; a pattern, character class or branch that now covers more or fewer inputs; rounding, flooring or truncation that changed; a cap or clamp applied before instead of after another step; an order, tie-break or default that changed. When a character class, range, set or list changed, name each member it gained or lost and use inputs that put each one where the pattern looks. A pull request can also move code into a new function: then check the old public function everywhere the moved code decides something.
- The title names the change the author knows about. At most a third of the cases may be about what the title mentions; put the rest on the other behaviour of the rewritten ranges and the code around them.
- Probe edges: just below, at and just above every limit, unit boundary or cap; the empty input; the far end of every option; options used together. Where code rounds, floors, ceils or truncates, use inputs that land just below, on and just above the half-way or whole point (a price like 19.99 at 15 percent), because round numbers hide the difference.
- When the code picks one of several (first or last duplicate, smaller or larger, which side wins a tie), give the candidates different identities so the result tells which one was picked.
- Where a state matters (a flag, a counter, a mode), build each state separately and run the same step from each: one case per state.
- A table of varied inputs belongs in many cases, one per input: short and long, with digits, with capitals, with repeats. Many small cases beat a few large ones. Write as many distinct inputs as the cap allows."""

FEEDBACK_NOTE = """Your previous module is shown above with what happened when it ran on BASE. Return a corrected, complete module and cases list. Fix imports, how state or inputs are built, and anything that threw; keep the cases that worked, with the same names, and replace the ones that failed. Return only the JSON object."""


@dataclass
class Proposal:
    module: str
    cases: list[dict]
    dropped: list[dict] = field(default_factory=list)


def build_record_messages(change: Change, max_cases: int, previous: str = "", feedback: str = "") -> list[dict]:
    messages = build_pin_messages(change, None)
    messages[0] = {"role": "system", "content": SYSTEM}
    lines = [f"Write at most {max_cases} cases.", "",
             "The pull request title is context only, it names the change the author announced: " + (change.title or "(none)")]
    for f in js_sources(change, "base"):
        if patch := file_diff(change.diff, f.path):
            lines += ["", f"### Diff of {f.path} (BASE lines rewritten: {base_ranges(patch) or 'unknown'})",
                      "```diff", clip(patch, MAX_DIFF_CHARS), "```"]
    messages[1]["content"] = clip(messages[1]["content"], MAX_PROMPT_CHARS) + "\n\n" + "\n".join(lines)
    if previous:
        messages[1]["content"] += f"\n\n### Your previous module\n```js\n{previous}\n```\n{feedback}\n{FEEDBACK_NOTE}"
    return messages


_NODE_IMPORT = re.compile(r"""^[ \t]*import\b[^;\n]*['"]node:(?:test|assert)[^'"]*['"];?[ \t]*$""", re.M)
_CASES_EXPORT = re.compile(r"\bexport\s+(?:const\s+cases\b|\{[^}]*\bcases\b)")
_IMPORTED = re.compile(r"""(?:\bfrom\s*|\bimport\s*)['"]([^'"]+)['"]""")


def module_problem(module: str, change: Change) -> str | None:
    """Why the whole module cannot go to the sandbox, or None."""
    if not isinstance(module, str) or not module.strip():
        return "the module is empty"
    if len(module) > MAX_MODULE_CHARS:
        return f"the module is over {MAX_MODULE_CHARS} characters"
    for label, pattern in FORBIDDEN.items():
        if pattern.search(module):
            return f"forbidden API: {label}"
    if not _CASES_EXPORT.search(module):
        return "the module has no `export const cases = {...}`"
    allowed = pinnable_paths(change)
    for spec in _IMPORTED.findall(module):
        if posixpath.normpath(posixpath.join(PINNED_DIR, spec)) not in allowed:
            return f"imports {spec}, only the changed and related files are allowed"
    return None


def case_problem(item: dict, change: Change, seen: set[str]) -> str | None:
    if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip()
                                             for k in ("name", "claim", "target_file", "target_symbol")):
        return "incomplete case"
    if not NAME_RE.fullmatch(item["name"]):
        return "bad name (need kebab-case, 3 to 60 characters)"
    if item["name"] in seen:
        return "duplicate name"
    base = pinnable_paths(change).get(posixpath.normpath(item["target_file"].replace("\\", "/")))
    if base is None:
        return f"unknown target file {item['target_file']}"
    symbol = item["target_symbol"]
    if symbol != "default" and not re.search(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])", base):
        return f"symbol {symbol} is not in the base source"
    return None


def propose_cases(client: Client, change: Change, max_cases: int = 16, taken: set[str] | frozenset[str] = frozenset(),
                  previous: str = "", feedback: str = "") -> Proposal:
    """Ask Super for a module of cases. A module that cannot be run comes back with no cases and the reason."""
    if not pinnable_paths(change):
        return Proposal("", [])
    messages = build_record_messages(change, max_cases, previous, feedback)
    for attempt in range(2):
        reply = client.chat("pin", messages)
        try:
            module, listed = parse_reply(reply.text)
            break
        except ModelError as exc:
            if attempt:
                raise
            messages = messages + [{"role": "assistant", "content": reply.text},
                                   {"role": "user", "content": f"That reply was rejected: {exc}. Send both parts again."}]
    if "\n" not in module.rstrip("\n") and "\\n" in module:  # newlines sent as the two characters backslash and n
        module = module.rstrip("\n").replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    module = fix_import_paths(_NODE_IMPORT.sub("", module), change)

    for target in {posixpath.normpath(str(c.get("target_file", "")).replace("\\", "/")) for c in listed if isinstance(c, dict)}:
        module = _add_missing_imports(module, change, target)
    if problem := module_problem(module, change):
        return Proposal("", [], [{"name": "(module)", "reason": f"record rejected: {problem}"}])
    cases: list[dict] = []
    dropped: list[dict] = []
    seen = set(taken)
    for item in listed:
        name = item.get("name", "?") if isinstance(item, dict) else "?"
        if len(cases) >= max_cases:
            dropped.append({"name": name, "reason": f"over the cap of {max_cases} cases"})
        elif reason := case_problem(item, change, seen):
            dropped.append({"name": name, "reason": f"record rejected: {reason}"})
        else:
            seen.add(item["name"])
            cases.append({k: item[k].strip() if k == "claim" else item[k] for k in
                          ("name", "claim", "target_file", "target_symbol")})
    return Proposal(module, cases, dropped)


def runner_files(proposal: Proposal) -> dict[str, str]:
    return {MODULE_FILE: proposal.module, HARNESS_FILE: HARNESS}


def parse_recording(output: str) -> tuple[dict[str, dict], str]:
    """(results by case name, problem). The harness prints one marked line; no line means the module did not load."""
    line = next((ln for ln in reversed(output.splitlines()) if ln.startswith(MARK)), None)
    if line is None:
        return {}, "the module did not run: " + clip(output.strip() or "no output", 600)
    try:
        results = json.loads(line[len(MARK):])
    except ValueError:
        return {}, "the recording was not valid JSON"
    return (results, "") if isinstance(results, dict) else ({}, "the recording was not an object")


def check_code(module: str, name: str, claim: str, expected: str) -> str:
    """One pinned check: the module's own text, but only the one named case is run and compared with the recording."""
    return f"""import test from 'node:test';
import assert from 'node:assert/strict';
{CANON}
const __expected = {json.dumps(expected)};
test({json.dumps(claim)}, async () => {{
  const __case = cases[{json.dumps(name)}];
  const __actual = __canon(await __case());
  assert.ok(__actual === __expected, `recorded on BASE, now different.\\ninput: ${{String(__case).slice(0, 700)}}\\nBASE gave: ${{__expected}}\\nthis side gave: ${{__actual}}`);
}});
{module}
"""


def build_checks(proposal: Proposal, results: dict[str, dict]) -> tuple[list[Invariant], list[dict]]:
    """One Invariant per case BASE answered, plus the cases dropped (threw, returned nothing, or are missing)."""
    checks: list[Invariant] = []
    dropped: list[dict] = []
    for case in proposal.cases:
        got = results.get(case["name"])
        if not isinstance(got, dict) or not got.get("ok") or not isinstance(got.get("value"), str):
            why = got.get("error", "unknown") if isinstance(got, dict) else "the case is not in the module"
            dropped.append({"name": case["name"], "reason": f"record failed on base: {why}"})
            continue
        checks.append(Invariant(name=case["name"], claim=case["claim"], target_file=posixpath.normpath(case["target_file"]),
                                target_symbol=case["target_symbol"],
                                test_code=check_code(proposal.module, case["name"], case["claim"], got["value"])))
    return checks, dropped
