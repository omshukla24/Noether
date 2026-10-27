"""Fix stage: where did a silent flip come from, and what is the smallest edit that undoes it?

The model proposes; this module only checks the proposal is well formed. A fix counts as proven later, when the
sandbox re-runs everything on a branch (verdict.fix_is_proven).
"""
from __future__ import annotations

import difflib

from noether.model import Change, ChangedFile, Fix, Flip, Location
from noether.nemotron import Client, ModelError
from noether.prompt_util import clip, file_diff, hunk_ranges, js_sources, numbered

MAX_DIFF_CHARS = 24000
MAX_SOURCE_CHARS = 14000
MAX_PROMPT_CHARS = 50000

LOCATE_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": "integer"},
        "code": {"type": "string"},
        "why": {"type": "string"},
        "search": {"type": "string"},
        "replace": {"type": "string"},
    },
    "required": ["file", "line", "code", "why", "search", "replace"],
}

SYSTEM = """A pull request silently broke a behaviour that the BASE code had. You get the failing test, the pull request diff and the HEAD source of the changed files, with line numbers.

Find the one line the pull request changed that causes the failure and propose the smallest edit that restores the BASE behaviour without undoing what the pull request set out to do.

Return a JSON object:
- file: repo-relative path of the changed file that holds the line.
- line: its line number in the HEAD source shown (the line must be one the diff added or changed).
- code: that line's text.
- why: one sentence on how this line breaks the behaviour.
- search: an exact, contiguous piece of the HEAD file, copied character for character, that appears exactly once in it. Include enough surrounding text to make it unique, and as little as possible otherwise.
- replace: the text that takes its place.

The edit must be small. Never touch tests."""


def _changed(change: Change, path: str) -> ChangedFile | None:
    return next((f for f in change.files if f.path == path and f.head_source is not None), None)


def validate_location(loc: Location, change: Change) -> bool:
    """The file is changed by the PR and the line sits inside one of its head-side hunks."""
    f = _changed(change, loc.file)
    if f is None or not f.hunks:
        return False
    return any(h.start <= loc.line < h.start + max(h.length, 1) for h in f.hunks)


def build_fix_messages(change: Change, flip: Flip) -> list[dict]:
    inv = flip.invariant
    parts = [f"Pull request title: {change.title or '(none)'}", "",
             f"Failing test: {inv.name}", f"Behaviour it protects: {inv.claim}", f"Test code:\n{inv.test_code}",
             f"Failure output on HEAD:\n{clip(flip.head_output, 2000)}", "",
             "Diff:", clip(change.diff, MAX_DIFF_CHARS), "", "HEAD source of changed files:"]
    room = MAX_PROMPT_CHARS
    for f in js_sources(change, "head"):
        source = clip(f.head_source, min(MAX_SOURCE_CHARS, max(room, 0)))
        parts += ["", f"### {f.path}", f"Changed lines on the head side: {hunk_ranges(f)}", numbered(source)]
        room -= len(source)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def _match_eol(snippet: str, source: str) -> str:
    return snippet.replace("\n", "\r\n") if "\r\n" in source and "\r\n" not in snippet else snippet


def _build_fix(path: str, head: str, search: str, replace: str) -> Fix | None:
    search, replace = _match_eol(search, head), _match_eol(replace, head)
    if not search or head.count(search) != 1 or search == replace:
        return None
    new = head.replace(search, replace, 1)
    diff = "".join(difflib.unified_diff(head.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}"))
    return Fix(file=path, new_source=new, diff=diff, proved=False)


def locate_and_propose(client: Client, change: Change, flip: Flip) -> tuple[Location | None, Fix | None]:
    """(location, fix). (None, None) when the model fails or names a file the PR did not change;
    (None, fix) when only the line is not in a changed hunk; (location, None) when the edit cannot be applied.
    Model failures end here as "no fix": a fix is optional, the verdict does not depend on it."""
    try:
        data = client.chat_json("fix", build_fix_messages(change, flip), LOCATE_FIX_SCHEMA)
    except ModelError:
        return None, None
    path = data["file"].strip().removeprefix("./")
    f = _changed(change, path)
    # Only code the model was shown: a README or package.json edit cannot restore a behaviour (no reinstall).
    if f is None or path not in {c.path for c in js_sources(change, "head")}:
        return None, None
    fix = _build_fix(f.path, f.head_source, data["search"], data["replace"])
    lines = f.head_source.split("\n")
    line = data["line"]
    # The model's quote must match the real line, or its line number is a guess.
    real = lines[line - 1] if 1 <= line <= len(lines) else None
    quote = data["code"].strip()
    if real is None or not quote or quote not in real:
        return None, fix
    loc = Location(file=f.path, line=line, code=real.strip(), why=data["why"].strip())
    return (loc if validate_location(loc, change) else None), fix
