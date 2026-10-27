from __future__ import annotations

import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from noether.limits import RateLimited, RateLimiter
from noether.live import PipelineError, parse_pr_url
from noether.server import RUN_ID, create_app, sse, stream_run
from noether.store import BlobStore, LocalStore, StoreError, check_key
from tests.replay_pipeline import load_bundle, replay_pipeline

PR = "https://github.com/omshukla24/hopper/pull/7"


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.split("\n\n"):
        lines = [ln for ln in block.splitlines() if not ln.startswith(":")]
        if lines:
            name = lines[0].removeprefix("event: ")
            out.append((name, json.loads(lines[1].removeprefix("data: "))))
    return out


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


def make_client(store, pipeline=None, **limits):
    limiter = RateLimiter(store, **{"per_ip_hour": 100, "per_day": 100, **limits})
    return TestClient(create_app(pipeline or replay_pipeline(speed=10_000, sleep=lambda s: None), store, limiter))


@pytest.mark.parametrize("url", [
    "https://github.com/omshukla24/hopper/pull/7",
    "https://github.com/a/b/pull/1/",
    "https://github.com/some-owner/repo.js/pull/123456789",
])
def test_accepts_plain_pull_request_urls(url):
    assert parse_pr_url(url)[2] >= 1


@pytest.mark.parametrize("url", [
    "http://github.com/o/r/pull/7",
    "https://www.github.com/o/r/pull/7",
    "https://github.com.evil.io/o/r/pull/7",
    "https://evil.io/https://github.com/o/r/pull/7",
    "https://user@github.com/o/r/pull/7",
    "https://github.com:443/o/r/pull/7",
    "https://github.com/o/r/pull/7?x=1",
    "https://github.com/o/r/pull/7#files",
    "https://github.com/o/r/pull/7/files",
    "https://github.com/o/r/pull/0",
    "https://github.com/o/r/pull/07",
    "https://github.com/o/../pull/7",
    "https://github.com/o/r/issues/7",
    "https://github.com/-o/r/pull/7",
    "https://github.com/o/r/pull/7\nhttps://evil.io",
    "https://github.com/o/r/pull/" + "9" * 12,
    "https://github.com/" + "o" * 300 + "/r/pull/7",
    "",
    None,
])
def test_rejects_everything_else(url):
    with pytest.raises(PipelineError) as err:
        parse_pr_url(url)
    assert err.value.code == "invalid_url"


def test_health(store):
    body = make_client(store).get("/api/health").json()
    assert body["ok"] is True and body["store"] == "local"


def test_stream_ends_with_the_sealed_bundle(store):
    client = make_client(store)
    response = client.post("/api/runs", json={"pr": PR})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    got = events(response.text)
    names = [n for n, _ in got]
    sealed = load_bundle()
    assert names[:-1] == ["stage"] * len(sealed["timeline"])
    assert names[-1] == "result"
    result = got[-1][1]
    assert result["verdict"] == "BROKEN" and result["stored"] is True
    assert result["sha256"] == sealed["sha256"] and RUN_ID.fullmatch(result["run_id"])
    assert got[0][1]["stage"] == "ingest"
    # the stored copy comes back from GET
    stored = client.get(f"/api/runs/{result['run_id']}")
    assert stored.status_code == 200 and stored.json()["sha256"] == sealed["sha256"]


def test_bad_inputs_are_rejected_before_streaming(store):
    client = make_client(store)
    assert client.post("/api/runs", json={"pr": "https://evil.io/o/r/pull/1"}).json()["error"]["code"] == "invalid_url"
    assert client.post("/api/runs", json={"pr": PR, "extra": 1}).status_code == 400
    assert client.post("/api/runs", content="not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/api/runs", json={}).status_code == 400


def test_run_id_is_validated_and_missing_is_404(store):
    client = make_client(store)
    for bad in ["..", "hopper", "20261027-025352-EDB700", "20261027-025352-edb70", "%2e%2e"]:
        assert client.get(f"/api/runs/{bad}").status_code in (400, 404)
    assert client.get("/api/runs/..%2f..%2fetc").status_code in (400, 404)
    assert client.get("/api/runs/20261027-025352-edb700").status_code == 404


def test_rate_limit_per_ip_then_global(store):
    client = make_client(store, per_ip_hour=2, per_day=3)
    assert client.post("/api/runs", json={"pr": PR}).status_code == 200
    assert client.post("/api/runs", json={"pr": PR}).status_code == 200
    third = client.post("/api/runs", json={"pr": PR})
    assert third.status_code == 429 and third.json()["error"]["code"] == "rate_limited"
    assert int(third.headers["retry-after"]) > 0


def test_limiter_keeps_no_raw_ip_and_fails_closed(store):
    now = 1_800_000_000.0
    limiter = RateLimiter(store, per_ip_hour=1, per_day=10, clock=lambda: now)
    limiter.hit("203.0.113.9")
    saved = [p for p in store.root.rglob("*.json")][0].read_text()
    assert "203.0.113.9" not in saved
    with pytest.raises(RateLimited):
        limiter.hit("203.0.113.9")
    limiter.clock = lambda: now + 3601  # the hour has passed
    limiter.hit("203.0.113.9")

    class Broken(LocalStore):
        def get(self, key, fresh=False):
            raise StoreError("down")

    with pytest.raises(RateLimited):
        RateLimiter(Broken(store.root), clock=lambda: now).hit("198.51.100.1")


def test_pipeline_errors_become_a_fail_event(store):
    def refuses(pr, emit, budget):
        raise PipelineError("public_only", "Noether only reads public repositories.")

    got = events(make_client(store, refuses).post("/api/runs", json={"pr": PR}).text)
    assert got == [("fail", {"code": "public_only", "message": "Noether only reads public repositories."})]

    def explodes(pr, emit, budget):
        raise RuntimeError("secret detail")

    got = events(make_client(store, explodes).post("/api/runs", json={"pr": PR}).text)
    assert got[0][1]["code"] == "internal" and "secret detail" not in json.dumps(got)


def test_hard_limit_ends_the_stream_with_a_timeout(store):
    release = threading.Event()
    slot = threading.Event()

    def stuck(pr, emit, budget):
        release.wait(5)
        return load_bundle()

    chunks = list(stream_run(stuck, store, PR, slot.set, hard_limit_s=0.2, keepalive_s=0.05))
    release.set()
    text = b"".join(chunks).decode()
    assert ": keepalive" in text
    assert events(text)[-1][0] == "fail" and events(text)[-1][1]["code"] == "timeout"


def test_the_slot_is_released_when_the_run_ends(store):
    done = threading.Event()
    list(stream_run(replay_pipeline(speed=10_000, sleep=lambda s: None), store, PR, done.set))
    assert done.wait(2)


def test_sse_is_one_line_per_field():
    frame = sse("stage", {"msg": "line one\nline two"}).decode()
    assert frame.count("\n") == 3 and frame.endswith("\n\n")


def test_local_store_rejects_traversal(tmp_path):
    local = LocalStore(tmp_path)
    for key in ["../x", "a/../b", "/abs", "a//b", "UPPER", ""]:
        with pytest.raises(StoreError):
            check_key(key)
    local.put("runs/x.json", b"{}")
    assert local.get("runs/x.json") == b"{}" and local.get("runs/none.json") is None


def test_blob_store_speaks_the_documented_wire_format():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "PUT":
            return httpx.Response(200, json={"url": "x"})
        return httpx.Response(200, content=b"{}") if "runs/ok.json" in str(request.url) else httpx.Response(404)

    token = "vercel_blob_rw_AbC123_secretsecret"
    blob = BlobStore(token, "public", httpx.Client(transport=httpx.MockTransport(handler)))
    blob.put("runs/ok.json", b"{}")
    put = seen[0]
    assert put.url.params["pathname"] == "runs/ok.json"
    assert put.headers["authorization"] == f"Bearer {token}"
    assert put.headers["x-vercel-blob-access"] == "public" and put.headers["x-allow-overwrite"] == "1"
    assert blob.get("runs/ok.json") == b"{}" and blob.get("runs/none.json") is None
    assert str(seen[1].url).startswith("https://abc123.public.blob.vercel-storage.com/runs/ok.json")
    with pytest.raises(StoreError):
        BlobStore("not-a-token")


def test_stream_keeps_events_in_order_under_pressure(store):
    started = time.monotonic()
    got = events(make_client(store).post("/api/runs", json={"pr": PR}).text)
    ts = [d["t_ms"] for n, d in got if n == "stage"]
    assert ts == sorted(ts) and time.monotonic() - started < 10
