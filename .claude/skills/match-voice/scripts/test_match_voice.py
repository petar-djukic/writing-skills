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


def main():
    test_returns_shape()
    test_accepted_when_clean()
    test_rejected_after_retries()
    test_restore_full_bold()
    print("test_match_voice: all assertions passed")


if __name__ == "__main__":
    main()
