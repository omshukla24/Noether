import os

import httpx
import pytest

from noether.ingest import IngestError, from_local, from_pr_url, from_refs, parse_hunks
from tests.tiny_cart import FIXTURE

BASE_SHA = "b" * 40
HEAD_SHA = "a" * 40
LIVE = pytest.mark.skipif(os.environ.get("NOETHER_LIVE") != "1", reason="set NOETHER_LIVE=1 to call GitHub")

PATCH = "@@ -1,3 +1,4 @@ function x\n a\n+b\n c\n d\n@@ -20,2 +21,0 @@\n-gone\n-gone too\n"
PR = {
    "title": "Speed up parsing",
    "body": "Parsing is faster now.",
    "base": {"sha": BASE_SHA, "ref": "main", "repo": {"full_name": "acme/lib"}},
    "head": {"sha": HEAD_SHA, "ref": "faster", "repo": {"full_name": "acme/lib"}},
}
FILES = [
    {"filename": "src/a.js", "status": "modified", "patch": PATCH},
    {"filename": "src/new.js", "status": "added", "patch": "@@ -0,0 +1,2 @@\n+x\n+y\n"},
    {"filename": "src/old.js", "status": "removed", "patch": "@@ -1,2 +0,0 @@\n-x\n-y\n"},
    {"filename": "src/moved.js", "status": "renamed", "previous_filename": "src/was.js"},
    {"filename": "logo.png", "status": "modified"},
]
RAW = {
    f"/acme/lib/{BASE_SHA}/src/a.js": b"old a",
    f"/acme/lib/{HEAD_SHA}/src/a.js": b"new a",
    f"/acme/lib/{HEAD_SHA}/src/new.js": b"x\ny\n",
    f"/acme/lib/{BASE_SHA}/src/old.js": b"x\ny\n",
}


def mock_github(pr=PR, files=FILES, raw=RAW, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=raw[path]) if path in raw else httpx.Response(404)
        if path.endswith("/files"):
            page, size = int(request.url.params["page"]), int(request.url.params["per_page"])
            return httpx.Response(200, json=files[(page - 1) * size : page * size])
        if path.endswith("/pulls/7"):
            return httpx.Response(200, json=pr)
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- parse_hunks


def test_parse_hunks_reads_head_side_ranges():
    assert [(h.start, h.length) for h in parse_hunks(PATCH)] == [(1, 4), (21, 0)]


def test_parse_hunks_defaults_a_missing_length_to_one():
    assert [(h.start, h.length) for h in parse_hunks("@@ -5 +5 @@\n-a\n+b\n")] == [(5, 1)]


def test_parse_hunks_of_nothing_is_empty():
    assert parse_hunks("") == []


# ---------------------------------------------------------------- local fixture


def test_from_local_finds_both_changes_of_the_fixture():
    change = from_local(str(FIXTURE))

    assert change.source == "local" and change.repo == "local/tiny-cart"
    assert change.title == "Raise the free-shipping threshold to 75"
    assert [(f.path, f.status) for f in change.files] == [("src/cart.js", "modified"), ("test/cart.test.js", "modified")]
    assert change.base_sha != change.head_sha and len(change.base_sha) == 12


def test_from_local_hunks_cover_every_changed_line():
    cart = from_local(str(FIXTURE)).files[0]
    lines = cart.head_source.splitlines()
    changed = [i + 1 for i, line in enumerate(lines) if "= 75" in line or "Math.floor" in line]

    assert len(changed) == 2
    for number in changed:
        assert any(h.start <= number < h.start + h.length for h in cart.hunks)


def test_from_local_diff_and_sources():
    change = from_local(str(FIXTURE))
    cart = change.files[0]

    assert "-export const FREE_SHIPPING_THRESHOLD = 50;" in change.diff
    assert "+export const FREE_SHIPPING_THRESHOLD = 75;" in change.diff
    assert "diff --git a/src/cart.js b/src/cart.js" in change.diff
    assert "Math.round((toCents" in cart.base_source and "Math.floor((toCents" in cart.head_source


def test_from_local_added_and_removed_files(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "head").mkdir()
    (tmp_path / "base" / "gone.js").write_bytes(b"a\nb\n")
    (tmp_path / "head" / "fresh.js").write_bytes(b"c\n")
    (tmp_path / "head" / "blob.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "change.json").write_text('{"title": "t", "body": "b"}')

    change = from_local(str(tmp_path))
    by_path = {f.path: f for f in change.files}

    assert by_path["gone.js"].status == "removed" and by_path["gone.js"].hunks == []
    assert by_path["gone.js"].base_source == "a\nb\n" and by_path["gone.js"].head_source is None
    assert by_path["fresh.js"].status == "added" and by_path["fresh.js"].base_source is None
    assert [(h.start, h.length) for h in by_path["fresh.js"].hunks] == [(1, 1)]
    assert by_path["blob.bin"].head_source is None
    assert "Binary or oversized" in change.diff
    assert change.repo == f"local/{tmp_path.name}"


def test_from_local_needs_the_three_parts(tmp_path):
    with pytest.raises(IngestError):
        from_local(str(tmp_path))


def test_from_local_reports_a_broken_change_json(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "head").mkdir()
    (tmp_path / "change.json").write_text("{nope")

    with pytest.raises(IngestError, match="not valid JSON"):
        from_local(str(tmp_path))


# ---------------------------------------------------------------- pull request


def test_pr_basics_and_hunks():
    change = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github())

    assert (change.repo, change.base_ref, change.head_ref) == ("acme/lib", "main", "faster")
    assert (change.base_sha, change.head_sha) == (BASE_SHA, HEAD_SHA)
    assert (change.title, change.body, change.source) == ("Speed up parsing", "Parsing is faster now.", "github")
    assert change.pr_url == "https://github.com/acme/lib/pull/7"
    assert [(h.start, h.length) for h in change.files[0].hunks] == [(1, 4), (21, 0)]


def test_pr_fetches_each_side_from_the_right_commit():
    change = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github())
    by_path = {f.path: f for f in change.files}

    assert (by_path["src/a.js"].base_source, by_path["src/a.js"].head_source) == ("old a", "new a")
    assert by_path["src/new.js"].base_source is None and by_path["src/new.js"].head_source == "x\ny\n"
    assert by_path["src/old.js"].head_source is None and by_path["src/old.js"].base_source == "x\ny\n"
    assert by_path["src/old.js"].hunks == []
    assert by_path["logo.png"].base_source is None and by_path["logo.png"].head_source is None


def test_pr_diff_is_assembled_from_the_patches():
    diff = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github()).diff

    assert "diff --git a/src/a.js b/src/a.js\n--- a/src/a.js\n+++ b/src/a.js\n@@ -1,3 +1,4 @@" in diff
    assert "--- /dev/null\n+++ b/src/new.js" in diff
    assert "rename from src/was.js\nrename to src/moved.js" in diff
    assert "diff --git a/logo.png b/logo.png\nBinary or oversized" in diff


def test_pr_from_a_fork_records_the_head_repo_and_fetches_its_files():
    fork = {**PR, "head": {"sha": HEAD_SHA, "ref": "faster", "repo": {"full_name": "someone/lib"}}}
    raw = {**RAW, f"/someone/lib/{HEAD_SHA}/src/a.js": b"fork a", f"/someone/lib/{HEAD_SHA}/src/new.js": b"fork new"}

    change = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github(fork, raw=raw))

    assert change.repo == "acme/lib"
    assert change.head_ref == f"someone/lib@{HEAD_SHA}"
    assert change.files[0].head_source == "fork a"


def test_pr_token_is_sent_only_when_given():
    seen = []
    from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github(seen=seen))
    assert all("authorization" not in r.headers for r in seen)

    seen.clear()
    from_pr_url("https://github.com/acme/lib/pull/7", token="t0k", http=mock_github(seen=seen))
    api = [r for r in seen if r.url.host == "api.github.com"]
    assert api and all(r.headers["authorization"] == "Bearer t0k" for r in api)
    assert all(r.headers["accept"] == "application/vnd.github+json" for r in api)


def test_pr_files_are_read_page_by_page():
    many = [{"filename": f"f{i}.js", "status": "modified"} for i in range(150)]
    seen = []

    change = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github(files=many, seen=seen))

    assert len(change.files) == 150
    assert sum(r.url.path.endswith("/files") for r in seen) == 2


def test_oversized_and_binary_sources_are_skipped():
    files = [{"filename": "big.js", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b\n"},
             {"filename": "bin.js", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b\n"}]
    raw = {f"/acme/lib/{BASE_SHA}/big.js": b"x" * 300_000, f"/acme/lib/{HEAD_SHA}/big.js": b"y",
           f"/acme/lib/{BASE_SHA}/bin.js": b"\xff\xfe\x00", f"/acme/lib/{HEAD_SHA}/bin.js": b"ok"}

    change = from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github(files=files, raw=raw))

    assert change.files[0].base_source is None and change.files[0].head_source == "y"
    assert change.files[1].base_source is None and change.files[1].head_source == "ok"


@pytest.mark.parametrize("url", ["https://example.com/acme/lib/pull/7", "https://github.com/acme/lib/issues/7", "nope"])
def test_pr_rejects_other_urls(url):
    with pytest.raises(IngestError, match="pull request URL"):
        from_pr_url(url, http=mock_github())


def test_pr_not_found_and_rate_limit_are_explained():
    with pytest.raises(IngestError, match="not found"):
        from_pr_url("https://github.com/acme/lib/pull/9", http=mock_github())

    limited = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"message": "rate limit"})))
    with pytest.raises(IngestError, match="GITHUB_TOKEN"):
        from_pr_url("https://github.com/acme/lib/pull/7", http=limited)


def test_pr_without_files_is_an_error():
    with pytest.raises(IngestError, match="no files"):
        from_pr_url("https://github.com/acme/lib/pull/7", http=mock_github(files=[]))


# ---------------------------------------------------------------- compare


def mock_compare(seen=None):
    compare = {
        "merge_base_commit": {"sha": BASE_SHA},
        "commits": [{"commit": {"message": "first change"}}, {"commit": {"message": "second change"}}],
        "files": [{"filename": "src/a.js", "status": "modified", "patch": PATCH}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=RAW[path]) if path in RAW else httpx.Response(404)
        if "/compare/" in path:
            return httpx.Response(200, json=compare)
        if path.endswith("/commits/faster"):
            return httpx.Response(200, text=HEAD_SHA + "\n")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_from_refs_uses_the_merge_base_and_resolves_the_head_branch():
    seen = []

    change = from_refs("acme/lib", "main", "faster", http=mock_compare(seen))

    assert (change.base_sha, change.head_sha) == (BASE_SHA, HEAD_SHA)
    assert (change.base_ref, change.head_ref, change.repo) == ("main", "faster", "acme/lib")
    assert change.body == "first change\n\nsecond change"
    assert change.files[0].base_source == "old a" and change.files[0].head_source == "new a"
    assert any(r.url.path.endswith("/compare/main...faster") for r in seen)
    sha_calls = [r for r in seen if r.url.path.endswith("/commits/faster")]
    assert sha_calls[0].headers["accept"] == "application/vnd.github.sha"


def test_from_refs_keeps_a_full_sha_without_asking_github():
    seen = []

    change = from_refs("acme/lib", "main", HEAD_SHA, http=mock_compare(seen))

    assert change.head_sha == HEAD_SHA
    assert not any("/commits/" in r.url.path for r in seen)


def test_from_refs_rejects_a_bad_repo():
    with pytest.raises(IngestError, match="owner/name"):
        from_refs("not a repo", "a", "b", http=mock_compare())


@LIVE
def test_live_small_public_pr():
    change = from_pr_url("https://github.com/sindresorhus/slugify/pull/73", token=os.environ.get("GITHUB_TOKEN"))

    assert change.repo == "sindresorhus/slugify" and len(change.files) == 2
    assert all(f.hunks and f.head_source for f in change.files)
    assert len(change.base_sha) == 40 and "diff --git" in change.diff
