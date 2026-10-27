"""A canned pipeline: replays the sealed Hopper run's timeline through the API.

Used by the API tests and, for local work on the cockpit, as a server that needs no keys:
    python tests/replay_pipeline.py            # http://127.0.0.1:8001/api/health
Set REPLAY_SPEED=10 to play it ten times faster than it was recorded.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
HOPPER = ROOT / "web" / "public" / "runs" / "hopper.json"


def load_bundle(path: Path = HOPPER) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def replay_pipeline(speed: float = 1.0, bundle: dict | None = None,
                    sleep: Callable[[float], None] = time.sleep) -> Callable:
    sealed = bundle or load_bundle()

    def run(pr_url: str, emit, budget_s: float) -> dict:
        from noether.model import Event

        last = 0
        for raw in sealed["timeline"]:
            sleep(max(0, raw["t_ms"] - last) / 1000 / speed)
            last = raw["t_ms"]
            emit(Event(raw["t_ms"], raw["stage"], raw["type"], raw["data"]))
        # a fresh id, so the stored copy never overwrites a real run; the seal stays that of the recorded run
        return {**sealed, "run_id": time.strftime("%Y%m%d-%H%M%S") + "-aaaaaa"}

    return run


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    import uvicorn

    from noether.limits import RateLimiter
    from noether.server import create_app
    from noether.store import LocalStore

    store = LocalStore()
    limiter = RateLimiter(store, per_ip_hour=1000, per_day=1000)
    uvicorn.run(create_app(replay_pipeline(float(os.environ.get("REPLAY_SPEED", "1"))), store, limiter), host="127.0.0.1", port=8001)
