"""Small text helpers the prompt builders share."""
from __future__ import annotations

import re

from noether.model import Change, ChangedFile

JS_SUFFIXES = (".js", ".mjs", ".cjs")
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__)/|\.(test|spec)\.[cm]?js$")


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [clipped]"


def numbered(source: str) -> str:
    """Source with 1-based line numbers, so a model can name a line without counting."""
    return "\n".join(f"{i:>4}| {line}" for i, line in enumerate(source.split("\n"), 1))


def file_diff(diff: str, path: str) -> str:
    """The part of a `git diff` that belongs to one file ('' when it is not in the diff)."""
    for part in re.split(r"(?m)^(?=diff --git )", diff):
        if part.split("\n", 1)[0].endswith(f" b/{path}"):
            return part
    return ""


def js_sources(change: Change, side: str) -> list[ChangedFile]:
    """Changed JavaScript files that are not tests and have source on the given side ('base' or 'head')."""
    attr = f"{side}_source"
    return [f for f in change.files
            if getattr(f, attr) is not None and f.path.endswith(JS_SUFFIXES) and not _TEST_PATH.search(f.path)]


def hunk_ranges(f: ChangedFile) -> str:
    return ", ".join(f"{h.start}-{h.start + max(h.length, 1) - 1}" for h in f.hunks) or "none"
