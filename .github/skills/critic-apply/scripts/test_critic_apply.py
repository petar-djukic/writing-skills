#!/usr/bin/env python3
"""Offline tests for critic-apply (GH-206): convergent-applied,
split-skipped, constitution-declined, remedy-conflict-omission, marker
round-trip, gate rejection, cross-instrument deletion. No model calls —
generate is a stub."""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import importlib
ca = importlib.import_module("critic_apply")

ARTICLE = """# Title

<!-- rst: nucleus | the thesis --> The system costs 42 dollars per run and the price is stated once [3]. The follow-up sentence restates what the price already showed.

The second paragraph stands alone and says one plain thing.

Trying to size a business that does not exist reveals nothing about whether it will ever exist.

The bridge sentence carries the constitution and must never change.
"""


def sheet(convergent_blocks="", single_blocks=""):
    return (f"# Critic panel sheet\n\n## Diagnoses\n\nx\n\n"
            f"## Convergent (n)\n\n{convergent_blocks}\n"
            f"## Single-critic suggestions\n\n{single_blocks}\n")


def conv(quote, entries):
    lines = [f'### "{quote}"', ""]
    for c, b, w in entries:
        lines.append(f"- **{c}:** {b} — *{w}*")
    return "\n".join(lines) + "\n\n"


def test_convergent_applied_and_marker_roundtrip():
    q = ("The follow-up sentence restates what the price already showed.")
    sh = sheet(conv(q, [("levine", "Cut the restatement to one clause.",
                         "the fact earns the laugh alone"),
                        ("didion", "Tighten it.", "restatement spends it")]))
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        # a valid candidate: numbers and citation intact, shorter
        return ("The system costs 42 dollars per run and the price is "
                "stated once [3]. The restatement goes.")

    new, recs = ca.decide_and_apply(
        ARTICLE, ca.parse_sheet(sh), generate=fake_generate)
    assert recs[0]["status"] == "applied-rewrite", recs
    # marker round-trip: never in the prompt, still in the output
    assert "rst:" not in prompts[0], prompts[0]
    assert "<!-- rst: nucleus" in new
    assert "The restatement goes." in new
    print("  convergent_applied + marker_roundtrip: ok")


def test_split_panel_skipped():
    q = "The second paragraph stands alone and says one plain thing."
    sh = sheet(conv(q, [("levine", "CUT", "does nothing"),
                        ("hemingway", "KEEP — it earns its place",
                         "the plainness is the point")]))
    called = []
    new, recs = ca.decide_and_apply(
        ARTICLE, ca.parse_sheet(sh),
        generate=lambda p: called.append(p) or "x")
    assert recs[0]["status"] == "skipped-split-panel", recs
    assert not called
    assert q in new
    print("  split_panel_skipped: ok")


def test_constitution_declined():
    q = "The bridge sentence carries the constitution and must never change."
    sh = sheet(conv(q, [("levine", "CUT", "flat"),
                        ("didion", "CUT", "flat")]))
    new, recs = ca.decide_and_apply(
        ARTICLE, ca.parse_sheet(sh),
        protected=["The bridge sentence carries the constitution"])
    assert recs[0]["status"] == "declined-constitution", recs
    assert "cause" in recs[0]
    assert q in new
    print("  constitution_declined: ok")


def test_remedy_conflict_prefers_omission():
    q = ("Trying to size a business that does not exist reveals nothing "
         "about whether it will ever exist.")
    sh = sheet(conv(q, [("didion", "CUT", "circles its own terms"),
                        ("levine", "Sizing a phantom proves nothing.",
                         "shorter")]))
    called = []
    new, recs = ca.decide_and_apply(
        ARTICLE, ca.parse_sheet(sh),
        generate=lambda p: called.append(p) or "x")
    assert recs[0]["status"] == "applied-deletion", recs
    assert not called, "deletion must author no prose and call no model"
    assert q not in new
    print("  remedy_conflict_prefers_omission: ok")


def test_gate_rejection():
    q = ("The follow-up sentence restates what the price already showed.")
    sh = sheet(conv(q, [("levine", "Trim.", "trim"),
                        ("didion", "Trim.", "trim")]))
    # candidate drops the number and the citation -> gate keeps original
    new, recs = ca.decide_and_apply(
        ARTICLE, ca.parse_sheet(sh),
        generate=lambda p: "The price is stated once and that is that.")
    assert recs[0]["status"] == "kept-gate", recs
    assert "number multiset" in recs[0]["cause"]
    assert q in new
    print("  gate_rejection: ok")


def test_cross_instrument_deletion():
    q = "The second paragraph stands alone and says one plain thing."
    single = '### levine\n\n1. "%s" → CUT — *adds nothing*\n' % q
    targets = ca.parse_sheet(sheet(single_blocks=single))
    # not convergent, no cheap rank -> skipped
    new, recs = ca.decide_and_apply(ARTICLE, targets)
    assert recs[0]["status"] == "skipped-not-convergent", recs
    # ranked cheap by reverse-outline -> accepted as a deletion
    new, recs = ca.decide_and_apply(ARTICLE, targets, cheap={2})
    assert recs[0]["status"] == "applied-deletion", recs
    assert recs[0]["cross_instrument"] == "reverse-outline-cheap"
    assert q not in new
    print("  cross_instrument_deletion: ok")


def test_counts():
    q = ("Trying to size a business that does not exist reveals nothing "
         "about whether it will ever exist.")
    sh = sheet(conv(q, [("a", "CUT", "x"), ("b", "CUT", "y")]))
    _new, recs = ca.decide_and_apply(ARTICLE, ca.parse_sheet(sh))
    c = ca.counts(recs)
    assert c["applied"] == 1 and c["kept"] == 0 and c["declined_by_rule"] == 0
    print("  counts: ok")


if __name__ == "__main__":
    test_convergent_applied_and_marker_roundtrip()
    test_split_panel_skipped()
    test_constitution_declined()
    test_remedy_conflict_prefers_omission()
    test_gate_rejection()
    test_cross_instrument_deletion()
    test_counts()
    print("all critic-apply tests passed")
