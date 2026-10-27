import json

import pytest

from noether import __version__
from noether.bundle import PRICES_PER_M, cost_estimate, to_bundle, verify_bundle, write_bundle
from noether.model import (DepBump, Event, Fix, Flip, Intent, Invariant, Location, ModelCall, Run, Snapshot,
                           SuiteResult)
from noether.model import TestResult as Result  # a name starting with "Test" makes pytest try to collect it


def inv(name):
    return Invariant(name, f"{name} claim", "src/physics.js", "clamp", f"// test {name}")


def tr(name, ok, output=""):
    return Result(name, ok, output)


@pytest.fixture
def run(change):
    held, intended, silent, flaky = inv("held-one"), inv("intended-one"), inv("silent-one"), inv("flaky-one")
    broken = Flip(silent, "AssertionError: 9 !== 10", kind="silent", reason="nothing announces it",
                  location=Location("src/physics.js", 3, "if (x >= hi) return hi - 1;", "excludes the bound"),
                  fix=Fix("src/physics.js", "new", "--- a\n+++ b\n", proved=True))
    return Run(
        run_id="20261027-aaaa", change=change, verdict="BROKEN", reason="1 behaviour broke.",
        intent=Intent("Tidies clamp.", ["clamp stops returning the bound"], [DepBump("vite", "5", "6", ["note"])]),
        invariants=[held, intended, silent, flaky],
        dropped=[{"name": "bad-name-one", "reason": "forbidden API: fetch"}],
        base_results={"held-one": [tr("held-one", True)] * 2, "intended-one": [tr("intended-one", True)] * 2,
                      "silent-one": [tr("silent-one", True)] * 2,
                      "flaky-one": [tr("flaky-one", True), tr("flaky-one", False, "flaked")]},
        head_results={"held-one": tr("held-one", True), "intended-one": tr("intended-one", False, "different"),
                      "silent-one": tr("silent-one", False, "AssertionError: 9 !== 10")},
        flips=[Flip(intended, "different", kind="intended", reason="announced"), broken],
        own_suite_base=SuiteResult(True, 0, 12, 0, "long output"), own_suite_head=SuiteResult(True, 1, 11, 1, "x"),
        snapshots=[Snapshot("img-base", "base"), Snapshot("img-head", "head")], sandbox_seconds=41.5,
        models=[ModelCall("pin", "nvidia/nemotron-3-super-120b-a12b", 5000, 3000, 12000.0),
                ModelCall("judge", "nvidia/Nemotron-3-Ultra-550b-a55b", 2000, 800, 4000.0)],
        timeline=[Event(0, "ingest", "start", {"repo": "acme/game"}), Event(900, "seal", "done", {})],
    )


def test_top_level_shape(run):
    b = to_bundle(run)
    assert list(b) == ["noether", "run_id", "repo", "pr", "base", "head", "verdict", "reason", "intent", "invariants",
                       "dropped", "breaks", "own_suite", "sandbox", "models", "cost_est_usd", "timeline", "sha256"]
    assert b["noether"] == __version__ and b["run_id"] == "20261027-aaaa" and b["repo"] == "acme/game"
    assert b["pr"] == {"url": "https://github.com/acme/game/pull/7", "title": "Tidy clamp"}
    assert b["base"] == {"ref": "main", "sha": "a" * 40} and b["head"] == {"ref": "feature", "sha": "b" * 40}
    assert b["verdict"] == "BROKEN" and b["reason"] == "1 behaviour broke."
    assert b["intent"] == {"summary": "Tidies clamp.", "intended_changes": ["clamp stops returning the bound"],
                           "dependency_bumps": [{"name": "vite", "old": "5", "new": "6", "notes": ["note"]}]}
    assert b["own_suite"] == {"base": {"ran": True, "exit_code": 0, "passed": 12, "failed": 0},
                              "head": {"ran": True, "exit_code": 1, "passed": 11, "failed": 1}}
    assert b["sandbox"] == {"snapshots": [{"label": "base", "image": "img-base"}, {"label": "head", "image": "img-head"}],
                            "seconds": 41.5}
    assert b["models"][0] == {"role": "pin", "model": "nvidia/nemotron-3-super-120b-a12b", "tokens_in": 5000,
                              "tokens_out": 3000, "ms": 12000.0}
    assert b["timeline"][0] == {"t_ms": 0, "stage": "ingest", "type": "start", "data": {"repo": "acme/game"}}


def test_invariant_rows(run):
    rows = {r["name"]: r for r in to_bundle(run)["invariants"]}
    assert {k: rows["held-one"][k] for k in ("base", "head", "kind", "output")} == {"base": "pass", "head": "pass", "kind": "held", "output": ""}
    assert (rows["intended-one"]["head"], rows["intended-one"]["kind"], rows["intended-one"]["output"]) == ("fail", "intended", "different")
    assert (rows["silent-one"]["head"], rows["silent-one"]["kind"]) == ("fail", "silent")
    assert (rows["flaky-one"]["base"], rows["flaky-one"]["head"], rows["flaky-one"]["kind"], rows["flaky-one"]["output"]) == ("flaky", None, "dropped", "flaked")
    assert set(rows["held-one"]) == {"name", "claim", "target_file", "target_symbol", "test_code", "base", "head", "kind", "output"}


def test_dropped_lists_validation_and_base_drops(run):
    assert to_bundle(run)["dropped"] == [{"name": "bad-name-one", "reason": "forbidden API: fetch"},
                                         {"name": "flaky-one", "reason": "flaky on base"}]


def test_breaks_are_silent_flips_with_proven_fixes(run):
    breaks = to_bundle(run)["breaks"]
    assert breaks == [{"invariant": "silent-one", "file": "src/physics.js", "line": 3,
                       "code": "if (x >= hi) return hi - 1;", "why": "excludes the bound",
                       "fix": {"file": "src/physics.js", "diff": "--- a\n+++ b\n", "proved": True}}]


def test_an_unproven_fix_is_not_shown(run):
    run.flips[1].fix.proved = False
    assert to_bundle(run)["breaks"][0]["fix"] is None


def test_a_break_without_a_location_falls_back_to_the_invariant(run):
    run.flips[1].location = None
    run.flips[1].fix = None
    assert to_bundle(run)["breaks"][0] == {"invariant": "silent-one", "file": "src/physics.js", "line": None,
                                           "code": "", "why": "nothing announces it", "fix": None}


def test_a_bare_run_still_makes_a_bundle(change):
    b = to_bundle(Run("r0", change))
    assert b["intent"] is None and b["invariants"] == [] and b["own_suite"] == {"base": None, "head": None}
    assert b["verdict"] == "INCONCLUSIVE" and verify_bundle(b)


def test_cost_estimate_uses_per_million_prices(run):
    assert cost_estimate([]) == 0.0
    p_in, p_out = PRICES_PER_M["nvidia/nemotron-3-super-120b-a12b"]
    one = cost_estimate([ModelCall("pin", "nvidia/nemotron-3-super-120b-a12b", 1_000_000, 1_000_000, 1.0)])
    assert one == pytest.approx(p_in + p_out)
    assert cost_estimate([ModelCall("x", "unknown/model", 1_000_000, 0, 1.0)]) > 0  # priced as the dearest model
    assert to_bundle(run)["cost_est_usd"] == cost_estimate(run.models) > 0


def test_sha256_round_trip(run, tmp_path):
    b = to_bundle(run)
    assert len(b["sha256"]) == 64 and verify_bundle(b)
    path = write_bundle(run, root=str(tmp_path))
    assert path == tmp_path / "20261027-aaaa" / "bundle.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == b and verify_bundle(loaded)


def test_tampering_is_detected(run):
    b = to_bundle(run)
    for edit in (lambda x: x.update(verdict="CONSERVED"),
                 lambda x: x["invariants"][0].update(test_code="// other"),
                 lambda x: x["models"].pop(),
                 lambda x: x.pop("sha256"),
                 lambda x: x.update(sha256="0" * 64)):
        copy = json.loads(json.dumps(b))
        edit(copy)
        assert not verify_bundle(copy)


def test_non_ascii_text_survives(run, tmp_path):
    run.change.title = "Tidy clamp → über"
    path = write_bundle(run, root=str(tmp_path))
    assert verify_bundle(json.loads(path.read_text(encoding="utf-8")))


def test_secrets_from_the_environment_never_reach_the_bundle(run, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-super-secret-value")
    run.invariants[0].test_code = "// leaked sk-super-secret-value here"
    text = json.dumps(to_bundle(run))
    assert "sk-super-secret-value" not in text and "[redacted]" in text


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", ""])
def test_unsafe_run_ids_are_refused(change, tmp_path, bad):
    with pytest.raises(ValueError):
        write_bundle(Run(bad, change), root=str(tmp_path))
