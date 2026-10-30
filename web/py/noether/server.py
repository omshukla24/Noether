"""The HTTP API: start a run and watch it as Server-Sent Events, fetch a stored bundle, health.

    POST /api/runs        {"pr": "https://github.com/owner/repo/pull/N"}  -> text/event-stream
    GET  /api/runs/{id}   a stored, sealed bundle (JSON)
    GET  /api/health

Stream events: `stage` (one pipeline event), `result` (the sealed bundle, last), `fail` (the run could not finish).
Deployed on AWS (deploy/aws); `uvicorn noether.server:app` runs it locally. web/api/index.py serves it on Vercel.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any, Callable, Iterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from noether import __version__
from noether.limits import RateLimited, RateLimiter
from noether.live import MAX_URL_CHARS, PipelineError, canonical_url, configured, parse_pr_url, run_live
from noether.model import Emit
from noether.store import Store, StoreError, make_store

log = logging.getLogger("noether.server")

RUN_ID = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}")
HARD_LIMIT_S = 270.0  # a stuck run must not hold one of the two run slots for long
BUDGET_S = 255.0  # the pipeline aborts itself at its next stage event after this
KEEPALIVE_S = 15.0
MAX_CONCURRENT = 2
DEV_ORIGINS = "http://localhost:3000,http://localhost:3001"

Pipeline = Callable[[str, Emit, float], dict]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr: str = Field(max_length=MAX_URL_CHARS)


def _problem(status: int, code: str, message: str, headers: dict[str, str] | None = None, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status, headers=headers)


def sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def client_ip(request: Request) -> str:
    # On Vercel the platform sets x-forwarded-for itself; anywhere else the header could be forged.
    if os.environ.get("VERCEL"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def stream_run(pipeline: Pipeline, store: Store, pr_url: str, release: Callable[[], None],
               hard_limit_s: float = HARD_LIMIT_S, budget_s: float = BUDGET_S,
               keepalive_s: float = KEEPALIVE_S) -> Iterator[bytes]:
    """Run `pipeline` in a worker thread and relay its events. The stream always ends with
    `result` or `fail`, even when the worker is still busy at the hard limit.
    The worker starts here, not on first read, so `release` always runs."""
    from noether.pipeline import CapHit

    q: queue.Queue[tuple[str, Any]] = queue.Queue()
    stop = threading.Event()
    aborted = False

    def emit(ev: Any) -> None:
        nonlocal aborted
        q.put(("stage", dataclasses.asdict(ev) if dataclasses.is_dataclass(ev) else ev))
        if stop.is_set() and not aborted:
            aborted = True  # the reader is gone: end the run at its next stage event, once
            raise CapHit("the client disconnected")

    def work() -> None:
        try:
            q.put(("bundle", pipeline(pr_url, emit, budget_s)))
        except PipelineError as exc:
            q.put(("fail", {"code": exc.code, "message": str(exc)}))
        except Exception:  # process boundary: the stream must end with a message, never a stack trace
            log.exception("run failed")
            q.put(("fail", {"code": "internal", "message": "The run failed unexpectedly. Nothing was sealed."}))
        finally:
            release()

    threading.Thread(target=work, daemon=True, name="noether-run").start()
    deadline = time.monotonic() + hard_limit_s

    def relay() -> Iterator[bytes]:
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    yield sse("fail", {"code": "timeout", "message": f"The run did not finish within {hard_limit_s:.0f} s, so it was stopped. Nothing was sealed."})
                    return
                try:
                    kind, payload = q.get(timeout=min(keepalive_s, left))
                except queue.Empty:
                    yield b": keepalive\n\n"
                    continue
                if kind == "stage":
                    yield sse("stage", payload)
                elif kind == "bundle":
                    yield sse("result", _result(store, payload))
                    return
                else:
                    yield sse("fail", payload)
                    return
        finally:
            stop.set()

    return relay()


def _result(store: Store, bundle: dict) -> dict:
    run_id = bundle.get("run_id", "")
    stored = False
    if RUN_ID.fullmatch(str(run_id)):
        try:
            store.put(f"runs/{run_id}.json", json.dumps(bundle, ensure_ascii=False).encode())
            stored = True
        except StoreError:
            log.exception("could not store bundle %s", run_id)
    return {"run_id": run_id, "verdict": bundle.get("verdict"), "reason": bundle.get("reason"),
            "sha256": bundle.get("sha256"), "stored": stored, "bundle": bundle}


def create_app(pipeline: Pipeline | None = None, store: Store | None = None, limiter: RateLimiter | None = None) -> FastAPI:
    """`pipeline`, `store` and `limiter` let tests (and the replay script) swap in fakes."""
    live = pipeline is None
    pipeline = pipeline or run_live
    store = store or make_store()
    limiter = limiter or RateLimiter(store)
    slots = threading.BoundedSemaphore(MAX_CONCURRENT)

    app = FastAPI(title="Noether API", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    origins = [o.strip() for o in os.environ.get("NOETHER_CORS_ORIGINS", DEV_ORIGINS).split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"], max_age=600)

    @app.exception_handler(RequestValidationError)
    def bad_body(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _problem(400, "invalid_url", "Send JSON like {\"pr\": \"https://github.com/owner/repo/pull/12\"}.")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "live": configured() if live else True, "store": store.kind}

    @app.post("/api/runs")
    def start_run(body: RunRequest, request: Request) -> Response:
        try:
            owner, repo, number = parse_pr_url(body.pr)
        except PipelineError as exc:
            return _problem(400, exc.code, str(exc))
        if live and not configured():
            return _problem(503, "not_configured", "Live runs are not switched on for this deployment.")
        try:
            limiter.hit(client_ip(request))
        except RateLimited as exc:
            return _problem(429, "rate_limited", str(exc), {"Retry-After": str(exc.retry_after)}, retry_after=exc.retry_after)
        if not slots.acquire(blocking=False):
            return _problem(429, "busy", "Two runs are already in progress. Try again in a minute.", {"Retry-After": "60"}, retry_after=60)
        headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"}
        gen = stream_run(pipeline, store, canonical_url(owner, repo, number), slots.release)
        return StreamingResponse(gen, media_type="text/event-stream", headers=headers)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Response:
        if not RUN_ID.fullmatch(run_id):
            return _problem(400, "invalid_id", "That is not a run id.")
        try:
            raw = store.get(f"runs/{run_id}.json")
        except StoreError:
            log.exception("could not read bundle %s", run_id)
            return _problem(503, "store_unavailable", "Stored runs cannot be read right now.")
        if raw is None:
            return _problem(404, "not_found", "No run was sealed under that id.")
        return Response(raw, media_type="application/json", headers={"Cache-Control": "public, max-age=3600, immutable", "X-Content-Type-Options": "nosniff"})

    return app


app = create_app()
