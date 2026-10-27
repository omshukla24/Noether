"""The real pipeline behind the API: one public GitHub pull request in, one sealed bundle out.

Runs inside a serverless function with a hard duration limit, so the run gets a time budget:
when it is spent, the next stage event aborts the run and the pipeline seals it INCONCLUSIVE.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from typing import Any, Callable

import httpx

from noether.model import Emit, Event

# https only, github.com only, a plain /owner/repo/pull/N path: no query, fragment, port, userinfo or extra segments.
_PR = re.compile(r"https://github\.com/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/(?P<repo>[A-Za-z0-9._-]{1,100})/pull/(?P<number>[1-9][0-9]{0,8})/?")
MAX_URL_CHARS = 200
SANDBOX_STEP_SECONDS = 150


class PipelineError(Exception):
    """A run that could not start or finish. `code` is stable for the UI; the message is for people."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def parse_pr_url(raw: str) -> tuple[str, str, int]:
    text = raw.strip() if isinstance(raw, str) else ""
    match = _PR.fullmatch(text) if len(text) <= MAX_URL_CHARS else None
    if not match or match["repo"] in (".", "..") or match["repo"].endswith(".git"):
        raise PipelineError("invalid_url", "Paste a public pull request URL such as https://github.com/owner/repo/pull/12.")
    return match["owner"], match["repo"], int(match["number"])


def canonical_url(owner: str, repo: str, number: int) -> str:
    return f"https://github.com/{owner}/{repo}/pull/{number}"


def configured() -> bool:
    return bool(os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_PROJECT_ID"))


def ensure_public(owner: str, repo: str, token: str | None, http: httpx.Client | None = None) -> None:
    """The API's token may see private repositories; a run must never read one."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = (http or httpx).get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=15)
    except httpx.HTTPError as exc:
        raise PipelineError("github", f"GitHub could not be reached ({type(exc).__name__}).") from exc
    if response.status_code == 404:
        raise PipelineError("public_only", "That repository was not found. Noether only reads public repositories.")
    if response.status_code in (401, 403, 429):
        raise PipelineError("github", "GitHub refused the lookup (rate limit). Try again in a few minutes.")
    if response.status_code != 200 or response.json().get("private") is not False:
        raise PipelineError("public_only", "Noether only reads public repositories.")


def run_live(pr_url: str, emit: Emit, budget_s: float) -> dict[str, Any]:
    """Check one PR and return its sealed bundle. Raises PipelineError for anything before the run starts."""
    from noether.ingest import IngestError, from_pr_url
    from noether.nemotron import Client, ModelError
    from noether.pipeline import CapHit, Caps, run_check
    from noether.runner import ContreeRunner

    owner, repo, number = parse_pr_url(pr_url)
    token = os.environ.get("GITHUB_TOKEN") or None
    ensure_public(owner, repo, token)
    try:
        change = from_pr_url(canonical_url(owner, repo, number), token)
        max_tokens = int(os.environ.get("NOETHER_API_MAX_TOKENS", 200_000))
        client = Client.from_env(max_run_tokens=max_tokens)
    except IngestError as exc:
        raise PipelineError("ingest", str(exc)) from exc
    except ModelError as exc:
        raise PipelineError("not_configured", "The model service is not configured on this server.") from exc

    end = time.monotonic() + budget_s
    fired = False

    def guarded(ev: Event) -> None:
        nonlocal fired
        emit(ev)
        if not fired and ev.stage != "seal" and time.monotonic() > end:
            fired = True  # once: the abort path emits events too
            raise CapHit(f"the run reached its {budget_s:.0f} s time limit")

    out = tempfile.mkdtemp(prefix="noether-run-")
    runner = ContreeRunner(run_timeout=SANDBOX_STEP_SECONDS)
    try:
        run = run_check(change, client, runner, guarded,
                        Caps(max_run_tokens=max_tokens, max_sandbox_seconds=int(budget_s)), out_dir=out)
        with open(run.timeline[-1].data["bundle"], encoding="utf-8") as fh:
            return json.load(fh)
    finally:
        close: Callable[[], None] | None = getattr(runner, "close", None)
        if close:
            close()
        shutil.rmtree(out, ignore_errors=True)
