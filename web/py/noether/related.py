"""Pick the unchanged files a pinned check needs to see.

A change to one module is usually felt through the modules that call it: Hopper's physics change only
shows up when replay.js steps the level with the recorded run. So the pin prompt gets the changed files
plus their importers and what those import, within a character budget.
"""
from __future__ import annotations

import posixpath
import re

JS_SUFFIXES = (".js", ".mjs", ".cjs")
_SKIP = re.compile(r"(^|/)(node_modules|dist|build|coverage|vendor|\.noether)/|\.min\.js$|(^|/)(test|tests|__tests__)/|\.(test|spec)\.[cm]?js$")
_SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]""")

MAX_RELATED_CHARS = 40000
MAX_RELATED_FILES = 12


def is_candidate(path: str) -> bool:
    return path.endswith(JS_SUFFIXES) and not _SKIP.search(path)


def imports_of(path: str, source: str, known: set[str]) -> set[str]:
    """Repo paths a file imports by relative specifier, resolved against the files we know about."""
    found = set()
    folder = posixpath.dirname(path)
    for spec in _SPEC.findall(source):
        target = posixpath.normpath(posixpath.join(folder, spec))
        for option in (target, *(target + s for s in JS_SUFFIXES), target + "/index.js"):
            if option in known:
                found.add(option)
                break
    return found


def pick_related(changed: list[str], sources: dict[str, str],
                 max_chars: int = MAX_RELATED_CHARS, max_files: int = MAX_RELATED_FILES) -> dict[str, str]:
    """path -> source for unchanged files ranked by how close they sit to the change in the import graph."""
    known = set(sources) | set(changed)
    changed_set = set(changed)
    graph = {p: imports_of(p, s, known) for p, s in sources.items()}
    importers = {p for p, deps in graph.items() if deps & changed_set and p not in changed_set}
    used = set().union(*(graph.get(p, set()) for p in importers | changed_set)) - changed_set
    folders = {posixpath.dirname(p) for p in changed}

    def score(p: str) -> int:
        return 3 * (p in importers) + 2 * (p in used) + (posixpath.dirname(p) in folders)

    ranked = sorted((p for p in sources if p not in changed_set and is_candidate(p) and score(p) > 0),
                    key=lambda p: (-score(p), len(sources[p]), p))
    picked: dict[str, str] = {}
    room = max_chars
    for p in ranked:
        if len(picked) >= max_files or len(sources[p]) > room:
            continue
        picked[p] = sources[p]
        room -= len(sources[p])
    return picked
