#!/usr/bin/env python3
"""Offline tests for retry-note classification in both drivers (GH-84).

Every verdict here comes from the real verify.py, because the bug was a
disagreement between what verify emits and what the drivers read, and a
hand-written fixture would have encoded one side of it. That is not
hypothetical: the stub in test_match_voice.py said {"type": "numbers"},
which matched the reader rather than the producer, and the suite passed
green while no specific retry note had ever fired.

Two failures, opposite directions, same cause:

  match_voice.py  keyed findings on "type", which no finding carries, so
                  every set was {""} and every retry got COPY_NOTE.
  drive.py        searched the verdict TEXT for '"markup"' and '"dashes"',
                  which are top-level measurement keys present in every
                  verdict — so both notes rode on every retry, whatever had
                  failed, and every anchored paragraph drew a bogus
                  "similarity" advisory.

No network, no model. Run: python3 <skill>/scripts/testdata/test_retry_notes.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402
import verify  # noqa: E402


def _verdict(original, rewrite, **kw):
    """A real verdict, as both the dict and the JSON the CLI would print."""
    v = verify.verify(original, rewrite, **kw)
    return v, json.dumps(v)


# The measured shapes: one thing wrong in each.
NUM_ORIG = "The system processed 12 requests under [@key-one]."
NUM_BAD = "The system processed 15 requests under [@key-one]."
MARKUP_ORIG = "The baseline cannot be reconstructed afterwards."
MARKUP_BAD = "The baseline **cannot** be reconstructed afterwards."
DASH_ORIG = "The baseline is captured before the rewrite starts, not after."
DASH_BAD = "The baseline is captured before the rewrite starts — not after."


def test_checks_in_reads_findings_only():
    """The top-level markup/dashes/similarity keys are measurements. A
    numbers-only verdict must classify as numbers and nothing else."""
    v, txt = _verdict(NUM_ORIG, NUM_BAD)
    assert verify.checks_in(v) == {"numbers"}, v["findings"]
    assert verify.checks_in(txt) == {"numbers"}, "JSON text and dict disagree"
    # The keys the old substring test matched are all still there.
    assert {"markup", "dashes", "similarity"} <= set(v), sorted(v)
    print("  checks_in_reads_findings_only: ok")


def test_checks_in_severity_filter():
    v, _ = _verdict("Throughput rose 12% under NASA control.",
                    "Throughput rose 12% under control.")
    assert "terms" in verify.checks_in(v)
    assert "terms" in verify.checks_in(v, severity="warn")
    assert "terms" not in verify.checks_in(v, severity="fatal")
    print("  checks_in_severity_filter: ok")


def test_checks_in_survives_a_crashed_gate():
    """A gate that crashed prints no verdict. Classifying nothing is the
    safe answer; the driver's COPY_NOTE fallback then applies."""
    for junk in ("{}", "", "Traceback (most recent call last):", "null",
                 "[]", None, 17):
        assert verify.checks_in(junk) == set(), repr(junk)
    print("  checks_in_survives_a_crashed_gate: ok")


def test_drive_note_is_only_what_failed():
    """The regression: a numbers failure must not carry markup and dash
    instructions. Before GH-84 this note contained all three."""
    _, txt = _verdict(NUM_ORIG, NUM_BAD)
    note = drive.retry_notes(txt)
    assert drive.NUM_NOTE in note
    assert drive.MARKUP_NOTE not in note, "markup note rode along"
    assert drive.DASH_NOTE not in note, "dash note rode along"
    assert drive.COPY_NOTE not in note
    print("  drive_note_is_only_what_failed: ok")


def test_drive_note_per_failure_kind():
    for orig, bad, want, unwanted in (
            (MARKUP_ORIG, MARKUP_BAD, drive.MARKUP_NOTE, drive.DASH_NOTE),
            (DASH_ORIG, DASH_BAD, drive.DASH_NOTE, drive.MARKUP_NOTE)):
        _, txt = _verdict(orig, bad)
        note = drive.retry_notes(txt)
        assert want in note, txt
        assert unwanted not in note, f"unearned note for {orig!r}"
        assert drive.NUM_NOTE not in note
    print("  drive_note_per_failure_kind: ok")


def test_drive_note_combines_real_multiple_failures():
    """Two genuine failures earn two notes — the behaviour the old code
    faked by always emitting them."""
    _, txt = _verdict("The run took 12 seconds and stayed plain.",
                      "The run took 15 seconds — and turned **bold**.")
    note = drive.retry_notes(txt)
    assert drive.NUM_NOTE in note and drive.MARKUP_NOTE in note \
        and drive.DASH_NOTE in note, note
    print("  drive_note_combines_real_multiple_failures: ok")


def test_drive_note_falls_back_to_copy_note():
    """A rejection with no classifiable finding still has to say something,
    and a crashed gate must not be read as 'everything failed'."""
    assert drive.retry_notes("{}") == drive.COPY_NOTE
    assert drive.retry_notes("Traceback...") == drive.COPY_NOTE
    print("  drive_note_falls_back_to_copy_note: ok")


def test_drive_protected_term_note_still_names_terms():
    """term_note parses the findings properly and always did; the extraction
    must not have lost it."""
    _, txt = _verdict("The decision plane sits above the detector.",
                      "The choice layer sits above the detector.",
                      protected_terms=["decision plane"])
    note = drive.retry_notes(txt)
    assert "decision plane" in note, note
    print("  drive_protected_term_note_still_names_terms: ok")


def test_similarity_measurement_is_not_a_finding():
    """The other half of the bug: with anchors retrieved and no violation,
    verify still reports a similarity MEASUREMENT. Reading that as a warning
    flagged every anchored paragraph in every run."""
    anchors = [{"file": "a1.md", "text": "Entirely unrelated exemplar prose "
                                         "about copper and hot dogs."}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(anchors, f)
        path = f.name
    try:
        v, _ = _verdict("The original paragraph text stands here.",
                        "A rewrite of that paragraph stands here.",
                        anchors_json=path)
    finally:
        os.unlink(path)
    assert v["similarity"] is not None, "guard did not run"
    assert v["similarity"]["violation"] is False
    assert bool(v["similarity"]) is True, "the truthiness the old test read"
    assert "similarity" not in verify.checks_in(v), v["findings"]
    print("  similarity_measurement_is_not_a_finding: ok")


def test_match_voice_sends_the_specific_note_on_retry():
    """End to end through match_voice_paragraph: the note the model actually
    receives on attempt 2. Before GH-84 this was COPY_NOTE every time."""
    import types
    from unittest import mock
    import match_voice as mv

    seen = []
    verify_mod = types.ModuleType("verify")
    verify_mod.checks_in = verify.checks_in

    def stub_verify(original, rewritten, anchors_json=None, max_shared_run=8):
        return verify.verify(NUM_ORIG, NUM_BAD)      # a real failing verdict
    verify_mod.verify = stub_verify

    rewrite_mod = types.ModuleType("rewrite")

    def stub_rewrite(paragraph, anchors, endpoint="", model="",
                     temperature=0.7, retry_note="", timeout=300):
        seen.append(retry_note)
        return "A rewrite of the paragraph that the gate will reject."
    rewrite_mod.rewrite = stub_rewrite

    with mock.patch.object(mv, "_import_sibling") as imp:
        def side(name):
            return {"verify": verify_mod, "rewrite": rewrite_mod}.get(
                name) or __import__(name)
        imp.side_effect = side
        fake = mock.MagicMock()
        fake.returncode = 0
        fake.stdout = "[]"
        with mock.patch("subprocess.run", return_value=fake):
            result = mv.match_voice_paragraph(
                NUM_ORIG, voice_dir="/tmp/fake-voice", retries=1)

    assert result["accepted"] is False
    assert len(seen) == 2, seen
    assert seen[0] == "", "first attempt should carry no retry note"
    assert mv.NUM_NOTE in seen[1], seen[1]
    assert mv.COPY_NOTE not in seen[1], "the generic fallback fired instead"
    assert mv.MARKUP_NOTE not in seen[1] and mv.DASH_NOTE not in seen[1]
    assert result["warnings"] == [], result["warnings"]
    print("  match_voice_sends_the_specific_note_on_retry: ok")


def main():
    test_checks_in_reads_findings_only()
    test_checks_in_severity_filter()
    test_checks_in_survives_a_crashed_gate()
    test_drive_note_is_only_what_failed()
    test_drive_note_per_failure_kind()
    test_drive_note_combines_real_multiple_failures()
    test_drive_note_falls_back_to_copy_note()
    test_drive_protected_term_note_still_names_terms()
    test_similarity_measurement_is_not_a_finding()
    test_match_voice_sends_the_specific_note_on_retry()
    print("test_retry_notes: all assertions passed")


if __name__ == "__main__":
    main()
