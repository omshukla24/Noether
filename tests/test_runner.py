import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from contree_sdk.sdk.exceptions import ContreeError

from noether import model as m
from noether.ingest import from_local
from noether.junit import pinned_filename
from noether.runner import ContreeRunner, LocalRunner, RunnerError, safe_relpath
from tests.tiny_cart import DISCOUNT, FIXTURE, LINE_TOTAL, PRELUDE, SHIPPING

REAL_REPORT = (Path(__file__).parent / "data" / "node24_junit_stdout.txt").read_text(encoding="utf-8")
LIVE = pytest.mark.skipif(os.environ.get("NOETHER_LIVE") != "1", reason="set NOETHER_LIVE=1 to use Nebius Sandboxes")


def passed(results: list[m.TestResult]) -> dict[str, bool]:
    return {r.name: r.passed for r in results}


@pytest.fixture
def runner():
    local = LocalRunner()
    yield local
    local.close()


@pytest.fixture
def change() -> m.Change:
    return from_local(str(FIXTURE))


# ------------------------------------------------------------------ LocalRunner


def test_local_base_is_green_on_every_invariant(runner, change):
    base = runner.prepare(change)

    assert passed(runner.run_tests(base, [LINE_TOTAL, DISCOUNT, SHIPPING])) == {
        LINE_TOTAL.name: True, DISCOUNT.name: True, SHIPPING.name: True}


def test_local_head_flips_the_discount_and_the_threshold(runner, change):
    head = runner.checkout_head(runner.prepare(change), change)

    results = runner.run_tests(head, [LINE_TOTAL, DISCOUNT, SHIPPING])

    assert passed(results) == {LINE_TOTAL.name: True, DISCOUNT.name: False, SHIPPING.name: False}
    assert "2.99 !== 3" in results[1].output
    assert results[1].ms > 0


def test_results_follow_the_order_of_the_tests_given(runner, change):
    base = runner.prepare(change)

    names = [r.name for r in runner.run_tests(base, [SHIPPING, LINE_TOTAL, DISCOUNT])]

    assert names == [SHIPPING.name, LINE_TOTAL.name, DISCOUNT.name]


def test_running_tests_leaves_the_snapshot_untouched(runner, change):
    base = runner.prepare(change)
    before = sorted(p.relative_to(base.image).as_posix() for p in Path(base.image).rglob("*"))

    runner.run_tests(base, [LINE_TOTAL])
    runner.run_own_suite(base)

    assert sorted(p.relative_to(base.image).as_posix() for p in Path(base.image).rglob("*")) == before


def test_own_suite_is_green_on_base_and_head(runner, change):
    base = runner.prepare(change)
    head = runner.checkout_head(base, change)

    for snap in (base, head):
        suite = runner.run_own_suite(snap)
        assert (suite.ran, suite.exit_code, suite.passed, suite.failed) == (True, 0, 6, 0)


def test_own_suite_is_skipped_without_a_test_script(runner, change, tmp_path):
    bare = runner.apply_files(runner.prepare(change), {"package.json": '{"name": "x", "type": "module"}'})

    assert runner.run_own_suite(bare) == m.SuiteResult(ran=False)


def test_own_suite_failure_shows_in_the_exit_code(runner, change):
    base = runner.prepare(change)
    broken = runner.apply_files(base, {"src/cart.js": "export const shippingFor = () => 1;\n"})

    suite = runner.run_own_suite(broken)

    assert suite.ran and suite.exit_code != 0 and suite.failed >= 1


def test_apply_files_branches_without_touching_the_original(runner, change):
    head = runner.checkout_head(runner.prepare(change), change)
    head_cart = (Path(head.image) / "src" / "cart.js").read_text(encoding="utf-8")

    fixed = runner.apply_files(head, {"src/cart.js": head_cart.replace("Math.floor", "Math.round")})

    assert fixed.label == "fix:src/cart.js" and fixed.image != head.image
    assert passed(runner.run_tests(fixed, [DISCOUNT]))[DISCOUNT.name] is True
    assert passed(runner.run_tests(head, [DISCOUNT]))[DISCOUNT.name] is False


def test_apply_files_refuses_paths_that_leave_the_repo(runner, change):
    base = runner.prepare(change)

    for bad in ("../outside.js", "/etc/passwd", "C:/Windows/x.js", ""):
        with pytest.raises(RunnerError, match="unsafe path"):
            runner.apply_files(base, {bad: "x"})


def test_a_test_that_quits_the_process_does_not_look_green(runner, change):
    quitter = m.Invariant("quits", "c", "f", "s", PRELUDE + "test('bye', () => { process.exit(0); });\n")
    base = runner.prepare(change)

    results = runner.run_tests(base, [LINE_TOTAL, quitter])

    assert not any(r.passed for r in results)
    assert all(r.output.startswith("did not run") for r in results)


def test_a_test_that_cannot_import_fails_with_the_reason(runner, change):
    bad = m.Invariant("bad_import", "c", "f", "s",
                      PRELUDE + "import { nope } from '../../src/cart.js';\ntest('x', () => assert.ok(nope));\n")

    result = runner.run_tests(runner.prepare(change), [bad])[0]

    assert not result.passed and "does not provide an export" in result.output


def test_pinned_test_code_cannot_write_or_spawn_or_read_elsewhere(runner, change):
    base = runner.prepare(change)
    outside = Path(base.image).parent / "noether-escape.txt"
    attempts = {
        "writes": f"import fs from 'node:fs';\ntest('w', () => fs.writeFileSync({str(outside)!r}, 'x'));\n",
        "spawns": "import cp from 'node:child_process';\ntest('s', () => cp.execSync('echo hi'));\n",
        "reads": f"import fs from 'node:fs';\ntest('r', () => fs.readdirSync({str(Path(base.image).parent)!r}));\n",
    }
    tests = [m.Invariant(name, "c", "f", "s", PRELUDE + code) for name, code in attempts.items()]

    results = runner.run_tests(base, tests)

    assert not any(r.passed for r in results)
    assert not outside.exists()
    assert all("ERR_ACCESS_DENIED" in r.output or "Access to this API has been restricted" in r.output for r in results)


def test_two_invariants_may_not_share_a_file(runner, change):
    twin = m.Invariant("line total multiplies", "c", "f", "s", "x")
    clash = m.Invariant("line_total multiplies", "c", "f", "s", "y")

    with pytest.raises(RunnerError, match="same file"):
        runner.run_tests(runner.prepare(change), [twin, clash])


def test_no_tests_means_no_results_and_no_process(runner, change):
    assert runner.run_tests(runner.prepare(change), []) == []


def test_local_runner_only_runs_local_fixtures(runner):
    with pytest.raises(RunnerError, match="only runs local fixtures"):
        runner.prepare(m.Change(repo="acme/lib", base_ref="main", head_ref="f", source="github"))


def test_seconds_add_up_and_close_removes_the_copies(runner, change):
    base = runner.prepare(change)
    runner.run_tests(base, [LINE_TOTAL])
    assert runner.seconds > 0

    runner.close()

    assert not Path(base.image).exists()


# ------------------------------------------------------------------ ContreeRunner (fake sandbox)


class FakeSandbox:
    """Stands in for ContreeSync: records every run and answers from a script."""

    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.runs: list[dict] = []
        self.imported: list[tuple] = []
        self.missing_tag = False
        self.images = self

    def use(self, ref, strict=False):
        if strict and self.missing_tag:
            raise ContreeError()
        return FakeImage(self, ref)

    def oci(self, ref, tag=None):
        self.imported.append((ref, tag))
        return FakeImage(self, tag)


class FakeImage:
    def __init__(self, sandbox, ref):
        self.sandbox, self.ref, self.request = sandbox, ref, None

    def run(self, **kwargs):
        pending = FakeImage(self.sandbox, self.ref)
        pending.request = kwargs
        return pending

    def wait(self):
        sandbox = self.sandbox
        exit_code, stdout, stderr = sandbox.answers.pop(0) if sandbox.answers else (0, "", "")
        sandbox.runs.append({"image": self.ref, **self.request})
        if exit_code == "timeout":
            raise ContreeError()
        return SimpleNamespace(uuid=f"uuid-{len(sandbox.runs)}", exit_code=exit_code, stdout=stdout, stderr=stderr)


def test_fake_sandbox_prepare_uploads_the_local_base(change):
    sandbox = FakeSandbox()
    runner = ContreeRunner(client=sandbox)

    snap = runner.prepare(change)

    run = sandbox.runs[0]
    assert snap == m.Snapshot(image="uuid-1", label="base")
    assert run["image"] == "noether-node24-slim" and run["disposable"] is False
    assert run["files"]["/w/repo/package.json"] == (FIXTURE / "base" / "package.json").read_bytes()
    assert b"Math.round" in run["files"]["/w/repo/src/cart.js"]
    assert "npm ci" in run["shell"] and "npm install" in run["shell"] and "codeload" not in run["shell"]


def test_fake_sandbox_prepare_fetches_a_github_tarball():
    sandbox = FakeSandbox()
    change = m.Change(repo="acme/lib", base_ref="main", head_ref="f", base_sha="a" * 40)

    ContreeRunner(client=sandbox).prepare(change)

    run = sandbox.runs[0]
    assert run["env"] == {"NOETHER_TARBALL": f"https://codeload.github.com/acme/lib/tar.gz/{'a' * 40}"}
    assert "tar xzf /w/src.tgz -C /w/repo --strip-components=1" in run["shell"]
    assert not run["files"]


def test_fake_sandbox_head_branches_from_the_base_checkpoint(change):
    sandbox = FakeSandbox()
    runner = ContreeRunner(client=sandbox)

    head = runner.checkout_head(m.Snapshot("base-uuid", "base"), change)

    run = sandbox.runs[0]
    assert run["image"] == "base-uuid" and run["disposable"] is False and head.label == "head"
    assert b"Math.floor" in run["files"]["/w/head/src/cart.js"]
    assert "mv /w/repo/node_modules /w/head/node_modules" in run["shell"]
    assert "cmp -s /w/repo/package.json /w/head/package.json" in run["shell"]
    assert "mv /w/head /w/repo" in run["shell"]


def test_fake_sandbox_head_of_a_fork_is_fetched_from_the_fork():
    sandbox = FakeSandbox()
    change = m.Change(repo="acme/lib", base_ref="main", head_ref=f"someone/lib@{'c' * 40}", head_sha="c" * 40)

    ContreeRunner(client=sandbox).checkout_head(m.Snapshot("b", "base"), change)

    assert sandbox.runs[0]["env"]["NOETHER_TARBALL"] == f"https://codeload.github.com/someone/lib/tar.gz/{'c' * 40}"


def test_head_of_a_same_repo_pr_uses_the_head_sha():
    sandbox = FakeSandbox()
    change = m.Change(repo="acme/lib", base_ref="main", head_ref="feature", head_sha="d" * 40)

    ContreeRunner(client=sandbox).checkout_head(m.Snapshot("b", "base"), change)

    assert sandbox.runs[0]["env"]["NOETHER_TARBALL"].endswith("/acme/lib/tar.gz/" + "d" * 40)


@pytest.mark.parametrize("repo,ref", [("acme/lib", "x; rm -rf /"), ("acme/lib/extra", "main"), ("a b/lib", "main"),
                                      ("acme/lib", "main$(id)"), ("../lib", "main")])
def test_nothing_unsafe_reaches_the_sandbox_shell(repo, ref):
    sandbox = FakeSandbox()

    with pytest.raises(RunnerError, match="refusing to fetch"):
        ContreeRunner(client=sandbox).prepare(m.Change(repo=repo, base_ref=ref, head_ref="f"))

    assert sandbox.runs == []


def test_a_failed_install_raises_with_the_stderr_tail(change):
    sandbox = FakeSandbox([(1, "", "npm ERR! 404 not found: left-padd")])

    with pytest.raises(RunnerError, match="left-padd"):
        ContreeRunner(client=sandbox).prepare(change)


def test_a_sandbox_error_becomes_a_runner_error(change):
    sandbox = FakeSandbox([("timeout", "", "")])

    with pytest.raises(RunnerError, match="sandbox call failed"):
        ContreeRunner(client=sandbox).prepare(change)


def test_fake_sandbox_run_tests_uploads_files_and_parses_the_report():
    sandbox = FakeSandbox([(0, REAL_REPORT, "")])
    tests = [m.Invariant(n, "c", "f", "s", f"// {n}") for n in ("a_pass", "b_fail", "e_missing")]

    results = ContreeRunner(client=sandbox).run_tests(m.Snapshot("snap", "head"), tests)

    run = sandbox.runs[0]
    assert run["disposable"] is True and run["image"] == "snap"
    assert run["files"] == {f"/w/repo/.noether/pinned/{n.name}.test.mjs": f"// {n.name}".encode() for n in tests}
    assert "--test-reporter=junit" in run["shell"] and ".noether/pinned/b_fail.test.mjs" in run["shell"]
    assert passed(results) == {"a_pass": True, "b_fail": False, "e_missing": False}


def test_run_tests_with_nothing_to_run_does_not_start_a_sandbox():
    sandbox = FakeSandbox()

    assert ContreeRunner(client=sandbox).run_tests(m.Snapshot("snap", "head"), []) == []
    assert sandbox.runs == []


def test_fake_sandbox_own_suite_outcomes():
    ok = "ℹ tests 6\nℹ pass 6\nℹ fail 0\n"
    sandbox = FakeSandbox([(0, "NOETHER_NO_TEST_SCRIPT\n", ""), (0, ok, ""), (1, "ℹ pass 4\nℹ fail 2\n", "")])
    runner = ContreeRunner(client=sandbox)
    snap = m.Snapshot("snap", "base")

    assert runner.run_own_suite(snap) == m.SuiteResult(ran=False)
    assert runner.run_own_suite(snap) == m.SuiteResult(True, 0, 6, 0, ok)
    red = runner.run_own_suite(snap)
    assert (red.ran, red.exit_code, red.passed, red.failed) == (True, 1, 4, 2)
    assert sandbox.runs[1]["env"] == {"CI": "1"} and sandbox.runs[1]["disposable"] is True


def test_fake_sandbox_apply_files_branches_with_whole_files():
    sandbox = FakeSandbox()

    snap = ContreeRunner(client=sandbox).apply_files(m.Snapshot("head-uuid", "head"), {"src/cart.js": "fixed\n"})

    run = sandbox.runs[0]
    assert snap == m.Snapshot("uuid-1", "fix:src/cart.js", "/w/repo")
    assert run["image"] == "head-uuid" and run["files"] == {"/w/repo/src/cart.js": b"fixed\n"}
    assert run["disposable"] is False


def test_fake_sandbox_apply_files_refuses_unsafe_paths():
    with pytest.raises(RunnerError, match="unsafe path"):
        ContreeRunner(client=FakeSandbox()).apply_files(m.Snapshot("h", "head"), {"../../etc/x": "y"})


def test_the_node_image_is_imported_when_the_tag_is_missing(change):
    sandbox = FakeSandbox()
    sandbox.missing_tag = True

    ContreeRunner(client=sandbox).prepare(change)

    assert sandbox.imported == [("docker.io/library/node:24-slim", "noether-node24-slim")]


def test_seconds_count_every_sandbox_call(change):
    runner = ContreeRunner(client=FakeSandbox())

    runner.prepare(change)
    first = runner.seconds
    runner.run_own_suite(m.Snapshot("s", "base"))

    assert 0 < first < runner.seconds


def test_safe_relpath_and_pinned_filename_agree_on_plain_names():
    assert safe_relpath("src\\a\\b.js") == "src/a/b.js"
    assert pinned_filename("plain_name-1.2") == "plain_name-1.2.test.mjs"


# ------------------------------------------------------------------ ContreeRunner (live)


@LIVE
def test_live_sandbox_prepare_head_and_pinned_tests(change, capsys):
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(os.environ.get("NOETHER_ENV_FILE") or find_dotenv(".env.local", usecwd=True))
    runner = ContreeRunner()
    marks = {}

    def timed(label, fn, *args):
        started = time.monotonic()
        value = fn(*args)
        marks[label] = round(time.monotonic() - started, 1)
        return value

    base = timed("prepare", runner.prepare, change)
    on_base = timed("tests_on_base", runner.run_tests, base, [LINE_TOTAL, DISCOUNT, SHIPPING])
    base_suite = timed("own_suite_base", runner.run_own_suite, base)
    head = timed("checkout_head", runner.checkout_head, base, change)
    on_head = timed("tests_on_head", runner.run_tests, head, [LINE_TOTAL, DISCOUNT, SHIPPING])
    head_suite = timed("own_suite_head", runner.run_own_suite, head)
    cart = (FIXTURE / "head" / "src" / "cart.js").read_text(encoding="utf-8")
    fix = timed("apply_files", runner.apply_files, head, {"src/cart.js": cart.replace("Math.floor", "Math.round")})
    on_fix = timed("tests_on_fix", runner.run_tests, fix, [LINE_TOTAL, DISCOUNT, SHIPPING])

    with capsys.disabled():
        print(f"\nLIVE base={base.image} head={head.image} fix={fix.image}")
        print(f"LIVE seconds={marks} sandbox_total={runner.seconds:.1f}")
    assert passed(on_base) == {LINE_TOTAL.name: True, DISCOUNT.name: True, SHIPPING.name: True}
    assert passed(on_head) == {LINE_TOTAL.name: True, DISCOUNT.name: False, SHIPPING.name: False}
    assert passed(on_fix) == {LINE_TOTAL.name: True, DISCOUNT.name: True, SHIPPING.name: False}
    assert (base_suite.exit_code, head_suite.exit_code) == (0, 0)
    assert (base_suite.passed, head_suite.passed) == (6, 6)
    assert len({base.image, head.image, fix.image}) == 3
