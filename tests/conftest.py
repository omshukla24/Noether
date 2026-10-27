"""Shared test helpers: a Token Factory client wired to canned replies, and one sample change."""
from __future__ import annotations

import json

import httpx
import pytest

from noether.model import Change, ChangedFile, Hunk
from noether.nemotron import Client

BASE_SOURCE = """export function clamp(x, lo, hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

export function price(cents) {
  return Math.round(cents) / 100;
}
"""
HEAD_SOURCE = BASE_SOURCE.replace("if (x > hi) return hi;", "if (x >= hi) return hi - 1;")
DIFF = """diff --git a/src/physics.js b/src/physics.js
--- a/src/physics.js
+++ b/src/physics.js
@@ -1,5 +1,5 @@
 export function clamp(x, lo, hi) {
   if (x < lo) return lo;
-  if (x > hi) return hi;
+  if (x >= hi) return hi - 1;
   return x;
 }
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""


def ok(content: str | None, total: int = 100, finish: str = "stop") -> httpx.Response:
    body = {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": total - 10, "completion_tokens": 10, "total_tokens": total}}
    return httpx.Response(200, json=body)


@pytest.fixture
def make_client():
    """build(*replies): each reply is an httpx.Response or a function(request) -> Response, served in order.
    The returned client keeps the request bodies it sent in `.sent`. Never sleeps."""
    def build(*replies, **kw) -> Client:
        queue = list(replies)
        sent: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            item = queue.pop(0)
            return item(request) if callable(item) else item

        client = Client("test-key", transport=httpx.MockTransport(handler), **kw)
        client.sleep = lambda seconds: None
        client.sent = sent
        return client

    build.ok = ok
    return build


@pytest.fixture
def change() -> Change:
    return Change(
        repo="acme/game", base_ref="main", head_ref="feature", title="Tidy clamp", body="Small cleanup.",
        diff=DIFF, base_sha="a" * 40, head_sha="b" * 40, pr_url="https://github.com/acme/game/pull/7",
        files=[
            ChangedFile("src/physics.js", "modified", [Hunk(1, 5)], BASE_SOURCE, HEAD_SOURCE),
            ChangedFile("README.md", "modified", [Hunk(1, 1)], "old\n", "new\n"),
            ChangedFile("src/new.js", "added", [Hunk(1, 3)], None, "export const x = 1;\n"),
        ],
    )
