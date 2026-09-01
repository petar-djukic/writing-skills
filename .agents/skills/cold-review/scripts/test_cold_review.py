#!/usr/bin/env python3
"""Offline tests for cold-review (GH-207): the planted number-swap yields
a revert list naming it; the applier restores baseline bytes and holds
the invariants; mismatched counts refuse."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import importlib
cr = importlib.import_module("cold_review")

BASELINE = """# Title

The seeded arm scored 0.768 and the pinned arm scored 0.867 on the pooled mean.

The critic said "the request was very dumb" and the gate let it stand.

A plain paragraph that both versions carry unchanged.
"""

# paragraph 1: the two arm numbers swapped; paragraph 2: quote reattributed
CANDIDATE = """# Title

The seeded arm scored 0.867 and the pinned arm scored 0.768 on the pooled mean.

The critic said "it was very dumb" and the gate let it stand.

A plain paragraph that both versions carry unchanged.
"""


def _write(tmp, name, content):
    p = os.path.join(tmp, name)
    open(p, "w", encoding="utf-8").write(content)
    return p


def test_screen_names_the_swap():
    with tempfile.TemporaryDirectory() as tmp:
        b = _write(tmp, "b.md", BASELINE)
        c = _write(tmp, "c.md", CANDIDATE)
        findings = cr.screen(b, c)
    by_para = {f["paragraph"]: f for f in findings}
    # The swap keeps the number MULTISET identical; the context-key check
    # is what names it (the 2026-09-01 0.768/0.867 case).
    assert 1 in by_para, findings
    assert any("reattached" in d and "0.768" in d
               for d in by_para[1]["drift"]), findings
    # And the altered quotation in paragraph 2 is caught by the quote check.
    assert 2 in by_para, findings
    assert any("quoted" in d for d in by_para[2]["drift"]), findings
    print("  screen_names_swap_and_quote: ok")


def test_screen_names_a_lost_number():
    with tempfile.TemporaryDirectory() as tmp:
        b = _write(tmp, "b.md", BASELINE)
        c = _write(tmp, "c.md", CANDIDATE.replace("0.867 and", "and"))
        findings = cr.screen(b, c)
    by_para = {f["paragraph"]: f for f in findings}
    assert 1 in by_para, findings
    assert any("numbers changed" in d and "0.867" in d
               for d in by_para[1]["drift"]), findings
    print("  screen_names_a_lost_number: ok")


def test_apply_reverts_verbatim():
    with tempfile.TemporaryDirectory() as tmp:
        b = _write(tmp, "b.md", BASELINE)
        c = _write(tmp, "c.md", CANDIDATE)
        out = os.path.join(tmp, "gated.md")
        problems = cr.apply_reverts(b, c, {1, 2}, out)
        assert problems == [], problems
        gated = open(out, encoding="utf-8").read()
    assert "0.768 and the pinned arm scored 0.867" in gated
    assert '"the request was very dumb"' in gated
    assert "A plain paragraph that both versions carry unchanged." in gated
    print("  apply_reverts_verbatim: ok")


def test_count_mismatch_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        b = _write(tmp, "b.md", BASELINE)
        c = _write(tmp, "c.md", CANDIDATE + "\nAn extra paragraph.\n")
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "cold_review.py"), "screen",
             "--baseline", b, "--candidate", c],
            capture_output=True, text=True)
    assert r.returncode != 0
    assert "counts differ" in r.stderr
    print("  count_mismatch_refuses: ok")


def test_locked_span_invariant():
    base = ("# T\n\nBefore.\n\n<!-- lock -->\nThe locked sentence stays "
            "byte-identical.\n<!-- /lock -->\n\nAfter paragraph here.\n")
    cand = base.replace("After paragraph here.", "After paragraph edited.")
    with tempfile.TemporaryDirectory() as tmp:
        b = _write(tmp, "b.md", base)
        c = _write(tmp, "c.md", cand)
        out = os.path.join(tmp, "gated.md")
        problems = cr.apply_reverts(b, c, {2}, out)
        gated = open(out, encoding="utf-8").read()
    assert problems == [], problems
    assert "After paragraph here." in gated
    assert "The locked sentence stays byte-identical." in gated
    print("  locked_span_invariant: ok")


if __name__ == "__main__":
    test_screen_names_the_swap()
    test_screen_names_a_lost_number()
    test_apply_reverts_verbatim()
    test_count_mismatch_refuses()
    test_locked_span_invariant()
    print("all cold-review tests passed")
