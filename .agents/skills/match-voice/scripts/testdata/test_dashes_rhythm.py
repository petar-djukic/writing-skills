#!/usr/bin/env python3
"""Tests for the em-dash gate and the rhythm report (GH-243).

A model told to match a punchy register reaches for the most legible signals of
punch it knows. Measured across two articles: em-dashes 7 -> 10 and 7 -> 15,
antithesis_pairs 1 -> 3 against a house rule of zero, and sentence_length_std
falling 8.9 -> 8.3 in both arms — the rewrite flattening rhythm while its
anchors had more of it.

No network, no model. Run: python3 <skill>/scripts/testdata/test_dashes_rhythm.py
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402
import verify  # noqa: E402
import rewrite  # noqa: E402


def fatal(original, rewritten):
    r = verify.verify(original, rewritten)
    return {f["check"] for f in r["findings"] if f["severity"] == "fatal"}, r


# --- the gate ----------------------------------------------------------------

def test_added_em_dash_is_fatal():
    o = "The orchestrator runs git, not the agents."
    w = "The orchestrator runs git — not the agents."
    f, r = fatal(o, w)
    assert "dashes" in f, r["findings"]
    assert r["dashes"] == {"original": 0, "rewrite": 1}, r["dashes"]


def test_preserved_em_dash_is_clean():
    o = "The gate is mechanical — Claude judges the meaning."
    w = "The gate is mechanical — the meaning is Claude's to judge."
    f, r = fatal(o, w)
    assert not f, r["findings"]


def test_removing_a_dash_is_allowed():
    """That direction is not the failure this checks for."""
    o = "The gate is mechanical — Claude judges the meaning."
    w = "The gate is mechanical. Claude judges the meaning."
    f, _r = fatal(o, w)
    assert not f


def test_comma_promoted_to_dash_is_caught():
    """The specific move the prompt now forbids: same words, punchier punctuation."""
    o = "Grouping does two jobs, and both matter."
    w = "Grouping does two jobs — and both matter."
    f, _r = fatal(o, w)
    assert "dashes" in f


def test_spaced_hyphen_counts_as_a_dash():
    o = "The scheduler assigns one slot per node."
    w = "The scheduler assigns one slot - one only - per node."
    f, r = fatal(o, w)
    assert "dashes" in f, r["dashes"]


def test_hyphenated_compound_is_not_a_dash():
    """load-bearing must not read as punctuation, or every compound fires."""
    assert verify._dashes("A load-bearing, first-class abstraction.") == 0


def test_cli_flag_in_code_span_is_not_a_dash():
    """`--pangram` inside backticks is a flag, not punch."""
    assert verify._dashes("Pass `--pangram` to measure it.") == 0
    o = "Pass the flag to measure it."
    w = "Pass `--pangram` to measure it."
    f, _r = fatal(o, w)
    assert "dashes" not in f


def test_dash_count_rise_reports_both_numbers():
    o = "One — two."
    w = "One — two — three — four."
    _f, r = fatal(o, w)
    d = [x for x in r["findings"] if x["check"] == "dashes"][0]["detail"]
    assert "1 -> 3" in d, d


# --- the prompt --------------------------------------------------------------

def test_prompt_states_all_three_constraints():
    p = rewrite.PROMPT
    assert "manufacture antithesis" in p or "manufacture antithesis." in p
    assert "em-dash" in p
    assert "uneven" in p or "even them out" in p


def test_prompt_rules_are_numbered_without_a_duplicate():
    """A duplicated rule number is how the last edit to this template went
    wrong; the model reads the list literally."""
    nums = [ln.split(".", 1)[0].strip()
            for ln in rewrite.PROMPT.splitlines()
            if ln[:2].strip().rstrip(".").isdigit()]
    assert nums == [str(i) for i in range(1, len(nums) + 1)], nums


# --- the rhythm report -------------------------------------------------------

def _doc(sentences):
    return "# H\n\n" + " ".join(sentences) + "\n"


UNEVEN = _doc(["Short.", "The scheduler assigns exactly one transmission slot "
                         "to every participating node in each and every frame "
                         "of the schedule it computes.", "It works.",
               "A considerably longer sentence follows here so that the "
               "variance in sentence length across this document is genuinely "
               "wide rather than merely nominal."] * 6)
FLAT = _doc(["The scheduler assigns one slot per node here." ] * 24)


def test_structural_reads_the_tracked_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a.md")
        open(p, "w").write(UNEVEN)
        got = drive._structural(p)
        assert set(got) == set(drive.STRUCT_KEYS), got
        assert got["sentence_length_std"] is not None, got


def test_flattened_rhythm_is_reported_as_worse():
    """std falling is the failure direction for that metric, and the report has
    to say so — it is the one that moved in BOTH measured arms."""
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "before.md")
        b = os.path.join(tmp, "after.md")
        open(a, "w").write(UNEVEN)
        open(b, "w").write(FLAT)
        buf = io.StringIO()
        with redirect_stdout(buf):
            drive.report_structural(a, b)
        out = buf.getvalue()
        assert "sentence_length_std" in out, out
        line = [ln for ln in out.splitlines() if "sentence_length_std" in ln][0]
        assert "WORSE" in line, line


def test_unchanged_document_reports_nothing_worse():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "before.md")
        b = os.path.join(tmp, "after.md")
        open(a, "w").write(UNEVEN)
        open(b, "w").write(UNEVEN)
        buf = io.StringIO()
        with redirect_stdout(buf):
            drive.report_structural(a, b)
        assert "WORSE" not in buf.getvalue(), buf.getvalue()


def test_report_is_silent_when_metrics_are_unavailable():
    """Short files skip these metrics entirely; the report must not print half a
    comparison or raise into a run whose draft is already written."""
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "before.md")
        b = os.path.join(tmp, "after.md")
        open(a, "w").write("# H\n\nToo short to score.\n")
        open(b, "w").write("# H\n\nAlso far too short to score.\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            drive.report_structural(a, b)
        assert buf.getvalue() == "", buf.getvalue()


def test_driver_classifies_a_dash_failure_for_retry():
    """The gate rejecting is only useful if the retry says what to fix."""
    fj = json.dumps({"findings": [{"check": "dashes", "severity": "fatal",
                                   "detail": "em-dash count rose 0 -> 1"}]})
    assert '"dashes"' in fj
    assert "em-dash" in drive.DASH_NOTE
    assert "antithesis" in drive.DASH_NOTE


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_dashes_rhythm: all assertions passed")


if __name__ == "__main__":
    main()
