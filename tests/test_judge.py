import json

import httpx

from noether.judge import JUDGE_SCHEMA, build_judge_messages, judge_flips
from noether.model import Flip, Intent, Invariant, Location

INTENT = Intent("Tidies clamp.", ["clamp stops returning the bound itself"])


def flip(name, **kw):
    inv = Invariant(name, f"{name} claim", "src/physics.js", "clamp", f"// test code of {name}")
    return Flip(inv, f"AssertionError in {name}", **kw)


def verdicts(*entries):
    return json.dumps({"verdicts": [{"name": n, "rule_gives": "x", "head_gives": "x", "kind": k, "reason": r}
                                    for n, k, r in entries]})


def test_no_flips_means_no_call(make_client, change):
    client = make_client()
    assert judge_flips(client, INTENT, change, []) == []
    assert client.sent == []


def test_intended_silent_and_unsure(make_client, change):
    client = make_client(make_client.ok(verdicts(("a-test", "intended", "the PR says so"),
                                                 ("b-test", "silent", "nothing announces it"),
                                                 ("c-test", "unsure", "too little context"))))
    flips = [flip("a-test"), flip("b-test"), flip("c-test")]
    out = judge_flips(client, INTENT, change, flips)
    assert [f.kind for f in out] == ["intended", "silent", "silent"]
    assert out[0].reason == "the PR says so" and out[1].reason == "nothing announces it"
    assert "unsure" in out[2].reason and "too little context" in out[2].reason
    assert len(client.sent) == 1  # one call for all flips


def test_inputs_are_not_mutated(make_client, change):
    original = flip("a-test")
    out = judge_flips(make_client(make_client.ok(verdicts(("a-test", "intended", "announced")))), INTENT, change, [original])
    assert out[0] is not original and out[0].invariant is original.invariant
    assert original.kind == "silent" and original.reason == ""


def test_missing_name_is_silent(make_client, change):
    out = judge_flips(make_client(make_client.ok(verdicts(("other", "intended", "x")))), INTENT, change, [flip("a-test")])
    assert out[0].kind == "silent" and "no verdict" in out[0].reason


def test_first_verdict_per_name_wins(make_client, change):
    reply = verdicts(("a-test", "silent", "first"), ("a-test", "intended", "second"))
    assert judge_flips(make_client(make_client.ok(reply)), INTENT, change, [flip("a-test")])[0].reason == "first"


def test_invalid_json_is_silent(make_client, change):
    client = make_client(make_client.ok("I think it is fine."), make_client.ok("still prose"))
    out = judge_flips(client, INTENT, change, [flip("a-test"), flip("b-test")])
    assert [f.kind for f in out] == ["silent", "silent"]
    assert all("could not be used" in f.reason for f in out)


def test_an_unknown_kind_fails_the_schema_and_is_silent(make_client, change):
    bad = verdicts(("a-test", "maybe", "hmm"))
    out = judge_flips(make_client(make_client.ok(bad), make_client.ok(bad)), INTENT, change, [flip("a-test")])
    assert out[0].kind == "silent"


def test_model_errors_are_silent(make_client, change):
    client = make_client(httpx.Response(401, json={"error": "nope"}))
    out = judge_flips(client, INTENT, change, [flip("a-test")])
    assert out[0].kind == "silent" and "HTTP 401" in out[0].reason


def test_existing_location_and_fix_are_kept(make_client, change):
    f = flip("a-test", location=Location("src/physics.js", 2, "x", "y"))
    out = judge_flips(make_client(make_client.ok(verdicts(("a-test", "silent", "r")))), INTENT, change, [f])
    assert out[0].location is f.location


def test_prompt_carries_intent_pr_diff_and_each_flip(make_client, change):
    client = make_client(make_client.ok(verdicts(("a-test", "silent", "r"))))
    judge_flips(client, INTENT, change, [flip("a-test")])
    sent = client.sent[0]
    user = sent["messages"][-1]["content"]
    assert sent["model"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert sent["response_format"]["json_schema"]["schema"] == JUDGE_SCHEMA
    for needle in ("Tidy clamp", "Small cleanup.", "clamp stops returning the bound itself", "hi - 1",
                   "a-test claim", "// test code of a-test", "AssertionError in a-test"):
        assert needle in user


def test_the_judge_reads_a_stated_rule_as_covering_every_input_and_unchanged_as_silent(change):
    system = build_judge_messages(INTENT, change, [flip("a-test")])[0]["content"]

    assert "A stated rule announces every input it applies to, not only its examples" in system
    assert "an input under an exception the text states, is silent" in system
    assert "whatever the diff or its comments suggest" in system


def test_the_judge_applies_the_rule_to_each_input_before_it_labels_the_flip(change):
    keys = list(JUDGE_SCHEMA["properties"]["verdicts"]["items"]["properties"])
    assert keys.index("rule_gives") < keys.index("kind") and keys.index("head_gives") < keys.index("kind")
    system = build_judge_messages(INTENT, change, [flip("a-test")])[0]["content"]
    assert "the reading that every example fits is the rule" in system
    assert "A flip is intended only when both are the same result" in system
