import json

import pytest

from noether.model import Change, ChangedFile
from noether.prompt_util import file_diff
from noether.pin import (FORBIDDEN, INVARIANT_SCHEMA, build_pin_messages, exports_of, pin_invariants,
                         validate_invariant)

GOOD_CODE = """import test from 'node:test';
import assert from 'node:assert/strict';
import { clamp } from '../../src/physics.js';

test('clamp keeps a value above the bound at the bound', () => {
  assert.equal(clamp(15, 0, 10), 10);
});
"""


def item(**over):
    base = {"name": "clamp-upper-bound", "claim": "clamp returns the upper bound for larger values",
            "target_file": "src/physics.js", "target_symbol": "clamp", "test_code": GOOD_CODE}
    base.update(over)
    return base


def reply(make_client, *items):
    return make_client(make_client.ok(json.dumps({"invariants": list(items)})))


def test_valid_item_passes(change):
    assert validate_invariant(item(), change) is None


@pytest.mark.parametrize("over,reason", [
    ({"name": "Clamp_Upper"}, "bad name"),
    ({"name": "ab"}, "bad name"),
    ({"name": "x" * 61}, "bad name"),
    ({"target_file": "src/missing.js"}, "unknown target file"),
    ({"target_file": "src/new.js"}, "unknown target file"),  # added file: nothing on base to describe
    ({"target_file": "README.md"}, "unknown target file"),
    ({"target_file": "../outside.js"}, "unknown target file"),
    ({"target_symbol": "nowhere"}, "not in the base source"),
    ({"claim": "  "}, "missing claim"),
    ({"test_code": GOOD_CODE + "// " + "x" * 6000}, "over 6000"),
    ({"test_code": GOOD_CODE.replace("import test from 'node:test';\n", "")}, "missing node:test import"),
    ({"test_code": GOOD_CODE.replace("import assert from 'node:assert/strict';\n", "")}, "node:assert/strict"),
    ({"test_code": GOOD_CODE.replace("assert.equal(clamp(15, 0, 10), 10);", "assert.ok();")}, "empty or missing assert"),
    ({"test_code": GOOD_CODE.replace("assert.equal(clamp(15, 0, 10), 10);", "clamp(15, 0, 10);")}, "empty or missing assert"),
    ({"test_code": GOOD_CODE.replace("assert.equal(clamp(15, 0, 10), 10);", "assert.ok(true);")}, "empty or missing assert"),
    ({"test_code": GOOD_CODE + "import x from '../../src/other.js';"}, "only the changed and related files"),
    ({"test_code": GOOD_CODE + "import lodash from 'lodash';"}, "only the changed and related files"),
])
def test_invalid_items_are_rejected(change, over, reason):
    assert reason in validate_invariant(item(**over), change)


@pytest.mark.parametrize("snippet,label", [
    ("import cp from 'node:child_process';", "child_process"),
    ("import fs from 'node:fs';", "fs"),
    ("import fs from 'fs/promises';", "fs"),
    ("import net from 'node:net';", "network module"),
    ("import http from 'http';", "network module"),
    ("import { Worker } from 'worker_threads';", "worker_threads"),
    ("await fetch('http://x');", "fetch"),
    ("const k = process.env.KEY;", "process.env"),
    ("eval('1');", "eval"),
    ("new Function('return 1')();", "Function constructor"),
    ("const m = require('fs');", "require"),
    ("const m = await import('../../src/physics.js');", "dynamic import"),
    ("const r = Math.random();", "clock or randomness"),
    ("const t = Date.now();", "clock or randomness"),
    ("const d = new Date();", "clock or randomness"),
])
def test_forbidden_apis_are_rejected(change, snippet, label):
    assert label in FORBIDDEN
    reason = validate_invariant(item(test_code=GOOD_CODE + snippet + "\n"), change)
    assert reason is not None and reason.startswith("forbidden API")


def test_a_fixed_date_is_fine(change):
    code = GOOD_CODE + "const d = new Date(2020, 1, 1);\n"
    assert validate_invariant(item(test_code=code), change) is None


def test_non_dict_and_duplicate(change):
    assert validate_invariant("nope", change) == "not an object"
    assert validate_invariant(item(), change, seen={"clamp-upper-bound"}) == "duplicate name"


def test_default_symbol_is_always_accepted(change):
    assert validate_invariant(item(target_symbol="default"), change) is None


def test_pin_keeps_valid_and_reports_dropped(make_client, change):
    client = reply(make_client, item(), item(name="clamp-upper-bound"), item(name="no-such-file", target_file="a.js"),
                   item(name="forbidden-thing", test_code=GOOD_CODE + "fetch('x');"))
    kept, dropped = pin_invariants(client, change)
    assert [k.name for k in kept] == ["clamp-upper-bound"]
    assert kept[0].target_file == "src/physics.js" and kept[0].target_symbol == "clamp"
    assert dropped == [{"name": "clamp-upper-bound", "reason": "duplicate name"},
                       {"name": "no-such-file", "reason": "unknown target file a.js"},
                       {"name": "forbidden-thing", "reason": "forbidden API: fetch"}]


def test_pin_caps_at_max_items(make_client, change):
    items = [item(name=f"clamp-case-{i}") for i in range(5)]
    kept, dropped = pin_invariants(reply(make_client, *items), change, max_items=3)
    assert [k.name for k in kept] == ["clamp-case-0", "clamp-case-1", "clamp-case-2"]
    assert dropped == [{"name": "clamp-case-3", "reason": "over the cap of 3 tests"},
                       {"name": "clamp-case-4", "reason": "over the cap of 3 tests"}]


def test_pin_uses_the_super_model_and_the_schema(make_client, change):
    client = reply(make_client, item())
    pin_invariants(client, change)
    sent = client.sent[0]
    assert sent["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert sent["response_format"]["json_schema"]["schema"] == INVARIANT_SCHEMA


def test_nothing_to_pin_means_no_model_call(make_client):
    change = Change("a/b", "main", "pr", files=[ChangedFile("src/x.js", "added", [], None, "export const x=1")])
    client = make_client()
    assert pin_invariants(client, change) == ([], [])
    assert client.sent == []


def test_prompt_shape(change):
    messages = build_pin_messages(change, max_items=7)
    system, user = messages[0]["content"], messages[1]["content"]
    assert "do not test the new behaviour" in system.lower() or "do not test the new behaviour" in user.lower()
    assert "'../../src/x.js'" in system
    assert "Tidy clamp" in user and "describe BASE" in user and "at most 7" in user
    assert "### src/physics.js" in user and "Exports: clamp, price" in user
    assert "export function price" in user  # base source, not head
    assert "hi - 1" not in user.rsplit("BASE source:", 1)[1]  # the head edit appears only inside the diff
    assert "1-5" in user  # head-side hunk range
    assert "src/new.js" not in user and "README" not in user


def test_prompt_clips_long_sources(change):
    change.files[0].base_source = "export const a = 1;\n" + "// filler\n" * 5000
    user = build_pin_messages(change)[1]["content"]
    assert "[clipped]" in user and len(user) < 20000


def test_exports_of():
    source = ("export function a() {}\nexport async function b() {}\nexport const c = 1;\n"
              "export class D {}\nexport { e, f as g };\nexport default function () {}\nfunction hidden() {}\n")
    assert exports_of(source) == ["D", "a", "b", "c", "default", "e", "g"]


def test_file_diff_picks_one_file_and_misses_cleanly(change):
    assert file_diff(change.diff, "src/physics.js").startswith("diff --git a/src/physics.js")
    assert "README" not in file_diff(change.diff, "src/physics.js")
    assert file_diff(change.diff, "src/none.js") == ""


def test_a_check_that_only_reads_a_constant_is_rejected(change):
    code = ("import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
            "import { GRAVITY } from '../../src/physics.js';\n"
            "test('gravity', () => { assert.equal(typeof clamp, 'function'); });\n")
    item = {"name": "gravity-value", "claim": "gravity is 30", "target_file": "src/physics.js",
            "target_symbol": "clamp", "test_code": code}
    assert validate_invariant(item, change) == "only reads a value; a check must call the code"


def test_a_check_may_import_a_related_file(change):
    from dataclasses import replace
    related = replace(change, related={"src/replay.js": "export function simulate(level, inputs) { return {}; }"})
    code = ("import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
            "import { simulate } from '../../src/replay.js';\n"
            "test('runs', () => { assert.equal(typeof simulate({}, []), 'object'); });\n")
    item = {"name": "replay-runs", "claim": "simulate returns an object", "target_file": "src/replay.js",
            "target_symbol": "simulate", "test_code": code}
    assert validate_invariant(item, related) is None
    assert validate_invariant(item, change) is not None  # without the related file it is unknown
