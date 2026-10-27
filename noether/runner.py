"""Where repo code runs.

`ContreeRunner` is the real one: every checkpoint is an immutable Nebius Sandbox
image and every "branch" is a new run started from it. `LocalRunner` exists so
the pipeline can be tested end to end without the network; it only ever runs
our own fixtures (fixtures/<name>/base and head), under Node's permission model.
"""
from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath

from noether.junit import FILE_LOG_MARK, parse_counts, parse_junit, pinned_filename, tail
from noether.model import Change, Invariant, Snapshot, SuiteResult, TestResult

SKIP_DIRS = {"node_modules", ".git", ".noether"}
NODE_IMAGE = "docker.io/library/node:24-slim"
JUNIT_PATH = "/tmp/noether-junit.xml"
LOG_PATH = "/tmp/noether-test.log"
ONE_PATH = "/tmp/noether-one.log"
MAX_FILE_LOG = 2000
NO_SUITE_MARKER = "NOETHER_NO_TEST_SCRIPT"
PER_TEST_TIMEOUT_MS = 20_000
MAX_SANDBOX_OUTPUT = 2_000_000  # the junit report comes back on stdout

_SLUG = re.compile(r"^[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^[A-Za-z0-9_./-]+$")
_FETCH_JS = (
    "fetch(process.env.NOETHER_TARBALL).then(r=>{if(!r.ok){console.error('tarball fetch failed, HTTP '"
    "+r.status+' for '+process.env.NOETHER_TARBALL);process.exit(3)}return r.arrayBuffer()})"
    ".then(b=>require('fs').writeFileSync('/w/src.tgz',Buffer.from(b)))"
)
_INSTALL = (
    "if [ -f package-lock.json ]; then npm ci --no-audit --no-fund || npm install --no-audit --no-fund; "
    "elif [ -f package.json ]; then npm install --no-audit --no-fund; fi"
)


class RunnerError(Exception):
    """Fetch, install, checkout or sandbox failure. The pipeline turns it into INCONCLUSIVE."""


def safe_relpath(path: str) -> str:
    """Repo-relative path from a model or a diff; refuse anything that could leave the repo."""
    posix = PurePosixPath(path.replace("\\", "/"))
    if not path or posix.is_absolute() or ".." in posix.parts or ":" in posix.parts[0]:
        raise RunnerError(f"refusing unsafe path {path!r}")
    return str(posix)


def pinned_files(tests: list[Invariant]) -> dict[str, str]:
    """Pinned file name -> test source. Two invariants may not share a file."""
    files: dict[str, str] = {}
    for test in tests:
        name = pinned_filename(test.name)
        if name in files:
            raise RunnerError(f"two invariants map to the same file {name}")
        files[name] = test.test_code
    return files


def read_tree(root: Path) -> dict[str, bytes]:
    """Every file under `root` (posix relative path -> bytes), minus dependency and VCS folders."""
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_DIRS.intersection(rel.parts):
            out[rel.as_posix()] = path.read_bytes()
    return out


class LocalRunner:
    """Runs fixtures on this machine. Node gets read access to one scratch folder
    and nothing else: no writes, no child processes, so test code cannot reach out."""

    def __init__(self, node: str = "node", timeout: float = 120.0):
        self.node = node
        self.timeout = timeout
        self.seconds = 0.0
        self._dirs: list[Path] = []

    def close(self) -> None:
        for path in self._dirs:
            shutil.rmtree(path, ignore_errors=True)  # best-effort cleanup of temp copies
        self._dirs.clear()

    def prepare(self, change: Change) -> Snapshot:
        return self._snapshot(self._fixture(change, "base"), "base")

    def checkout_head(self, base: Snapshot, change: Change) -> Snapshot:
        return self._snapshot(self._fixture(change, "head"), "head")

    def apply_files(self, snap: Snapshot, files: dict[str, str]) -> Snapshot:
        scratch = self._clone(Path(snap.image))
        for rel, text in files.items():
            target = scratch / safe_relpath(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")
        return Snapshot(str(scratch), "fix:" + ",".join(files), str(scratch))

    def run_tests(self, snap: Snapshot, tests: list[Invariant]) -> list[TestResult]:
        if not tests:
            return []
        files = pinned_files(tests)
        scratch = self._clone(Path(snap.image))
        try:
            pinned_dir = scratch / ".noether" / "pinned"
            pinned_dir.mkdir(parents=True)
            for name, code in files.items():
                (pinned_dir / name).write_text(code, encoding="utf-8")
            args = ["--test-reporter=junit", *(f".noether/pinned/{name}" for name in files)]
            proc = self._node(scratch, args)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        names = [t.name for t in tests]
        report = proc.stdout if "<testsuites" in proc.stdout else proc.stdout + proc.stderr
        results = parse_junit(report, names)
        return [results[n] for n in names]

    def run_own_suite(self, snap: Snapshot) -> SuiteResult:
        root = Path(snap.image)
        package = root / "package.json"
        if not package.is_file() or not json.loads(package.read_text(encoding="utf-8")).get("scripts", {}).get("test"):
            return SuiteResult(ran=False)
        scratch = self._clone(root)
        try:
            proc = self._node(scratch, [])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        output = proc.stdout + proc.stderr
        passed, failed = parse_counts(output)
        return SuiteResult(True, proc.returncode, passed, failed, tail(output))

    def _fixture(self, change: Change, side: str) -> Path:
        # The one guard that keeps arbitrary repo code off this machine.
        if change.source != "local" or not change.local_dir:
            raise RunnerError("LocalRunner only runs local fixtures; use ContreeRunner for repositories")
        src = Path(change.local_dir) / side
        if not src.is_dir():
            raise RunnerError(f"fixture folder {src} does not exist")
        return src

    def _tmp(self) -> Path:
        path = Path(tempfile.mkdtemp(prefix="noether-local-")).resolve()
        self._dirs.append(path)
        return path

    def _snapshot(self, src: Path, label: str) -> Snapshot:
        dst = self._tmp()
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("node_modules"))
        return Snapshot(str(dst), label, str(dst))

    def _clone(self, src: Path) -> Path:
        dst = self._tmp()
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return dst

    def _node(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        # --test-isolation=none keeps the tests in this one process, so no child process is allowed.
        cmd = [self.node, "--permission", f"--allow-fs-read={cwd}", "--test", "--test-isolation=none", *args]
        started = time.monotonic()
        try:
            return subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"node --test timed out after {self.timeout:.0f}s") from exc
        finally:
            self.seconds += time.monotonic() - started


class ContreeRunner:
    """Runs repositories in Nebius Sandboxes (contree-sdk). Sandbox state is an
    image uuid, so a checkpoint costs nothing to keep and a branch is one run."""

    def __init__(self, client=None, image_tag: str = "noether-node24-slim", run_timeout: int = 300):
        self._client = client
        self.image_tag = image_tag
        self.run_timeout = run_timeout
        self.seconds = 0.0
        self._node_image = None

    @property
    def client(self):
        if self._client is None:
            from contree_sdk import ContreeSync

            self._client = ContreeSync()  # reads NEBIUS_API_KEY and NEBIUS_PROJECT_ID
        return self._client

    def prepare(self, change: Change) -> Snapshot:
        if change.source == "local":
            uploads = self._uploads(Path(change.local_dir) / "base", "/w/repo")
            fetch = ""
        else:
            uploads = {}
            fetch = self._fetch(change.repo, change.base_sha or change.base_ref, "/w/repo")
        script = f"set -e\nmkdir -p /w/repo\n{fetch}cd /w/repo\n{_INSTALL}\n"
        env = self._tarball_env(change.repo, change.base_sha or change.base_ref, change.source)
        done = self._exec(self._base_image(), script, files=uploads, env=env, disposable=False)
        return Snapshot(image=str(done.uuid), label="base")

    def checkout_head(self, base: Snapshot, change: Change) -> Snapshot:
        if change.source == "local":
            uploads = self._uploads(Path(change.local_dir) / "head", "/w/head")
            fetch, env = "", {}
        else:
            repo, ref = self._head_target(change)
            uploads = {}
            fetch = self._fetch(repo, ref, "/w/head")
            env = self._tarball_env(repo, ref, change.source)
        # Moving node_modules is safe: the base checkpoint is immutable and this run is a branch of it.
        script = (
            f"set -e\nmkdir -p /w/head\n{fetch}"
            "if [ -d /w/repo/node_modules ]; then mv /w/repo/node_modules /w/head/node_modules; fi\n"
            "need=0\n"
            "cmp -s /w/repo/package.json /w/head/package.json || need=1\n"
            "if [ -f /w/head/package-lock.json ]; then cmp -s /w/repo/package-lock.json /w/head/package-lock.json || need=1; fi\n"
            "rm -rf /w/repo\nmv /w/head /w/repo\ncd /w/repo\n"
            f'if [ "$need" = 1 ]; then {_INSTALL}; fi\n'
        )
        done = self._exec(self._image(base), script, files=uploads, env=env, disposable=False)
        return Snapshot(image=str(done.uuid), label="head")

    def apply_files(self, snap: Snapshot, files: dict[str, str]) -> Snapshot:
        uploads = {f"{snap.workdir}/{safe_relpath(rel)}": text.encode("utf-8") for rel, text in files.items()}
        done = self._exec(self._image(snap), "true", files=uploads, disposable=False)
        return Snapshot(image=str(done.uuid), label="fix:" + ",".join(files), workdir=snap.workdir)

    def run_tests(self, snap: Snapshot, tests: list[Invariant]) -> list[TestResult]:
        if not tests:
            return []
        files = pinned_files(tests)
        uploads = {f"{snap.workdir}/.noether/pinned/{n}": code.encode("utf-8") for n, code in files.items()}
        targets = " ".join(shlex.quote(f".noether/pinned/{n}") for n in files)
        # The report goes to a file so anything the tests print cannot corrupt the XML.
        # A file that dies before running a check (bad import, syntax error) is reported as a bare "test failed"
        # and its stderr is dropped, so when anything is red the red files run once more alone to say why.
        script = (
            f"cd {shlex.quote(snap.workdir)}\n"
            f"node --test --test-timeout={PER_TEST_TIMEOUT_MS} --test-reporter=junit "
            f"--test-reporter-destination={JUNIT_PATH} {targets} > {LOG_PATH} 2>&1\n"
            "rc=$?\n"
            f"cat {JUNIT_PATH} 2>/dev/null || tail -c 4000 {LOG_PATH}\n"
            f'if [ "$rc" != 0 ]; then for f in {targets}; do node "$f" > {ONE_PATH} 2>&1 || '
            f'{{ echo; echo "{FILE_LOG_MARK}$f"; head -c {MAX_FILE_LOG} {ONE_PATH}; }}; done; fi\n'
        )
        done = self._exec(self._image(snap), script, files=uploads, disposable=True)
        names = [t.name for t in tests]
        results = parse_junit(_text(done.stdout), names)
        return [results[n] for n in names]

    def run_own_suite(self, snap: Snapshot) -> SuiteResult:
        has_script = (
            "node -e \"process.exit(((JSON.parse(require('fs').readFileSync('package.json','utf8')).scripts||{}).test)?0:1)\""
        )
        script = (
            f"cd {shlex.quote(snap.workdir)} || exit 97\n"
            f"if [ ! -f package.json ] || ! {has_script}; then echo {NO_SUITE_MARKER}; exit 0; fi\n"
            "npm test 2>&1\n"
        )
        done = self._exec(self._image(snap), script, env={"CI": "1"}, disposable=True)
        output = _text(done.stdout) + _text(done.stderr)
        if NO_SUITE_MARKER in output and done.exit_code == 0:
            return SuiteResult(ran=False)
        passed, failed = parse_counts(output)
        return SuiteResult(True, done.exit_code, passed, failed, tail(output))

    def _base_image(self):
        if self._node_image is None:
            from contree_sdk.sdk.exceptions import ContreeError

            try:
                self._node_image = self.client.images.use(self.image_tag, strict=True)
            except ContreeError:
                try:
                    self._node_image = self.client.images.oci(NODE_IMAGE, tag=self.image_tag)
                except ContreeError as exc:
                    raise RunnerError(f"cannot get the sandbox image {self.image_tag}: {exc}") from exc
        return self._node_image

    def _image(self, snap: Snapshot):
        return self.client.images.use(snap.image)

    def _exec(self, image, script: str, *, files=None, env=None, disposable: bool):
        from contree_sdk.sdk.exceptions import ContreeError

        started = time.monotonic()
        try:
            for attempt in range(2):
                try:
                    done = image.run(
                        shell=script,
                        files=files or None,
                        env=env or None,
                        timeout=self.run_timeout,
                        disposable=disposable,
                        truncate_output_at=MAX_SANDBOX_OUTPUT,
                    ).wait()
                    break
                except ContreeError as exc:
                    # One dropped connection to the sandbox API (seen live) is not a verdict-worthy failure; a
                    # script that outlives run_timeout is a different error and is not retried.
                    if attempt == 0 and "timeout_type='connect'" in str(exc):
                        continue
                    raise RunnerError(f"sandbox call failed: {exc}") from exc
        finally:
            self.seconds += time.monotonic() - started
        if not disposable and done.exit_code != 0:
            raise RunnerError(f"sandbox step failed (exit {done.exit_code}): " + tail(_text(done.stderr) + _text(done.stdout), 1500))
        return done

    @staticmethod
    def _uploads(root: Path, dest: str) -> dict[str, bytes]:
        if not root.is_dir():
            raise RunnerError(f"fixture folder {root} does not exist")
        return {f"{dest}/{rel}": data for rel, data in read_tree(root).items()}

    @staticmethod
    def _head_target(change: Change) -> tuple[str, str]:
        """A fork PR stores its head as "<owner>/<repo>@<sha>" in `head_ref`."""
        if "@" in change.head_ref:
            repo, ref = change.head_ref.split("@", 1)
            return repo, ref
        return change.repo, change.head_sha or change.head_ref

    @staticmethod
    def _tarball_env(repo: str, ref: str, source: str) -> dict[str, str]:
        if source == "local":
            return {}
        parts = repo.split("/")
        plain = len(parts) == 2 and all(_SLUG.match(p) and p not in (".", "..") for p in parts)
        if not plain or not _REF.match(ref) or ".." in ref.split("/"):
            raise RunnerError(f"refusing to fetch {repo!r} at {ref!r}")
        return {"NOETHER_TARBALL": f"https://codeload.github.com/{repo}/tar.gz/{ref}"}

    @staticmethod
    def _fetch(repo: str, ref: str, dest: str) -> str:
        ContreeRunner._tarball_env(repo, ref, "github")  # validate before it reaches a shell
        return (
            f'node -e "{_FETCH_JS}"\nmkdir -p {dest}\n'
            f"tar xzf /w/src.tgz -C {dest} --strip-components=1\nrm -f /w/src.tgz\n"
        )


def _text(value) -> str:
    return value if isinstance(value, str) else ("" if value is None else bytes(value).decode("utf-8", "replace"))
