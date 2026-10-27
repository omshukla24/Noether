"""Turn `node --test` output into `TestResult`s.

Pinned tests are written as `.noether/pinned/<name>.test.mjs`, so a testcase's
`file` attribute tells us which invariant it belongs to.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from noether.model import TestResult

MAX_FAILURE_CHARS = 4096
PINNED_SUFFIX = ".test.mjs"

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")
# Node prints its summary as "ℹ pass 6" (spec reporter) or "# pass 6" (tap).
_COUNT = r"(?m)^\s*(?:ℹ|#)\s+{word}\s+(\d+)\s*$"
_MOCHA = r"(?m)^\s*(\d+)\s+{word}\b"
_JEST = r"Tests:.*?(\d+)\s+{word}"


def pinned_filename(name: str) -> str:
    """File name a pinned invariant is written under. Same input, same output."""
    return _UNSAFE.sub("_", name) + PINNED_SUFFIX


def tail(text: str, limit: int = MAX_FAILURE_CHARS) -> str:
    return text if len(text) <= limit else text[-limit:]


def parse_junit(xml: str, names: list[str]) -> dict[str, TestResult]:
    """Map every name in `names` to a result. A name whose file reported nothing
    is failed with "did not run", so a crashed run can never look green."""
    wanted = {pinned_filename(n): n for n in names}
    cases, problem = _read_cases(xml)
    seen: dict[str, list[TestResult]] = {}
    for case in cases:
        name = wanted.get(_basename(case.get("file", "")))
        if name is not None:
            seen.setdefault(name, []).append(_case_result(name, case))

    out: dict[str, TestResult] = {}
    for name in names:
        parts = seen.get(name)
        if not parts:
            note = "did not run" + (f": {problem}" if problem else "")
            out[name] = TestResult(name, False, note)
            continue
        failed = [p for p in parts if not p.passed]
        out[name] = TestResult(
            name,
            not failed,
            tail("\n\n".join(p.output for p in failed)),
            sum(p.ms for p in parts),
        )
    return out


def parse_counts(output: str) -> tuple[int, int]:
    """Best-effort (passed, failed) from a test runner's text output. (0, 0) when
    the format is not recognised; the exit code stays the source of truth."""
    for pattern in (_COUNT, _MOCHA):
        passed = _first_int(pattern.format(word="(?:pass|passing)"), output)
        failed = _first_int(pattern.format(word="(?:fail|failing)"), output)
        if passed or failed:
            return passed, failed
    return _first_int(_JEST.format(word="passed"), output), _first_int(_JEST.format(word="failed"), output)


def _first_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _read_cases(xml: str) -> tuple[list[ET.Element], str]:
    # Test code can print before the report starts, so cut the document out.
    start = xml.rfind("<?xml")
    if start < 0:
        start = xml.find("<testsuites")
    end = xml.rfind("</testsuites>")
    if start < 0 or end < 0:
        return [], "no junit report in the output: " + tail(xml.strip(), 600)
    try:
        root = ET.fromstring(xml[start : end + len("</testsuites>")])
    except ET.ParseError as exc:
        return [], f"junit report is not valid XML ({exc})"
    return list(root.iter("testcase")), ""


def _case_result(name: str, case: ET.Element) -> TestResult:
    ms = float(case.get("time") or 0) * 1000
    for tag in ("failure", "error"):
        node = case.find(tag)
        if node is not None:
            message = node.get("message") or ""
            body = (node.text or "").strip()
            text = body if (not message or message in body) else f"{message}\n{body}"
            return TestResult(name, False, tail(text.strip() or "failed with no message"), ms)
    if case.find("skipped") is not None:
        return TestResult(name, False, "skipped, so it proved nothing", ms)
    return TestResult(name, True, "", ms)
