#!/usr/bin/env python3
"""A rewrite that damages citation markers is refused at the splice (GH-159).

The trigger case is real: rewriting a paragraph carrying [@park2024], the
model emitted [@key] — the example from the prompt's own rule. Identity, not
shape, is what the gate checks.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import drive  # noqa: E402


def test_swapped_key_is_damage():
    assert drive._citation_damage(
        "Park et al. showed the distortion [@park2024].",
        "Park et al. showed the distortion [@key].") \
        == "citation markers damaged: lost [@park2024]; invented [@key]"
    print("  swapped_key_is_damage: ok")


def test_preserved_markers_pass():
    for o, r in [
            ("Stability fell [2].", "Stability dropped [2]."),
            ("Shown in [@a2020] and \\citep{b2021}.",
             "As \\citep{b2021} and [@a2020] both show."),  # order-free
            ("No citations here.", "Still none here.")]:
        assert drive._citation_damage(o, r) is None, (o, r)
    print("  preserved_markers_pass: ok")


def test_dropped_and_duplicated_are_damage():
    assert "lost [2]" in drive._citation_damage("Fell [2].", "Fell.")
    assert "invented [2]" in drive._citation_damage("Fell [2].", "Fell [2] [2].")
    print("  dropped_and_duplicated_are_damage: ok")


ARTICLE = ("Park et al. demonstrated the distortion effect and proposed "
           "corrections [@park2024], and the mitigation is a simpler grammar "
           "requiring less masking in the first place overall.\n\n"
           "A second paragraph with enough plain words to be its own target "
           "for the rewrite loop, carrying the marker-two token for the test.")


def test_damaging_rewrite_is_refused_at_the_splice():
    def swapping(text, issues, endpoint, model, timeout):
        if "[@park2024]" in text:
            return text.replace("[@park2024]", "[@key]")
        return text.replace("marker-two", "REWRITTEN-two")

    scan = {"lexical": {"issue_count": 2, "issues": []},
            "structural": {"issue_count": 0, "issues": []},
            "verdict": "likely-ai", "needs_step3": True}
    orig = (drive.rewrite_passage, drive.run_lexical, drive.run_structural)
    drive.rewrite_passage = swapping
    drive.run_lexical = lambda path: {"issue_count": 2, "issues": []}
    drive.run_structural = lambda path, vp=None: {"issue_count": 0, "issues": []}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            art = os.path.join(tmp, "a.md")
            with open(art, "w") as f:
                f.write(ARTICLE)
            result = drive.run_rewrite(art, scan, None, "http://unused",
                                       "test-model", 5, max_passes=1)
            draft = open(result["draft_path"]).read()
    finally:
        drive.rewrite_passage, drive.run_lexical, drive.run_structural = orig

    assert "[@park2024]" in draft, "original citation must survive"
    assert "[@key]" not in draft, "the swapped key must never be spliced"
    assert "REWRITTEN-two" in draft, "the clean rewrite still lands"
    p1 = result["passes"][-1]
    errs = [e for e in p1.get("errors", []) if e["cause"] == "citation-damage"]
    assert len(errs) == 1 and "[@key]" in errs[0]["error"], p1
    print("  damaging_rewrite_is_refused_at_the_splice: ok")



def test_structural_issues_scoped_to_their_paragraph():
    """GH-171: an issue quoting another paragraph's prose must not reach this
    paragraph's rewrite prompt — models spliced the quoted sentence in."""
    scan = {"lexical": {"issues": [
                {"line": 5, "category": "banned-word", "text": "in this one"},
                {"line": 90, "category": "banned-word", "text": "elsewhere"}]},
            "structural": {"issues": [
                {"type": "antithesis-fragment", "position": "sentence pair 4-5",
                 "detail": 'Pair: "Consider two runners chasing the same bus."'},
                {"type": "antithesis-fragment", "position": "sentence pair 90-91",
                 "detail": 'Pair: "A sentence living in a distant paragraph."'},
                {"type": "dash-heavy",
                 "detail": "3.9 per 500w across the document"}]}}
    passage = "Consider two runners chasing the same bus. Only one of them makes it."
    out = drive._issues_for_lines(scan, 1, 10, passage)
    assert "two runners" in out, out
    assert "distant paragraph" not in out, "other paragraph's quote leaked in"
    assert "dash-heavy" in out, "quote-less document-level issue must survive"
    assert "L5" in out and "L90" not in out
    print("  structural_issues_scoped_to_their_paragraph: ok")



def test_extractors_strip_cohere_bold_residue():
    """GH-180: Cohere bolds field labels; values must come out clean."""
    assert drive._extract_field("**AI_PROBABILITY:** 95%", "AI_PROBABILITY") == "95%"
    assert drive._extract_field("CONFIDENCE: ** High", "CONFIDENCE") == "High"
    pri = drive._extract_priority(
        "REWRITE_PRIORITY:\n**\n1. **Lines 10-12:** fix the antithesis\n"
        "2. Lines 30-31: drop the tricolon")
    assert pri == ["Lines 10-12:** fix the antithesis",
                   "Lines 30-31: drop the tricolon"] or all(
        "Lines" in x for x in pri), pri
    assert "**" not in "".join(p[:2] for p in pri)
    print("  extractors_strip_cohere_bold_residue: ok")

def main():
    test_extractors_strip_cohere_bold_residue()
    test_structural_issues_scoped_to_their_paragraph()
    test_swapped_key_is_damage()
    test_preserved_markers_pass()
    test_dropped_and_duplicated_are_damage()
    test_damaging_rewrite_is_refused_at_the_splice()
    print("test_citation_gate: all assertions passed")


if __name__ == "__main__":
    main()
