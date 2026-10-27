"""`python -m noether check ...`: run the pipeline from a terminal.

Exit code: 0 CONSERVED, 1 BROKEN, 2 INCONCLUSIVE (or the change could not be read).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from noether.ingest import IngestError, from_local, from_pr_url, from_refs
from noether.model import Change, Event
from noether.pipeline import Caps, Stages, run_check

EXIT_CODES = {"CONSERVED": 0, "BROKEN": 1, "INCONCLUSIVE": 2}
MAX_VALUE_CHARS = 110


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noether", description="Prove a change did not silently break behaviour.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check one change")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--pr", metavar="URL", help="a GitHub pull request URL")
    source.add_argument("--repo", metavar="OWNER/NAME", help="a repository, with --base and --head")
    source.add_argument("--local", metavar="DIR", help="a fixture folder with base/, head/ and change.json")
    check.add_argument("--base", help="base ref or sha (with --repo)")
    check.add_argument("--head", help="head ref or sha (with --repo)")
    check.add_argument("--runner", choices=("contree", "local"), default="contree",
                       help="where code runs; local is only for --local fixtures")
    check.add_argument("--no-fix", action="store_true", help="skip the fix stage")
    check.add_argument("--out", default="runs", help="folder for the proof bundle (default: runs)")
    check.add_argument("--json", action="store_true", help="print the bundle JSON to stdout, events to stderr")
    check.add_argument("--env-file", help="env file with NEBIUS_* keys (default: .env.local found upwards from here)")
    return parser


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.repo and not (args.base and args.head):
        parser.error("--repo needs --base and --head")
    if not args.repo and (args.base or args.head):
        parser.error("--base and --head only go with --repo")
    if args.runner == "local" and not args.local:
        parser.error("--runner local only runs our own fixtures; pass --local DIR")
    return args


def format_event(ev: Event) -> str:
    detail = " ".join(f"{key}={_short(value)}" for key, value in ev.data.items())
    return f"{ev.t_ms / 1000:7.1f}s  {ev.stage:<7} {ev.type:<8} {detail}".rstrip()


def _short(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        text = ",".join(_short(v) for v in value) or "-"
    elif isinstance(value, dict):
        text = json.dumps(value, separators=(",", ":"), default=str)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - 3] + "..."


def load_env(path: str | None) -> None:
    from dotenv import find_dotenv, load_dotenv

    target = path or os.environ.get("NOETHER_ENV_FILE") or find_dotenv(".env.local", usecwd=True)
    if target:
        load_dotenv(target)


def read_change(args: argparse.Namespace) -> Change:
    token = os.environ.get("GITHUB_TOKEN") or None
    if args.local:
        return from_local(args.local)
    if args.pr:
        return from_pr_url(args.pr, token)
    return from_refs(args.repo, args.base, args.head, token)


def make_runner(kind: str) -> Any:
    from noether.runner import ContreeRunner, LocalRunner

    return LocalRunner() if kind == "local" else ContreeRunner()


def make_client() -> Any:
    from noether.nemotron import Client

    return Client.from_env()


def main(argv: list[str] | None = None, *, client: Any = None, runner: Any = None, stages: Stages | None = None) -> int:
    """`client`, `runner` and `stages` let tests replace the model and the sandbox."""
    args = parse_args(argv)
    load_env(args.env_file)
    try:
        change = read_change(args)
    except IngestError as exc:
        print(f"noether: {exc}", file=sys.stderr)
        return 2
    try:
        client = client or make_client()
        runner = runner or make_runner(args.runner)
    except Exception as exc:  # process boundary: whatever is wrong with the setup, say so and exit 2
        print(f"noether: setup failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2

    log = sys.stderr if args.json else sys.stdout

    def show(ev: Event) -> None:
        print(format_event(ev), file=log, flush=True)

    try:
        run = run_check(change, client, runner, show, Caps(fix=not args.no_fix), stages, out_dir=args.out)
    finally:
        close = getattr(runner, "close", None)
        if close:
            close()

    sealed = run.timeline[-1].data
    if args.json:
        with open(sealed["bundle"], encoding="utf-8") as fh:
            print(fh.read())
    else:
        print(f"\nVERDICT {run.verdict}\nreason  {run.reason}\nbundle  {sealed['bundle']}\nsha256  {sealed['sha256']}")
    return EXIT_CODES[run.verdict]
