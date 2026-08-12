#!/usr/bin/env python3
"""Offline tests for the markup-preservation gate (GH-232).

The fixtures are the measured failure: a section built entirely out of bold
lead-ins, where three of six paragraphs came back as plain declarative prose
with every number and citation intact. verify.py exited clean on all three,
because inline emphasis was none of the things it checked.

No network, no model. Run: python3 <skill>/scripts/testdata/test_verify_markup.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import verify  # noqa: E402
import drive  # noqa: E402

# p29 from the measured run: accepted by the old gate, bold lead-in gone.
P29_ORIG = ("**The context stays clean.** An autonomous loop keeps its own "
            "context, so nothing you did earlier crowds the window.")
P29_LOST = ("The context stays clean. An autonomous loop keeps its own "
            "context, so nothing you did earlier crowds the window.")
P29_KEPT = ("**The context stays clean.** A loop of this kind carries its own "
            "context, so earlier work never crowds the window.")


def _checks(original, rewrite):
    """The set of check names that came back fatal."""
    r = verify.verify(original, rewrite)
    return {f["check"] for f in r["findings"] if f["severity"] == "fatal"}, r


def test_leading_bold_loss_is_fatal():
    fatal, r = _checks(P29_ORIG, P29_LOST)
    assert "markup" in fatal, r["findings"]
    assert not r["clean"]
    # The count rule and the leading rule both fire here; the operator should be
    # told the lead-in specifically, not only that a count moved.
    details = " ".join(f["detail"] for f in r["findings"] if f["check"] == "markup")
    assert "leading emphasis" in details, details


def test_leading_bold_kept_is_clean():
    fatal, r = _checks(P29_ORIG, P29_KEPT)
    assert not fatal, r["findings"]
    assert r["clean"]
    assert r["markup"]["original"]["bold"] == r["markup"]["rewrite"]["bold"] == 1


def test_plain_prose_unaffected():
    """The common case: no markup in, no markup rule fires."""
    o = "The driver scans the article before it touches a paragraph."
    w = "Before touching a paragraph, the driver scans the article."
    fatal, r = _checks(o, w)
    assert not fatal, r["findings"]
    assert r["markup"]["original"] == {"code": 0, "bold": 0, "italic": 0}


def test_inline_code_loss_is_fatal():
    o = "Pass `--pangram` and the driver captures a baseline first."
    w = "Pass --pangram and the driver captures a baseline first."
    fatal, r = _checks(o, w)
    assert "markup" in fatal, r["findings"]


def test_italic_loss_is_fatal():
    o = "The baseline is captured *before* the rewrite starts."
    w = "The baseline is captured before the rewrite starts."
    fatal, _ = _checks(o, w)
    assert "markup" in fatal


def test_added_emphasis_is_not_fatal():
    """A rewrite that adds emphasis is a style question, not a broken document."""
    o = "The baseline cannot be reconstructed afterwards."
    w = "The baseline **cannot** be reconstructed afterwards."
    fatal, r = _checks(o, w)
    assert not fatal, r["findings"]


def test_snake_case_is_not_italic():
    """Underscore italic must not fire on identifiers, or every code-adjacent
    paragraph reports emphasis it never had."""
    m = verify._markup_spans("The fields are fraction_ai and fraction_ai_assisted.")
    assert m["italic"] == 0, m


def test_asterisks_inside_code_are_not_bold():
    m = verify._markup_spans("Use `**kwargs` to forward them.")
    assert m["bold"] == 0 and m["code"] == 1, m


def test_bold_count_shortfall_is_fatal():
    """Three lead-ins in, two out: the article-wide 11 -> 8 drop in miniature."""
    o = "**One.** text **Two.** text **Three.** text"
    w = "**One.** text **Two.** text Three. text"
    fatal, r = _checks(o, w)
    assert "markup" in fatal
    assert r["markup"]["original"]["bold"] == 3
    assert r["markup"]["rewrite"]["bold"] == 2


def test_citations_and_numbers_still_pass_through():
    """The markup check is additive: it must not disturb the existing gate."""
    o = "Throughput rose 12% under [@djukic-2007-scheduling]."
    w = "Under [@djukic-2007-scheduling], throughput rose 12%."
    fatal, r = _checks(o, w)
    assert not fatal, r["findings"]


def test_restore_full_bold_repairs_whole_paragraph():
    """A wholly-bold original is repaired deterministically, so the gate sees
    the markup the draft will actually carry."""
    o = "**Everything here is emphasised.**"
    c = "All of this is emphasised."
    assert drive.restore_full_bold(o, c) == "**All of this is emphasised.**"
    fatal, _ = _checks(o, drive.restore_full_bold(o, c))
    assert not fatal


def test_restore_full_bold_leaves_leading_bold_alone():
    """The narrow repair must NOT touch a leading lead-in — where the lead-in
    landed in the rewrite is not knowable here, so that case is the gate's."""
    assert drive.restore_full_bold(P29_ORIG, P29_LOST) == P29_LOST


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_verify_markup: all assertions passed")


if __name__ == "__main__":
    main()
