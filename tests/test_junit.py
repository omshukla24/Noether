from pathlib import Path

from noether.junit import MAX_FAILURE_CHARS, parse_counts, parse_junit, pinned_filename

# Captured from `node --test --test-reporter=junit` on Node 24 (paths and host scrubbed).
REAL = (Path(__file__).parent / "data" / "node24_junit_stdout.txt").read_text(encoding="utf-8")
NAMES = ["a_pass", "b_fail", "c_import_error", "d_multi", "e_missing"]


def test_real_report_maps_every_file_to_its_name():
    results = parse_junit(REAL, NAMES)

    assert list(results) == NAMES
    assert results["a_pass"].passed and results["a_pass"].output == ""
    assert not results["b_fail"].passed and "3 !== 2.99" in results["b_fail"].output
    assert not results["c_import_error"].passed and "does not provide an export" in results["c_import_error"].output


def test_one_failing_subtest_fails_the_whole_file():
    result = parse_junit(REAL, NAMES)["d_multi"]

    assert not result.passed
    assert "0 !== 7" in result.output
    assert result.ms > 0


def test_a_file_that_reported_nothing_did_not_run():
    result = parse_junit(REAL, NAMES)["e_missing"]

    assert not result.passed
    assert result.output.startswith("did not run")


def test_output_printed_before_the_report_is_ignored():
    assert REAL.startswith("noise before the report")
    assert parse_junit(REAL, ["a_pass"])["a_pass"].passed


def test_no_report_at_all_fails_every_test_and_says_why():
    # A test that calls process.exit(0) ends the whole run with no report; that must not look green.
    results = parse_junit("noise before the report\n", ["a_pass", "b_fail"])

    assert not any(r.passed for r in results.values())
    assert "no junit report" in results["a_pass"].output


def test_broken_xml_fails_closed():
    results = parse_junit("<?xml version='1.0'?><testsuites><testcase></testsuites>", ["a_pass"])

    assert not results["a_pass"].passed
    assert "not valid XML" in results["a_pass"].output


def test_failure_text_is_cut_to_4kb():
    big = "x" * 20_000
    xml = (
        '<?xml version="1.0"?><testsuites>'
        f'<testcase name="t" file="/w/.noether/pinned/big.test.mjs"><failure message="m">{big}</failure></testcase>'
        "</testsuites>"
    )

    assert len(parse_junit(xml, ["big"])["big"].output) <= MAX_FAILURE_CHARS


def test_skipped_test_does_not_count_as_green():
    xml = (
        '<?xml version="1.0"?><testsuites>'
        '<testcase name="t" file="/w/.noether/pinned/s.test.mjs"><skipped/></testcase></testsuites>'
    )

    assert not parse_junit(xml, ["s"])["s"].passed


def test_windows_and_posix_paths_both_match():
    xml = (
        '<?xml version="1.0"?><testsuites>'
        '<testcase name="t" file="C:\\w\\.noether\\pinned\\win.test.mjs"/>'
        '<testcase name="t" file="/w/.noether/pinned/nix.test.mjs"/></testsuites>'
    )

    results = parse_junit(xml, ["win", "nix"])

    assert results["win"].passed and results["nix"].passed


def test_unsafe_characters_in_a_name_never_reach_the_file_name():
    assert pinned_filename("../evil name") == ".._evil_name.test.mjs"
    assert "/" not in pinned_filename("a/b\\c")


def test_counts_from_node_spec_reporter():
    out = "ℹ tests 6\nℹ suites 0\nℹ pass 5\nℹ fail 1\nℹ cancelled 0\n"
    assert parse_counts(out) == (5, 1)


def test_counts_from_tap():
    assert parse_counts("# tests 3\n# pass 3\n# fail 0\n") == (3, 0)


def test_counts_from_mocha_and_jest():
    assert parse_counts("  4 passing (12ms)\n  2 failing\n") == (4, 2)
    assert parse_counts("Tests:       1 failed, 5 passed, 6 total\n") == (5, 1)


def test_counts_default_to_zero_when_unrecognised():
    assert parse_counts("something else entirely") == (0, 0)
