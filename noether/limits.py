"""Run limits for the public API: a few runs per IP per hour and a global cap per UTC day.

Counters live in the same store as the bundles, so they survive across serverless instances.
Only a salted hash of the IP is stored, never the address.
shortcut: a read-modify-write on the store, so two instances racing can both pass once; the
daily cap can overshoot by the number of concurrent requests. Upgrade to an atomic counter if abused.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Callable

from noether.store import Store, StoreError

HOUR = 3600


class RateLimited(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    def __init__(self, store: Store, per_ip_hour: int | None = None, per_day: int | None = None,
                 clock: Callable[[], float] = time.time, salt: str | None = None):
        self.store = store
        self.per_ip_hour = per_ip_hour if per_ip_hour is not None else int(os.environ.get("NOETHER_RUNS_PER_IP_HOUR", 3))
        self.per_day = per_day if per_day is not None else int(os.environ.get("NOETHER_RUNS_PER_DAY", 30))
        self.clock = clock
        self.salt = salt if salt is not None else os.environ.get("NOETHER_IP_SALT", "noether")

    def _digest(self, ip: str, day: str) -> str:
        return hashlib.sha256(f"{self.salt}|{day}|{ip}".encode()).hexdigest()[:16]

    def hit(self, ip: str) -> None:
        """Count one run for `ip`, or raise RateLimited. A broken store fails closed."""
        now = self.clock()
        day = time.strftime("%Y%m%d", time.gmtime(now))
        key = f"limits/day-{day}.json"
        try:
            raw = self.store.get(key, fresh=True)
            state = json.loads(raw) if raw else {"total": 0, "ips": {}}
            who = self._digest(ip, day)
            recent = [t for t in state["ips"].get(who, []) if now - t < HOUR]
            if state["total"] >= self.per_day:
                tomorrow = (int(now // 86400) + 1) * 86400
                raise RateLimited("The daily limit for live runs has been reached. Replay the sealed Hopper run, or try again tomorrow.",
                                  int(tomorrow - now))
            if len(recent) >= self.per_ip_hour:
                raise RateLimited(f"Only {self.per_ip_hour} live runs per hour from one address. Try again in a few minutes.",
                                  max(1, int(HOUR - (now - min(recent)))))
            state["ips"][who] = recent + [now]
            state["ips"] = {k: v for k, v in state["ips"].items() if any(now - t < HOUR for t in v)}
            state["total"] += 1
            self.store.put(key, json.dumps(state, separators=(",", ":")).encode())
        except (StoreError, ValueError, KeyError, TypeError) as exc:
            raise RateLimited("Live runs are paused while the limit store is unavailable.", 60) from exc
