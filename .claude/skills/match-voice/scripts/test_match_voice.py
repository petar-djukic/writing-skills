#!/usr/bin/env python3
"""Tests for match_voice_paragraph — mocked subprocess calls."""
import os
import sys
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _make_verify_module():
    """Stub verify module returning clean or dirty results."""
    mod = types.ModuleType("verify")
    mod._clean = True

    def verify(original, rewritten, anchors_json=None, max_shared_run=8):
        if mod._clean:
            return {"clean": True, "findings": []}
        return {"clean": False, "findings": [{"type": "numbers", "detail": "changed"}]}
    mod.verify = verify
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


def main():
    test_returns_shape()
    test_accepted_when_clean()
    test_rejected_after_retries()
    test_restore_full_bold()
    test_verify_list_anchors_empty()
    test_verify_list_anchors_nonempty()
    test_verify_dict_anchors()
    test_classify_gate_crash()
    print("test_match_voice: all assertions passed")


if __name__ == "__main__":
    main()
