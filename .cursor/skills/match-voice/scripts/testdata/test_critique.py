#!/usr/bin/env python3
"""Tests for the critique-repair harness (GH-77, sub-issue B).

Covers:
  - critique.mechanical: protected-term swap, banned word introduced,
    antithesis / tricolon counts rising, quoted span lost; nothing fires on
    a faithful candidate
  - parse_model: bare JSON, fenced JSON, prose-wrapped JSON, garbage -> None
  - merge: accept / repair / reject routing, mechanical-only repair, model
    term_swaps naming the replacement, unparsed -> accept with the flag
  - critique() with an injected generate stub (no network)
  - render_constraints: every finding becomes one explicit constraint
  - load_banned reads filter-tells' own list
  - summarize_passes: counts from synthetic results, pre-harness records
    count as pass 1; manifest carries the critique block and null without it

No network, no model.
Run: python3 <skill>/scripts/testdata/test_critique.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import critique as cq  # noqa: E402
import drive  # noqa: E402

ORIG = ('The exposure is what the detector measures. A veteran consultant might call it '
        '"plausible deniability" and move on; the decision plane does not.')
FAITHFUL = ('What the detector measures is the exposure. A veteran consultant might call it '
            '"plausible deniability" and move on; the decision plane does not.')
BROKEN = ('The justification is what the tool measures, not what it reports, but what it '
          'hides. A veteran consultant calls it plausible denial and moves on; the decision '
          'does not. It is fast, cheap, and salient.')
TERMS = ["exposure", "detector", "decision plane"]
BANNED = ["salient", "myriad", "at the heart of"]


def test_mechanical_fields():
    m = cq.mechanical(ORIG, BROKEN, TERMS, BANNED)
    assert [t["from"] for t in m["term_swaps"]] == ["exposure", "detector", "decision plane"], m
    assert m["banned_words"] == ["salient"]
    assert m["new_antithesis"] is True
    assert m["new_tricolon"] is True
    assert m["quoted_span_changes"] == ["plausible deniability"]
    clean = cq.mechanical(ORIG, FAITHFUL, TERMS, BANNED)
    assert not any(clean.values()), clean
    # a banned word the original already used is not the rewrite's doing
    m = cq.mechanical("A salient point.", "A salient remark.", [], BANNED)
    assert m["banned_words"] == []
    print("  mechanical_fields: ok")


def test_parse_model():
    obj = {"meaning_deltas": ["x"], "term_swaps": [], "register_drift": False, "verdict": "repair"}
    assert cq.parse_model(json.dumps(obj)) == obj
    assert cq.parse_model("```json\n" + json.dumps(obj) + "\n```") == obj
    assert cq.parse_model("Here is my verdict:\n" + json.dumps(obj) + "\nThanks.") == obj
    assert cq.parse_model("I think it is fine.") is None
    assert cq.parse_model("{not json") is None
    assert cq.parse_model("") is None and cq.parse_model(None) is None
    assert cq.parse_model("[1, 2]") is None
    print("  parse_model: ok")


def test_merge_routing():
    none = cq.mechanical(ORIG, FAITHFUL, TERMS, BANNED)
    hits = cq.mechanical(ORIG, BROKEN, TERMS, BANNED)
    ok = {"meaning_deltas": [], "term_swaps": [], "register_drift": False, "verdict": "accept"}
    assert cq.merge(none, ok)["verdict"] == "accept"
    assert cq.merge(hits, ok)["verdict"] == "repair", "mechanical finding alone is a repair"
    rep = dict(ok, verdict="repair", register_drift=True)
    out = cq.merge(none, rep)
    assert out["verdict"] == "repair" and out["register_drift"] is True
    assert "register_drift" in out["source"]["model"]
    rej = dict(ok, verdict="reject", meaning_deltas=["the consultant is made definite"])
    out = cq.merge(none, rej)
    assert out["verdict"] == "reject" and out["meaning_deltas"] == ["the consultant is made definite"]
    # a model that lists a delta but says accept is overruled to repair
    out = cq.merge(none, dict(ok, meaning_deltas=["hedge dropped"]))
    assert out["verdict"] == "repair"
    # the model names the replacement for a term the regex only saw lost
    out = cq.merge(hits, dict(ok, term_swaps=[{"from": "exposure", "to": "justification"},
                                              {"from": "refrain", "to": "chorus"}]))
    by = {t["from"]: t["to"] for t in out["term_swaps"]}
    assert by["exposure"] == "justification" and by["detector"] is None and by["refrain"] == "chorus"
    # unparsed: accept, flagged, nothing else changed
    out = cq.merge(none, None)
    assert out["verdict"] == "accept" and out["source"]["model"] == ["unparsed"]
    out = cq.merge(hits, None)
    assert out["verdict"] == "repair", "mechanical findings still repair when the model is silent"
    out = cq.merge(none, dict(ok, verdict="maybe"))
    assert out["verdict"] == "accept" and "unrecognized-verdict" in out["source"]["model"]
    print("  merge_routing: ok")


def test_critique_with_stub_generate():
    seen = {}

    def gen(prompt):
        seen["prompt"] = prompt
        return '{"meaning_deltas": ["hypothetical consultant made definite"], ' \
               '"term_swaps": [{"from": "exposure", "to": "justification"}], ' \
               '"register_drift": true, "verdict": "repair"}'
    out = cq.critique(ORIG, BROKEN, TERMS, BANNED, gen)
    assert out["verdict"] == "repair"
    assert "ORIGINAL:" in seen["prompt"] and BROKEN in seen["prompt"]
    assert "exposure; detector; decision plane" in seen["prompt"], "own terms listed"
    assert out["raw"].startswith("{")
    assert out["source"]["mechanical"] and out["source"]["model"]
    # no generate: mechanical only, reported as skipped
    out = cq.critique(ORIG, FAITHFUL, TERMS, BANNED, None)
    assert out["verdict"] == "accept" and out["source"]["model"] == ["skipped"]
    # garbage from the model never rejects
    out = cq.critique(ORIG, FAITHFUL, TERMS, BANNED, lambda p: "Looks good to me!")
    assert out["verdict"] == "accept" and out["source"]["model"] == ["unparsed"]

    # a critic that raises is logged, not fatal, and the candidate proceeds
    def down(prompt):
        raise RuntimeError("Ollama timed out after 300s")
    out = cq.critique(ORIG, BROKEN, TERMS, BANNED, down)
    assert out["verdict"] == "repair", "mechanical findings still count"
    assert out["error"].startswith("Ollama timed out") and out["source"]["model"] == ["unparsed"]
    print("  critique_with_stub_generate: ok")


def test_render_constraints():
    crit = cq.merge(cq.mechanical(ORIG, BROKEN, TERMS, BANNED), {
        "meaning_deltas": ["the consultant is made definite"],
        "term_swaps": [{"from": "exposure", "to": "justification"}],
        "register_drift": True, "verdict": "repair"})
    text = cq.render_constraints(crit)
    for needle in ("Keep the word 'exposure'; do not replace it with 'justification'.",
                   "Keep the word 'detector' exactly as the original uses it.",
                   "Meaning changed: the consultant is made definite",
                   "do not smooth it into generic prose",
                   "Do not use the word 'salient'",
                   "Do not stage a contrast",
                   "Do not add a three-item list",
                   'must survive verbatim: "plausible deniability".'):
        assert needle in text, f"missing: {needle}\n{text}"
    assert cq.render_constraints({"verdict": "accept"}) == ""
    print("  render_constraints: ok")


def test_load_banned_reads_filter_tells():
    words = cq.load_banned()
    assert "myriad" in words and "salient" in words, words[:10]
    assert "at the heart of" in words, "AI_PHRASES included"
    assert not any(w.startswith("#") for w in words), "comments stripped"
    assert cq.load_banned("/nonexistent/detect-lexical.sh") == []
    print("  load_banned_reads_filter_tells: ok")


def test_summarize_passes_and_manifest():
    results = [
        {"n": 1, "status": "accepted-mechanical", "pass": 1,
         "critique": {"verdict": "accept", "source": {"model": []}}},
        {"n": 2, "status": "accepted-mechanical", "pass": 2,
         "critique": {"verdict": "repair", "source": {"model": ["meaning_deltas"]}}},
        {"n": 3, "status": "rejected-critique", "pass": 1,
         "critique": {"verdict": "reject", "source": {"model": ["meaning_deltas"]}}},
        {"n": 4, "status": "kept-original", "pass": 2,
         "critique": {"verdict": "repair", "source": {"model": ["unparsed"]}}},
        {"n": 5, "status": "accepted-mechanical"},        # pre-harness / --no-critique
        {"n": 6, "status": "skipped-short"},
    ]
    s = cq.summarize_passes(results)
    assert s == {"pass1_accepted": 2, "pass2_accepted": 1, "repaired": 2,
                 "rejected_critique": 1, "critique_unparsed": 1, "critiqued": 4}, s

    class Args:
        model = "m"; no_anchors = True; role = None; anchor_tags = ""; stratum = None
        style_note = ""; paragraphs = ""; author = None
    a = Args()
    a._critique = dict(s, model="critic-x")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "m.yaml")
        drive.write_manifest(path, a, None, results)
        text = open(path).read()
        assert "  critique:\n    model: critic-x\n    pass1_accepted: 2\n    pass2_accepted: 1\n" in text, text
        assert "rejected_critique: 1" in text and "critique_unparsed: 1" in text
        b = Args()
        drive.write_manifest(path, b, None, results)
        assert "critique: null" in open(path).read()
    print("  summarize_passes_and_manifest: ok")


def main():
    test_mechanical_fields()
    test_parse_model()
    test_merge_routing()
    test_critique_with_stub_generate()
    test_render_constraints()
    test_load_banned_reads_filter_tells()
    test_summarize_passes_and_manifest()
    print("test_critique: all assertions passed")


if __name__ == "__main__":
    main()
