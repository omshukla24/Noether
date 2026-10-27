import json
import subprocess
import sys
from pathlib import Path

import pytest

from noether import model as m
from noether.cli import format_event, main
from tests.tiny_cart import (DISCOUNT, FIXTURE, LINE_TOTAL, FakeClient, ScriptedRunner, make_stages)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env_file(tmp_path):
    # An empty env file keeps the tests from picking up a real .env.local further up the tree.
    path = tmp_path / "empty.env"
    path.write_text("", encoding="utf-8")
    return str(path)


def check(env_file, tmp_path, *extra, **injected):
    argv = ["check", "--local", str(FIXTURE), "--out", str(tmp_path / "runs"), "--env-file", env_file, *extra]
    return main(argv, client=FakeClient(), **injected)


def test_a_broken_change_exits_1_and_prints_stage_lines_and_the_verdict(env_file, tmp_path, capsys):
    code = check(env_file, tmp_path, "--runner", "local", stages=make_stages())

    out = capsys.readouterr().out
    assert code == 1
    assert "VERDICT BROKEN" in out
    assert "ingest  start" in out and "base    progress" in out and "fix     progress" in out
    assert "seal    done" in out
    bundle = next(line.split()[1] for line in out.splitlines() if line.startswith("bundle"))
    assert Path(bundle).exists()


def test_a_conserved_change_exits_0(env_file, tmp_path, capsys):
    only_total = make_stages(pin_invariants=lambda client, change, max_items=12: ([LINE_TOTAL], []))

    code = check(env_file, tmp_path, runner=ScriptedRunner(), stages=only_total)

    assert code == 0
    assert "VERDICT CONSERVED" in capsys.readouterr().out


def test_an_inconclusive_run_exits_2_with_its_reason(env_file, tmp_path, capsys):
    code = check(env_file, tmp_path, runner=ScriptedRunner(fail_on={"prepare"}), stages=make_stages())

    out = capsys.readouterr().out
    assert code == 2
    assert "VERDICT INCONCLUSIVE" in out and "reason  sandbox failed during base" in out


def test_no_fix_skips_the_fix_stage(env_file, tmp_path, capsys):
    runner = ScriptedRunner(plan={"head": [{DISCOUNT.name: False}]})

    code = check(env_file, tmp_path, "--no-fix", runner=runner, stages=make_stages())

    assert code == 1
    assert " fix " not in capsys.readouterr().out and "apply_files" not in runner.calls


def test_json_prints_only_the_bundle_on_stdout(env_file, tmp_path, capsys):
    code = check(env_file, tmp_path, "--json", runner=ScriptedRunner(), stages=make_stages())

    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert code == 0 and body["verdict"] == "CONSERVED" and body["run_id"]
    assert "ingest" in captured.err and "VERDICT" not in captured.out


def test_the_runner_is_closed_after_the_run(env_file, tmp_path):
    class Closing(ScriptedRunner):
        closed = False

        def close(self):
            self.closed = True

    runner = Closing()
    check(env_file, tmp_path, runner=runner, stages=make_stages())

    assert runner.closed


def test_an_unreadable_change_exits_2(env_file, tmp_path, capsys):
    code = main(["check", "--local", str(tmp_path / "missing"), "--env-file", env_file], client=FakeClient(),
                runner=ScriptedRunner())

    assert code == 2
    assert "noether:" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["check", "--pr", "https://github.com/a/b/pull/1", "--runner", "local"],
    ["check", "--repo", "a/b", "--base", "main"],
    ["check", "--local", "x", "--base", "main"],
    ["check", "--local", "x", "--pr", "https://github.com/a/b/pull/1"],
    ["check"],
    [],
])
def test_bad_arguments_are_a_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)

    assert exc.value.code == 2


def test_format_event_is_one_plain_line():
    ev = m.Event(12_340, "pin", "progress", {"name": "x", "files": ["a", "b"], "none": [], "long": "y" * 300})

    line = format_event(ev)

    assert "\n" not in line and line.startswith("   12.3s  pin     progress ")
    assert "name=x files=a,b none=- " in line and line.endswith("...")


def test_python_dash_m_noether_is_wired_up():
    help_run = subprocess.run([sys.executable, "-m", "noether", "check", "--help"], cwd=ROOT, capture_output=True,
                              text=True, timeout=60)
    bad_run = subprocess.run([sys.executable, "-m", "noether", "check", "--pr", "https://github.com/a/b/pull/1",
                              "--runner", "local"], cwd=ROOT, capture_output=True, text=True, timeout=60)

    assert help_run.returncode == 0 and "--local" in help_run.stdout and "--runner" in help_run.stdout
    assert bad_run.returncode == 2 and "--local" in bad_run.stderr
