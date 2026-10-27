from noether.comment import MARK, render_markdown


def _bundle(**over):
    base = {
        "verdict": "BROKEN",
        "reason": "One pinned invariant broke without being announced.",
        "invariants": [
            {"name": "air-momentum", "claim": "speed holds in the air", "kind": "silent"},
            {"name": "coyote", "claim": "jump allowed 4 frames after a ledge", "kind": "intended"},
            {"name": "coins", "claim": "a coin counts once", "kind": "held"},
            {"name": "bad", "claim": "x", "kind": "dropped"},
        ],
        "breaks": [{"invariant": "air-momentum", "file": "src/physics.js", "line": 42,
                    "why": "friction | runs in the air", "fix": {"diff": "-a\n+b", "proved": True}}],
        "own_suite": {"head": {"ran": True, "exit_code": 0}},
        "sha256": "ab" * 32,
        "cost_est_usd": 0.0123,
    }
    base.update(over)
    return base


def test_broken_comment_lists_break_fix_and_counts():
    md = render_markdown(_bundle(), "https://example.org/runs/1")
    assert md.startswith(MARK)
    assert "Broken" in md
    assert "Pinned 3 invariants on base: 1 held on head, 1 changed as announced, 1 broke silently." in md
    assert "`src/physics.js:42`" in md and "re-proved" in md
    assert "friction \\| runs in the air" in md  # pipes escaped so the table holds
    assert "```diff" in md and "[proof bundle](https://example.org/runs/1)" in md
    assert "own suite passed on head" in md


def test_conserved_comment_has_no_break_table():
    md = render_markdown(_bundle(verdict="CONSERVED", reason="", breaks=[]))
    assert "Conserved" in md and "| Silent break |" not in md


def test_unproved_fix_is_not_shown_as_a_diff():
    b = _bundle()
    b["breaks"][0]["fix"] = {"diff": "-a\n+b", "proved": False}
    md = render_markdown(b)
    assert "proposed, not proved" in md and "```diff" not in md
