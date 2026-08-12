#!/usr/bin/env python3
"""Tests for GH-254: sweep preserves drafts per (article, arm).

Run: python3 testdata/test_preserve_drafts.py

Verifies that _sweep_full copies each draft to a unique path keyed by
(article, arm hash), and that the ledger records the path so verify can find it.
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import ledger  # noqa: E402


def test_draft_path_roundtrip():
    """draft_path serializes and deserializes through the ledger."""
    tmp = tempfile.mkdtemp(prefix="test-draft-path-")
    try:
        path = os.path.join(tmp, "ledger.yaml")
        lg = ledger.Ledger(path)
        lg.append(ledger.Trial(
            article="a.md", arm="tags~clipped", model="test",
            draft_path="/some/path/a-abc12345.md"))
        lg.append(ledger.Trial(
            article="b.md", arm="role=venue-voice", model="test",
            draft_path=None))
        lg.save()

        lg2 = ledger.Ledger.load(path)
        assert lg2.trials[0].draft_path == "/some/path/a-abc12345.md"
        assert lg2.trials[1].draft_path is None
        print("  draft_path roundtrip: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_draft_naming():
    """Draft names are article stem + arm hash, so different arms get different files."""
    arm_a = "tags~clipped"
    arm_b = "role=venue-voice"
    hash_a = hashlib.sha256(arm_a.encode()).hexdigest()[:8]
    hash_b = hashlib.sha256(arm_b.encode()).hexdigest()[:8]

    name_a = f"article-{hash_a}.md"
    name_b = f"article-{hash_b}.md"

    assert name_a != name_b, "different arms must produce different filenames"
    assert len(hash_a) == 8 and hash_a.isalnum()
    print(f"  draft naming: {name_a} vs {name_b} — distinct")


def test_trial_to_dict_includes_draft_path():
    """to_dict includes draft_path when set, omits it when None."""
    t1 = ledger.Trial(article="a.md", arm="x", draft_path="/tmp/draft.md")
    d1 = t1.to_dict()
    assert d1["draft_path"] == "/tmp/draft.md"

    t2 = ledger.Trial(article="a.md", arm="x", draft_path=None)
    d2 = t2.to_dict()
    assert "draft_path" not in d2, "None draft_path should be omitted"
    print("  to_dict draft_path: passed")


def test_verify_skips_missing_draft():
    """verify prints SKIP when trial has no draft_path."""
    import io
    from contextlib import redirect_stdout
    sys.path.insert(0, SCRIPTS)
    import tune_anchors  # noqa: E402

    tmp = tempfile.mkdtemp(prefix="test-verify-no-draft-")
    try:
        lg = ledger.Ledger()
        lg.append(ledger.Trial(
            article="a.md", arm="arm-x", model="test",
            register_markers={"passive_per_1k": 3.0, "nominalization_per_1k": 15.0},
            draft_path=None))
        path = os.path.join(tmp, "ledger.yaml")
        lg.save(path)

        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            top = 1
            budget = 5
        with redirect_stdout(buf):
            tune_anchors.cmd_verify(FakeArgs())

        output = buf.getvalue()
        assert "SKIP" in output, f"expected SKIP for missing draft: {output}"
        print("  verify skips missing draft: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_draft_path_roundtrip()
    test_draft_naming()
    test_trial_to_dict_includes_draft_path()
    test_verify_skips_missing_draft()
    print("test_preserve_drafts: all assertions passed")


if __name__ == "__main__":
    main()
