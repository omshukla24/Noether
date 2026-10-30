import json
import shutil

import pytest

from noether.ingest import from_local
from noether.model import Change, ChangedFile
from noether.record import (CANON, Proposal, build_checks, build_record_messages, module_problem, parse_recording,
                            propose_cases, runner_files)
from noether.runner import LocalRunner
from tests.tiny_cart import FIXTURE

MODULE = """import { clamp } from '../../src/physics.js';
export const cases = {
  "clamp-above-the-bound": () => clamp(15, 0, 10),
  "clamp-below-the-bound": () => clamp(-3, 0, 10),
};
"""


def case(name="clamp-above-the-bound", **over):
    base = {"name": name, "claim": "a value above the bound", "target_file": "src/physics.js", "target_symbol": "clamp"}
    base.update(over)
    return base


def reply(make_client, module=MODULE, cases=None):
    text = "```js\n" + module.rstrip("\n") + "\n```\n```json\n" + json.dumps(cases or [case()]) + "\n```"
    return make_client(make_client.ok(text))


def test_the_prompt_asks_for_inputs_only_and_shows_both_sides_of_the_diff(change):
    system, user = (m["content"] for m in build_record_messages(change, 8))

    assert "You do not write expected values" in system
    assert "Write at most 8 cases." in user
    assert "-  if (x > hi) return hi;" in user and "+  if (x >= hi) return hi - 1;" in user
    assert "BASE lines rewritten: 1-5" in user and "Diff of README" not in user


def test_the_prompt_returns_a_failed_module_with_the_reason(change):
    user = build_record_messages(change, 8, previous="export const cases = {};", feedback="- x: boom")[1]["content"]

    assert "### Your previous module" in user and "- x: boom" in user


def test_a_good_module_gives_cases_and_node_imports_are_stripped(make_client, change):
    module = "import test from 'node:test';\nimport assert from 'node:assert/strict';\n" + MODULE
    proposal = propose_cases(reply(make_client, module), change)

    assert [c["name"] for c in proposal.cases] == ["clamp-above-the-bound"] and proposal.dropped == []
    assert "node:" not in proposal.module


@pytest.mark.parametrize("bad,reason", [
    (MODULE.replace("export const cases", "const cases"), "no `export const cases"),
    (MODULE + "fetch('http://x');", "forbidden API: fetch"),
    (MODULE + "const t = Date.now();", "forbidden API: clock"),
    (MODULE.replace("../../src/physics.js", "../../src/other.js"), "only the changed and related files"),
    ("", "empty"),
    (MODULE + "// " + "x" * 12000, "over 12000"),
])
def test_a_module_that_cannot_run_is_rejected_whole(make_client, change, bad, reason):
    proposal = propose_cases(reply(make_client, bad), change)

    assert proposal.module == "" and proposal.cases == []
    assert reason in proposal.dropped[0]["reason"]


def test_bad_cases_are_dropped_one_by_one_and_the_cap_holds(make_client, change):
    cases = [case(), case(), case("Bad Name"), case("clamp-far-file", target_file="src/nope.js"),
             case("clamp-no-symbol", target_symbol="missing"), case("clamp-below-the-bound"), case("one-more-case")]

    proposal = propose_cases(reply(make_client, cases=cases), change, max_cases=2, taken={"taken-name"})

    assert [c["name"] for c in proposal.cases] == ["clamp-above-the-bound", "clamp-below-the-bound"]
    reasons = {d["name"]: d["reason"] for d in proposal.dropped}
    assert "duplicate" in reasons["clamp-above-the-bound"] and "bad name" in reasons["Bad Name"]
    assert "unknown target file" in reasons["clamp-far-file"] and "not in the base source" in reasons["clamp-no-symbol"]
    assert "over the cap of 2" in reasons["one-more-case"]


def test_a_missing_import_is_added(make_client, change):
    module = MODULE.replace("import { clamp } from '../../src/physics.js';\n", "")

    proposal = propose_cases(reply(make_client, module), change)

    assert "import { clamp } from '../../src/physics.js';" in proposal.module


def test_a_module_sent_with_escaped_newlines_and_the_wrong_import_folder_is_repaired(make_client, change):
    module = MODULE.replace("../../src", "./src").replace("\n", "\\n")

    proposal = propose_cases(reply(make_client, module), change)

    assert proposal.dropped == [] and proposal.module == MODULE


def test_an_import_from_the_wrong_folder_is_fixed_and_unknown_files_are_left_alone(change):
    from noether.pin import fix_import_paths

    code = ("import a from './src/physics.js';\nimport b from '../src/physics.js';\nimport c from '../../src/physics.js';\n"
            "import d from './src/other.js';\nimport test from 'node:test';\n")

    assert fix_import_paths(code, change) == (
        "import a from '../../src/physics.js';\nimport b from '../../src/physics.js';\n"
        "import c from '../../src/physics.js';\nimport d from './src/other.js';\nimport test from 'node:test';\n")


def test_nothing_to_pin_makes_no_model_call(make_client):
    none = Change("a/b", "main", "pr", files=[ChangedFile("src/x.js", "added", [], None, "export const x=1")])
    client = make_client()

    assert propose_cases(client, none).cases == [] and client.sent == []


def test_parse_recording():
    line = "@@NOETHER-RECORD " + json.dumps({"a": {"ok": True, "value": "1"}})

    assert parse_recording("noise\n" + line + "\n") == ({"a": {"ok": True, "value": "1"}}, "")
    results, problem = parse_recording("SyntaxError: Unexpected token")
    assert results == {} and problem.startswith("the module did not run: SyntaxError")
    assert parse_recording("@@NOETHER-RECORD not json")[1] == "the recording was not valid JSON"


def test_checks_are_built_from_the_recording_only_for_cases_that_answered():
    proposal = Proposal(MODULE, [case(), case("clamp-below-the-bound"), case("clamp-threw"), case("clamp-gone")])
    results = {"clamp-above-the-bound": {"ok": True, "value": "10"}, "clamp-below-the-bound": {"ok": True, "value": "0"},
               "clamp-threw": {"ok": False, "error": "TypeError: x"}}

    checks, dropped = build_checks(proposal, results)

    assert [c.name for c in checks] == ["clamp-above-the-bound", "clamp-below-the-bound"]
    assert 'const __expected = "10";' in checks[0].test_code and 'cases["clamp-above-the-bound"]' in checks[0].test_code
    assert dropped == [{"name": "clamp-threw", "reason": "record failed on base: TypeError: x"},
                       {"name": "clamp-gone", "reason": "record failed on base: the case is not in the module"}]


def test_runner_files_are_the_module_and_the_harness():
    files = runner_files(Proposal(MODULE, []))

    assert files["_record.mjs"] == MODULE and "mod.cases" in files["_record_run.mjs"] and CANON in files["_record_run.mjs"]
    assert module_problem(MODULE, Change("a/b", "m", "p")) is not None  # no pinnable files: the import is refused


@pytest.fixture
def node():
    if not shutil.which("node"):
        pytest.skip("node is not installed")


def test_record_on_base_then_the_check_catches_a_silent_change_on_head_for_real(node):
    # tiny-cart: the title announces a threshold; discount rounding changed silently from round to floor.
    change = from_local(str(FIXTURE))
    module = ("import { discountAmount, shippingFor } from '../../src/cart.js';\nexport const cases = {\n"
              '  "discount-of-fifteen-on-nineteen-ninety-nine": () => discountAmount(19.99, 15),\n'
              '  "discount-of-ten-on-ten": () => discountAmount(10, 10),\n'
              '  "shipping-at-sixty": () => shippingFor(60),\n  "this-one-throws": () => { throw new RangeError("no"); },\n};\n')
    meta = [case(n, target_file="src/cart.js", target_symbol=s) for n, s in [
        ("discount-of-fifteen-on-nineteen-ninety-nine", "discountAmount"), ("discount-of-ten-on-ten", "discountAmount"),
        ("shipping-at-sixty", "shippingFor"), ("this-one-throws", "shippingFor")]]
    proposal = Proposal(module, meta)
    runner = LocalRunner()
    try:
        base = runner.prepare(change)
        head = runner.checkout_head(base, change)
        results, problem = parse_recording(runner.run_module(base, runner_files(proposal), "_record_run.mjs"))
        checks, dropped = build_checks(proposal, results)
        on_base = {r.name: r.passed for r in runner.run_tests(base, checks)}
        on_head = {r.name: r for r in runner.run_tests(head, checks)}
    finally:
        runner.close()

    assert problem == "" and [d["name"] for d in dropped] == ["this-one-throws"]
    assert on_base == dict.fromkeys([c.name for c in checks], True)
    assert not on_head["discount-of-fifteen-on-nineteen-ninety-nine"].passed
    assert "BASE gave: 3" in on_head["discount-of-fifteen-on-nineteen-ninety-nine"].output
    assert on_head["discount-of-ten-on-ten"].passed
    assert not on_head["shipping-at-sixty"].passed  # the announced threshold moved: one input flips on its own
