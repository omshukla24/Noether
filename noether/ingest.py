"""Turn a fixture folder, a GitHub PR or a pair of refs into a `Change`.

Fork convention (there is no field for it in `Change`): `change.repo` is always
the base repository, and when a PR comes from a fork `change.head_ref` is
"<owner>/<repo>@<sha>" instead of a branch name. `ContreeRunner` splits it.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import posixpath
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

import httpx

from noether.model import Change, ChangedFile, Hunk
from noether.related import is_candidate, pick_related
from noether.runner import read_tree

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_SOURCE_BYTES = 200_000
MAX_SOURCE_FILES = 60  # raw fetches per side; the diff itself is always complete
FILES_PER_PAGE = 100
MAX_FILE_PAGES = 10
MAX_RELATED_FETCHES = 20  # raw fetches for unchanged neighbours of the change
MAX_RELATED_FILE_BYTES = 60_000
MAX_COMMIT_MESSAGES = 20

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)
_PR_URL = re.compile(r"^https?://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_STATUS = {"added": "added", "removed": "removed", "renamed": "renamed"}  # everything else is "modified"


class IngestError(Exception):
    """The change could not be read (bad URL, missing PR, API limit, empty diff)."""


def parse_hunks(patch: str) -> list[Hunk]:
    """Head-side ranges from the "@@ -a,b +c,d @@" headers of a unified diff."""
    return [Hunk(int(m.group(1)), 1 if m.group(2) is None else int(m.group(2))) for m in _HUNK.finditer(patch)]


# ---------------------------------------------------------------- local fixtures


def from_local(fixture_dir: str) -> Change:
    root = Path(fixture_dir).resolve()
    meta_path = root / "change.json"
    if not meta_path.is_file() or not (root / "base").is_dir() or not (root / "head").is_dir():
        raise IngestError(f"{root} needs base/, head/ and change.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(f"{meta_path} is not valid JSON: {exc}") from exc
    base, head = read_tree(root / "base"), read_tree(root / "head")

    files: list[ChangedFile] = []
    diffs: list[str] = []
    for path in sorted(set(base) | set(head)):
        old, new = base.get(path), head.get(path)
        if old == new:
            continue
        status = "added" if old is None else "removed" if new is None else "modified"
        old_text, new_text = _decode(old), _decode(new)
        patch = _unified(path, old_text, new_text, status)
        files.append(
            ChangedFile(path, status, [] if status == "removed" else parse_hunks(patch), old_text, new_text)
        )
        diffs.append(_file_diff(path, path, status, patch))

    texts = {path: t for path, data in base.items() if is_candidate(path) and (t := _decode(data)) is not None}
    related = pick_related([f.path for f in files], texts)
    return Change(
        repo=meta.get("repo") or f"local/{root.name}",
        base_ref="base",
        head_ref="head",
        title=meta.get("title", ""),
        body=meta.get("body", ""),
        diff="".join(diffs),
        files=files,
        base_sha=_tree_id(base),
        head_sha=_tree_id(head),
        source="local",
        local_dir=str(root),
        related=related,
    )


def _decode(data: bytes | None) -> str | None:
    if data is None or len(data) > MAX_SOURCE_BYTES or b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _unified(path: str, old: str | None, new: str | None, status: str) -> str:
    if old is None and status != "added" or new is None and status != "removed":
        return ""  # binary or too large: no patch, same as GitHub
    lines = difflib.unified_diff(
        (old or "").splitlines(),
        (new or "").splitlines(),
        "/dev/null" if status == "added" else f"a/{path}",
        "/dev/null" if status == "removed" else f"b/{path}",
        n=3,
        lineterm="",
    )
    return "\n".join(lines) + "\n"


def _tree_id(tree: dict[str, bytes]) -> str:
    """Stand-in for a commit sha: a short hash of the folder's paths and bytes."""
    digest = hashlib.sha256()
    for path, data in sorted(tree.items()):
        digest.update(path.encode() + b"\0" + data + b"\0")
    return digest.hexdigest()[:12]


def _file_diff(old_path: str, new_path: str, status: str, patch: str) -> str:
    head = f"diff --git a/{old_path} b/{new_path}\n"
    if status == "renamed":
        head += f"rename from {old_path}\nrename to {new_path}\n"
    if not patch:
        return head if status == "renamed" else head + "Binary or oversized file: no textual diff\n"
    if patch.startswith("--- "):  # local diffs already carry their own file headers
        return head + patch
    old_name = "/dev/null" if status == "added" else f"a/{old_path}"
    new_name = "/dev/null" if status == "removed" else f"b/{new_path}"
    return head + f"--- {old_name}\n+++ {new_name}\n" + patch.rstrip("\n") + "\n"


# ---------------------------------------------------------------------- GitHub


def from_pr_url(url: str, token: str | None = None, http: httpx.Client | None = None) -> Change:
    match = _PR_URL.match(url.strip())
    if not match:
        raise IngestError(f"not a GitHub pull request URL: {url}")
    owner, name, number = match.groups()
    with _session(http) as client:
        pr = _get_json(client, f"{API}/repos/{owner}/{name}/pulls/{number}", token)
        entries = _get_pages(client, f"{API}/repos/{owner}/{name}/pulls/{number}/files", token)
        base_repo = (pr["base"].get("repo") or {}).get("full_name") or f"{owner}/{name}"
        head_repo = (pr["head"].get("repo") or {}).get("full_name") or base_repo
        base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
        files, diff = _assemble(client, token, entries, (base_repo, base_sha), (head_repo, head_sha))
        related = _related(client, token, (base_repo, base_sha), [f.path for f in files])
    return Change(
        repo=base_repo,
        base_ref=pr["base"]["ref"],
        head_ref=f"{head_repo}@{head_sha}" if head_repo != base_repo else pr["head"]["ref"],
        title=pr.get("title") or "",
        body=pr.get("body") or "",
        diff=diff,
        files=files,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_url=url,
        source="github",
        related=related,
    )


def from_refs(repo: str, base: str, head: str, token: str | None = None, http: httpx.Client | None = None) -> Change:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise IngestError(f"repository must look like owner/name, got {repo!r}")
    with _session(http) as client:
        url = f"{API}/repos/{repo}/compare/{quote(base, safe='/')}...{quote(head, safe='/')}"
        first = _get_json(client, url, token, {"per_page": FILES_PER_PAGE, "page": 1})
        entries = list(first.get("files", []))
        for page in range(2, MAX_FILE_PAGES + 1):
            if len(entries) < (page - 1) * FILES_PER_PAGE:
                break
            entries += _get_json(client, url, token, {"per_page": FILES_PER_PAGE, "page": page}).get("files", [])
        base_sha = first["merge_base_commit"]["sha"]  # what the head branch really diverged from
        head_sha = head if _SHA.match(head) else _resolve_sha(client, repo, head, token)
        files, diff = _assemble(client, token, entries, (repo, base_sha), (repo, head_sha))
        related = _related(client, token, (repo, base_sha), [f.path for f in files])
    messages = [c["commit"]["message"] for c in first.get("commits", [])[:MAX_COMMIT_MESSAGES]]
    return Change(
        repo=repo,
        base_ref=base,
        head_ref=head,
        title=f"{base}...{head}",
        body="\n\n".join(messages),
        diff=diff,
        files=files,
        base_sha=base_sha,
        head_sha=head_sha,
        source="github",
        related=related,
    )


def _related(client: httpx.Client, token: str | None, at: tuple[str, str], changed: list[str]) -> dict[str, str]:
    """Fetch the nearest unchanged JS files from the base tree and keep the ones the change is felt through."""
    repo, sha = at
    try:
        tree = _get_json(client, f"{API}/repos/{repo}/git/trees/{sha}", token, {"recursive": "1"})
    except IngestError:
        return {}  # extra context only; the pin stage still works from the changed files
    folders = [posixpath.dirname(p) for p in changed]

    def distance(path: str) -> int:
        d = posixpath.dirname(path)
        return min((0 if d == f else 1 if d.startswith(f) or f.startswith(d) else 2) for f in folders) if folders else 2

    candidates = [e["path"] for e in tree.get("tree", [])
                  if e.get("type") == "blob" and e.get("size", 0) <= MAX_RELATED_FILE_BYTES
                  and is_candidate(e["path"]) and e["path"] not in changed]
    candidates.sort(key=lambda p: (distance(p), p.count("/"), p))
    sources = {}
    for path in candidates[:MAX_RELATED_FETCHES]:
        text = _raw(client, token, at, path)
        if text is not None:
            sources[path] = text
    return pick_related(changed, sources)


@contextmanager
def _session(http: httpx.Client | None) -> Iterator[httpx.Client]:
    if http is not None:
        yield http
        return
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        yield client


def _headers(token: str | None, accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "noether"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(client: httpx.Client, url: str, token: str | None, params: dict | None = None, accept: str | None = None):
    try:
        response = client.get(url, params=params, headers=_headers(token, accept or "application/vnd.github+json"))
    except httpx.HTTPError as exc:
        raise IngestError(f"GitHub request failed: {exc}") from exc
    if response.status_code == 404:
        raise IngestError(f"GitHub says not found: {url} (a private repository needs a token)")
    if response.status_code in (401, 403, 429):
        raise IngestError(f"GitHub refused the request (HTTP {response.status_code}); set GITHUB_TOKEN to raise the rate limit")
    if response.status_code >= 400:
        raise IngestError(f"GitHub returned HTTP {response.status_code} for {url}")
    return response


def _get_json(client: httpx.Client, url: str, token: str | None, params: dict | None = None) -> dict:
    return _get(client, url, token, params).json()


def _get_pages(client: httpx.Client, url: str, token: str | None) -> list[dict]:
    entries: list[dict] = []
    for page in range(1, MAX_FILE_PAGES + 1):
        batch = _get(client, url, token, {"per_page": FILES_PER_PAGE, "page": page}).json()
        entries += batch
        if len(batch) < FILES_PER_PAGE:
            break
    return entries


def _resolve_sha(client: httpx.Client, repo: str, ref: str, token: str | None) -> str:
    response = _get(client, f"{API}/repos/{repo}/commits/{quote(ref, safe='/')}", token, accept="application/vnd.github.sha")
    sha = response.text.strip()
    if not _SHA.match(sha):
        raise IngestError(f"could not resolve {ref!r} in {repo}")
    return sha


def _assemble(
    client: httpx.Client,
    token: str | None,
    entries: list[dict],
    base: tuple[str, str],
    head: tuple[str, str],
) -> tuple[list[ChangedFile], str]:
    if not entries:
        raise IngestError("the change touches no files")
    files: list[ChangedFile] = []
    diffs: list[str] = []
    fetched = 0
    for entry in entries:
        status = _STATUS.get(entry["status"], "modified")
        path = entry["filename"]
        old_path = entry.get("previous_filename") or path
        patch = entry.get("patch") or ""
        changed = ChangedFile(path, status, [] if status == "removed" else parse_hunks(patch))  # type: ignore[arg-type]
        if patch and fetched < MAX_SOURCE_FILES:
            fetched += 1
            if status != "added":
                changed.base_source = _raw(client, token, base, old_path)
            if status != "removed":
                changed.head_source = _raw(client, token, head, path)
        files.append(changed)
        diffs.append(_file_diff(old_path, path, status, patch))
    return files, "".join(diffs)


def _raw(client: httpx.Client, token: str | None, at: tuple[str, str], path: str) -> str | None:
    repo, sha = at
    try:
        response = client.get(f"{RAW}/{repo}/{sha}/{quote(path)}", headers=_headers(token, "text/plain"))
    except httpx.HTTPError as exc:
        raise IngestError(f"could not fetch {path}: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise IngestError(f"raw.githubusercontent.com returned HTTP {response.status_code} for {path}")
    return _decode(response.content)
