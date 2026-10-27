import json

from noether.fix import LOCATE_FIX_SCHEMA, locate_and_propose, validate_location
from noether.model import Change, ChangedFile, Flip, Hunk, Invariant, Location

FLIP = Flip(Invariant("clamp-upper-bound", "clamp returns the upper bound", "src/physics.js", "clamp", "// test"),
            "AssertionError: 9 !== 10")


def proposal(**over):
    data = {"file": "src/physics.js", "line": 3, "code": "if (x >= hi) return hi - 1;",
            "why": "the bound check now excludes the bound itself",
            "search": "if (x >= hi) return hi - 1;", "replace": "if (x > hi) return hi;"}
    data.update(over)
    return data


def run(make_client, change, **over):
    client = make_client(make_client.ok(json.dumps(proposal(**over))))
    return locate_and_propose(client, change, FLIP), client


def test_valid_location_and_fix(make_client, change):
    (loc, fix), client = run(make_client, change)
    assert loc == Location("src/physics.js", 3, "if (x >= hi) return hi - 1;", "the bound check now excludes the bound itself")
    assert fix.file == "src/physics.js" and fix.proved is False
    assert fix.new_source == change.files[0].base_source  # the edit restores the base text exactly
    assert "-  if (x >= hi) return hi - 1;" in fix.diff and "+  if (x > hi) return hi;" in fix.diff
    assert fix.diff.startswith("--- a/src/physics.js\n+++ b/src/physics.js")
    assert client.sent[0]["model"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert client.sent[0]["response_format"]["json_schema"]["schema"] == LOCATE_FIX_SCHEMA


def test_the_real_line_replaces_the_models_quote(make_client, change):
    (loc, _), _ = run(make_client, change, code="  if (x >= hi)")
    assert loc.code == "if (x >= hi) return hi - 1;"


def test_line_outside_a_hunk_gives_a_fix_without_a_location(make_client, change):
    (loc, fix), _ = run(make_client, change, line=8, code="return Math.round(cents) / 100;")
    assert loc is None and fix is not None


def test_a_quote_that_does_not_match_the_line_is_unlocated(make_client, change):
    (loc, fix), _ = run(make_client, change, line=2, code="if (x >= hi) return hi - 1;")
    assert loc is None and fix is not None


def test_line_number_out_of_range_or_empty_quote_is_unlocated(make_client, change):
    assert run(make_client, change, line=99)[0][0] is None
    assert run(make_client, change, line=0)[0][0] is None
    assert run(make_client, change, code="  ")[0][0] is None


def test_search_must_occur_exactly_once(make_client, change):
    (loc, fix), _ = run(make_client, change, search="return", replace="return 0")
    assert loc is not None and fix is None


def test_search_not_found_or_empty_or_unchanged(make_client, change):
    assert run(make_client, change, search="not in the file")[0][1] is None
    assert run(make_client, change, search="")[0][1] is None
    assert run(make_client, change, replace="if (x >= hi) return hi - 1;")[0][1] is None


def test_unchanged_or_non_code_files_give_nothing(make_client, change):
    assert run(make_client, change, file="src/other.js")[0] == (None, None)
    assert run(make_client, change, file="README.md", line=1, code="new", search="new", replace="old")[0] == (None, None)


def test_an_added_file_can_be_fixed(make_client, change):
    (loc, fix), _ = run(make_client, change, file="src/new.js", line=1, code="export const x = 1;",
                        search="x = 1", replace="x = 2")
    assert loc.file == "src/new.js" and fix.new_source == "export const x = 2;\n"


def test_leading_dot_slash_is_tolerated(make_client, change):
    (loc, fix), _ = run(make_client, change, file="./src/physics.js")
    assert loc is not None and fix is not None


def test_model_failure_is_no_fix(make_client, change):
    client = make_client(make_client.ok("nothing useful"), make_client.ok("still nothing"))
    assert locate_and_propose(client, change, FLIP) == (None, None)


def test_crlf_sources_still_match(make_client):
    head = "function f() {\r\n  return 1;\r\n}\r\n"
    change = Change("a/b", "main", "pr", diff="diff --git a/f.js b/f.js\n",
                    files=[ChangedFile("f.js", "modified", [Hunk(1, 3)], "x", head)])
    client = make_client(make_client.ok(json.dumps(proposal(file="f.js", line=2, code="return 1;",
                                                           search="function f() {\n  return 1;", replace="function f() {\n  return 2;"))))
    loc, fix = locate_and_propose(client, change, FLIP)
    assert fix.new_source == "function f() {\r\n  return 2;\r\n}\r\n" and loc.line == 2


def test_validate_location(change):
    def at(line, file="src/physics.js"):
        return validate_location(Location(file, line, "", ""), change)

    assert at(1) and at(5)  # first and last line of the hunk 1..5
    assert not at(6) and not at(0)
    assert not at(1, "src/missing.js")
    assert at(2, "src/new.js")  # an added file counts as changed


def test_validate_location_edge_cases():
    change = Change("a/b", "main", "pr", files=[
        ChangedFile("gone.js", "removed", [Hunk(1, 0)], "x", None),
        ChangedFile("cut.js", "modified", [Hunk(10, 0)], "x", "y\n" * 20),
        ChangedFile("nohunks.js", "modified", [], "x", "y"),
    ])
    assert not validate_location(Location("gone.js", 1, "", ""), change)  # no head source
    assert validate_location(Location("cut.js", 10, "", ""), change)  # a pure deletion: the line before the cut
    assert not validate_location(Location("cut.js", 11, "", ""), change)
    assert not validate_location(Location("nohunks.js", 1, "", ""), change)


def test_prompt_has_numbered_head_source_diff_and_the_failure(make_client, change):
    _, client = run(make_client, change)
    user = client.sent[0]["messages"][-1]["content"]
    assert "   3|   if (x >= hi) return hi - 1;" in user
    for needle in ("clamp-upper-bound", "clamp returns the upper bound", "AssertionError: 9 !== 10", "diff --git a/src/physics.js"):
        assert needle in user
    assert "README" not in user.split("HEAD source of changed files:")[1]
