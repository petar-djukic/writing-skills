#!/usr/bin/env python3
"""Tests for match_voice_paragraph — mocked subprocess calls."""
import os
import sys
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _make_verify_module():
    """Stub verify module returning clean or dirty results.

    The finding is keyed "check" because that is what the real verify()
    emits. It used to say "type", which matched the reader in match_voice.py
    rather than the producer — so the stub agreed with the bug and the tests
    passed while no retry note ever fired (GH-84). A stub that invents its
    own shape tests nothing; checks_in comes from the real module for the
    same reason.
    """
    import verify as real_verify
    mod = types.ModuleType("verify")
    mod._clean = True

    def verify(original, rewritten, anchors_json=None, max_shared_run=8):
        if mod._clean:
            return {"clean": True, "findings": [], "similarity": None}
        return {"clean": False, "similarity": None,
                "findings": [{"check": "numbers", "severity": "fatal",
                              "detail": "number '12' lost or altered"}]}
    mod.verify = verify
    mod.checks_in = real_verify.checks_in
    return mod


def _make_rewrite_module():
    mod = types.ModuleType("rewrite")

    def rewrite(paragraph, anchors, endpoint="", model="", temperature=0.7,
                retry_note="", timeout=300):
        return "Rewritten paragraph text with matching voice here."
    mod.rewrite = rewrite
    return mod


def test_returns_shape():
    import match_voice as mv
    verify_mod = _make_verify_module()
    rewrite_mod = _make_rewrite_module()

    with mock.patch.object(mv, "_import_sibling") as imp:
        def side(name):
            if name == "verify":
                return verify_mod
            if name == "rewrite":
                return rewrite_mod
            import retrieve
            return retrieve
        imp.side_effect = side

        fake_retrieve = mock.MagicMock()
        fake_retrieve.returncode = 0
        fake_retrieve.stdout = '[]'

        with mock.patch("subprocess.run", return_value=fake_retrieve):
            result = mv.match_voice_paragraph(
                "A paragraph with enough words to be worth rewriting.",
                voice_dir="/tmp/fake-voice")

    assert "accepted" in result
    assert "rewritten" in result
    assert "findings" in result
    assert "attempts" in result
    assert "anchors" in result
    assert isinstance(result["accepted"], bool)
    print("  returns_shape: ok")


def test_accepted_when_clean():
    import match_voice as mv
    verify_mod = _make_verify_module()
    verify_mod._clean = True
    rewrite_mod = _make_rewrite_module()

    with mock.patch.object(mv, "_import_sibling") as imp:
        def side(name):
            if name == "verify":
                return verify_mod
            if name == "rewrite":
                return rewrite_mod
            import retrieve
            return retrieve
        imp.side_effect = side

        fake = mock.MagicMock()
        fake.returncode = 0
        fake.stdout = '[]'

        with mock.patch("subprocess.run", return_value=fake):
            result = mv.match_voice_paragraph(
                "A paragraph with enough words.", voice_dir="/tmp/fake")

    assert result["accepted"] is True
    assert result["rewritten"] is not None
    assert result["attempts"] == 1
    print("  accepted_when_clean: ok")


def test_rejected_after_retries():
    import match_voice as mv
    verify_mod = _make_verify_module()
    verify_mod._clean = False
    rewrite_mod = _make_rewrite_module()

    with mock.patch.object(mv, "_import_sibling") as imp:
        def side(name):
            if name == "verify":
                return verify_mod
            if name == "rewrite":
                return rewrite_mod
            import retrieve
            return retrieve
        imp.side_effect = side

        fake = mock.MagicMock()
        fake.returncode = 0
        fake.stdout = '[]'

        with mock.patch("subprocess.run", return_value=fake):
            result = mv.match_voice_paragraph(
                "A paragraph with enough words.", voice_dir="/tmp/fake",
                retries=1)

    assert result["accepted"] is False
    assert result["rewritten"] is None
    assert result["attempts"] == 2
    assert len(result["findings"]) > 0
    print("  rejected_after_retries: ok")


def test_restore_full_bold():
    import match_voice as mv
    orig = "**Bold line here**\nNormal line here"
    cand = "Bold line modified\nNormal line modified"
    fixed = mv._restore_full_bold(orig, cand)
    assert fixed.startswith("**"), f"bold not restored: {fixed}"
    assert "Normal line modified" in fixed
    print("  restore_full_bold: ok")


def test_verify_list_anchors_empty():
    # GH-318: drive.py --no-anchors writes [] (a bare list) to the anchors
    # JSON. verify() must treat that as "no anchors", not crash on .get().
    import json
    import tempfile
    import verify as vf
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([], f)
        path = f.name
    try:
        result = vf.verify("The original paragraph text.",
                           "A rewrite of the paragraph.", anchors_json=path)
    finally:
        os.unlink(path)
    assert result["clean"] is True
    assert result["similarity"] is None
    print("  verify_list_anchors_empty: ok")


def test_verify_list_anchors_nonempty():
    # Bare-list format with content: the similarity guard runs, no crash.
    import json
    import tempfile
    import verify as vf
    anchors = [{"file": "a1.md", "text": "Entirely unrelated exemplar prose."}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(anchors, f)
        path = f.name
    try:
        result = vf.verify("The original paragraph text.",
                           "A rewrite of the paragraph.", anchors_json=path)
    finally:
        os.unlink(path)
    assert result["clean"] is True
    assert result["similarity"] is not None
    print("  verify_list_anchors_nonempty: ok")


def test_verify_dict_anchors():
    # The dict form {"anchors": [...]} keeps working.
    import json
    import tempfile
    import verify as vf
    payload = {"anchors": [{"file": "a1.md",
                            "text": "Entirely unrelated exemplar prose."}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        path = f.name
    try:
        result = vf.verify("The original paragraph text.",
                           "A rewrite of the paragraph.", anchors_json=path)
    finally:
        os.unlink(path)
    assert result["clean"] is True
    assert result["similarity"] is not None
    print("  verify_dict_anchors: ok")


def test_classify_gate_crash():
    # GH-319: a verify.py crash (nonzero exit, traceback on stderr, no JSON
    # verdict) is a gate-error, not a rejection. A rejection carries a JSON
    # verdict on stdout even though the exit code is nonzero.
    import drive
    crash = drive.classify_gate_crash(
        1, "", 'Traceback (most recent call last):\n  AttributeError: ...')
    assert crash is not None
    assert crash["status"] == "gate-error"
    assert "AttributeError" in crash["err"]

    # Rejection: nonzero exit WITH a JSON verdict — normal path, no crash.
    rejection = drive.classify_gate_crash(1, '{"clean": false}', "")
    assert rejection is None

    # Pass: exit 0 — normal path.
    passed = drive.classify_gate_crash(0, '{"clean": true}', "")
    assert passed is None

    # Crash with empty stderr still yields a non-empty reason.
    silent = drive.classify_gate_crash(2, "", "")
    assert silent["status"] == "gate-error"
    assert silent["err"]
    print("  classify_gate_crash: ok")


def test_compose_note():
    # GH-323: the standing style note rides on every attempt; a retry's
    # failure note is appended after it. Empty when both are absent, so the
    # caller's truthiness check keeps first attempts note-free by default.
    import drive
    assert drive.compose_note("", None) == ""
    assert drive.compose_note("active voice", None) == "active voice"
    assert drive.compose_note("", "keep the numbers") == "keep the numbers"
    assert drive.compose_note("active voice", "keep the numbers") \
        == "active voice keep the numbers"
    print("  compose_note: ok")


def test_parse_paragraph_selection():
    # GH-322: 'N,M-K' syntax, 1-based, validated against the paragraph count
    # before any model call.
    import drive
    parse = drive.parse_paragraph_selection
    assert parse("3", 10) == {3}
    assert parse("1,3,5", 10) == {1, 3, 5}
    assert parse("2-4", 10) == {2, 3, 4}
    assert parse("1,3-5,9", 10) == {1, 3, 4, 5, 9}
    assert parse(" 1 , 3-5 ", 10) == {1, 3, 4, 5}
    for bad in ("abc", "1-2-3", "0", "11", "5-11", "5-3", "", ","):
        try:
            parse(bad, 10)
            assert False, f"selection '{bad}' should have raised"
        except ValueError:
            pass
    print("  parse_paragraph_selection: ok")


def test_compress_ranges():
    # The next-pass string round-trips through the selection parser.
    import drive
    assert drive.compress_ranges([1, 3, 4, 5, 9]) == "1,3-5,9"
    assert drive.compress_ranges([2]) == "2"
    assert drive.compress_ranges([1, 2, 3]) == "1-3"
    assert drive.compress_ranges([5, 1, 2]) == "1-2,5"
    spec = drive.compress_ranges([1, 3, 4, 5, 9])
    assert drive.parse_paragraph_selection(spec, 10) == {1, 3, 4, 5, 9}
    print("  compress_ranges: ok")


def test_readability_guard():
    # GH-324: relative-increase thresholds on register per_1000 rates. The
    # calibrating case (passive 4.1 -> 8.6, +110%) must warn; drift below
    # threshold and improvements must not.
    import drive
    guard = drive.readability_guard

    warns = guard({"passive": 4.1, "nominalization": 35.4, "filler": 1.8},
                  {"passive": 8.6, "nominalization": 33.7, "filler": 1.8})
    assert [w["metric"] for w in warns] == ["passive"]
    assert warns[0]["rise_pct"] > 100

    # Below threshold: passive +40% under the 50% ceiling.
    assert guard({"passive": 5.0}, {"passive": 7.0}) == []
    # Improvement never warns.
    assert guard({"passive": 8.0}, {"passive": 4.0}) == []
    # Nominalization has the tighter 25% ceiling.
    warns = guard({"nominalization": 20.0}, {"nominalization": 26.0})
    assert [w["metric"] for w in warns] == ["nominalization"]
    # From zero: no relative rise; warns only at a visible absolute rate.
    assert guard({"filler": 0.0}, {"filler": 1.0}) == []
    warns = guard({"filler": 0.0}, {"filler": 3.0})
    assert warns and warns[0]["rise_pct"] is None
    # Missing metrics are skipped, not crashed on.
    assert guard({}, {"passive": 9.9}) == []
    print("  readability_guard: ok")


def test_first_person_introduced():
    import verify as vf
    orig = ("The assumption came from the API shape the whole industry "
            "integrates against.")
    # The recorded live pastiche (2026-09-01, the-qwerty-endpoint): fatal.
    cand = (orig + " I might not understand, being too thick-skulled to see "
            "the new era clearly. But in my view, trouble is brewing just "
            "over the horizon.")
    v = vf.verify(orig, cand)
    checks = [f["check"] for f in v["findings"] if f["severity"] == "fatal"]
    assert "first-person-introduced" in checks, v
    # Original carrying first person keeps the check silent.
    orig_we = "We banned a model from our writing pipeline."
    v = vf.verify(orig_we, "We denylisted a model in our pipeline.")
    assert "first-person-introduced" not in [f["check"] for f in v["findings"]]
    # 'US' the country and 'usable' never trip; capitalized 'We' does.
    v = vf.verify("The US market is usable.", "The US market stays usable.")
    assert "first-person-introduced" not in [f["check"] for f in v["findings"]]
    v = vf.verify("The market is broken.", "We think the market is broken.")
    assert "first-person-introduced" in [
        f["check"] for f in v["findings"] if f["severity"] == "fatal"]
    print("  first_person_introduced: ok")


def main():
    test_returns_shape()
    test_first_person_introduced()
    test_accepted_when_clean()
    test_rejected_after_retries()
    test_restore_full_bold()
    test_verify_list_anchors_empty()
    test_verify_list_anchors_nonempty()
    test_verify_dict_anchors()
    test_classify_gate_crash()
    test_compose_note()
    test_parse_paragraph_selection()
    test_compress_ranges()
    test_readability_guard()
    print("test_match_voice: all assertions passed")


if __name__ == "__main__":
    main()
