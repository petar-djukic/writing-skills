#!/usr/bin/env python3
"""Offline tests for pangram_report.py. Run: python3 <surface>/scripts/test_pangram_report.py

No network, no API key. Responses are synthesised against the real span offsets
of pangram_sample.md, so the window->paragraph mapping is exercised on genuine
character positions rather than hand-picked numbers.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pangram_report as pr  # noqa: E402

SAMPLE = os.path.join(HERE, "testdata_pangram_sample.md")


def response(spans, scores, fracs=(0.7, 0.2, 0.1), verdict="Mixed",
             segs=(2, 1, 1)):
    """Build a response whose windows sit exactly on the given paragraphs."""
    windows = []
    for i, sc in scores.items():
        s = spans[i]
        windows.append({
            "text": s["preview"], "label": "AI-Generated" if sc >= 0.5 else "Human",
            "ai_assistance_score": sc,
            "confidence": "High" if sc >= 0.5 else "Low",
            "start_index": s["start"], "end_index": s["end"],
        })
    return {
        "stage": "STAGE_SUCCESS", "prediction_short": verdict,
        "fraction_ai": fracs[0], "fraction_ai_assisted": fracs[1],
        "fraction_human": fracs[2],
        "num_ai_segments": segs[0], "num_ai_assisted_segments": segs[1],
        "num_human_segments": segs[2],
        "windows": windows,
    }


def main():
    text, spans = pr.build_payload(SAMPLE)

    # 1. Prose only. The extractor's job, asserted here because a code fence
    #    reaching a prose detector both skews the result and costs money.
    assert "def schedule" not in text, "code fence leaked into the payload"
    assert "| Run |" not in text, "table leaked into the payload"
    assert "- a list item" not in text, "list leaked into the payload"
    assert "title: Sample draft" not in text, "front matter leaked into the payload"
    assert len(spans) == 3, f"expected 3 prose paragraphs, got {len(spans)}"

    # 2. Spans index the submitted text exactly — this is what window offsets
    #    are relative to, so an off-by-one here silently misattributes findings.
    for s in spans:
        assert text[s["start"]:s["end"]].startswith(s["preview"][:30]), \
            f"span {s['index']} does not index its own text"
    assert spans[1]["line_start"] > spans[0]["line_end"], "line ranges out of order"

    # 3. A window maps to the paragraph it overlaps, and carries its line number.
    resp = response(spans, {1: 0.85})
    paras = pr.map_windows(resp, spans)
    assert paras[1]["flagged"] and not paras[0]["flagged"] and not paras[2]["flagged"]
    assert paras[1]["line_start"] == spans[1]["line_start"]
    assert paras[1]["score"] == 0.85 and paras[1]["confidence"] == "High"

    # 4. Overlapping windows keep the MAX, not the mean: averaging a strong
    #    local signal against quiet neighbours hides the passage worth fixing.
    s = spans[0]
    multi = {"stage": "STAGE_SUCCESS", "fraction_ai": 0.5, "windows": [
        {"ai_assistance_score": 0.9, "confidence": "High",
         "start_index": s["start"], "end_index": s["start"] + 10},
        {"ai_assistance_score": 0.1, "confidence": "Low",
         "start_index": s["start"] + 5, "end_index": s["end"]},
    ]}
    m = pr.map_windows(multi, spans)[0]
    assert m["score"] == 0.9, f"expected max 0.9, got {m['score']} (mean would be 0.5)"
    assert m["confidence"] == "High" and m["windows"] == 2

    # 5. Percentages, not raw fractions.
    assert pr.fractions(resp)["ai"] == 70.0, "0.70 must render as 70.0"

    # 6. A real improvement is reported as such.
    before = response(spans, {1: 0.85}, fracs=(0.70, 0.20, 0.10))
    after = response(spans, {1: 0.20}, fracs=(0.15, 0.10, 0.75), verdict="Human")
    d = pr.diff(after, before, pr.map_windows(after, spans),
                pr.map_windows(before, spans))
    assert d["delta"]["ai"] == -55.0, f"expected -55.0pt, got {d['delta']['ai']}"
    assert d["paragraphs"][1]["state"] == "improved"
    assert not d["paragraphs"][1]["flagged"]
    assert d["note"] is None

    # 7. A rewrite that made things worse is not reported as progress.
    worse = response(spans, {1: 0.95}, fracs=(0.90, 0.05, 0.05), verdict="AI")
    d2 = pr.diff(worse, before, pr.map_windows(worse, spans),
                 pr.map_windows(before, spans))
    assert d2["delta"]["ai"] == 20.0 and d2["paragraphs"][1]["state"] == "regressed"

    # 8. Differing paragraph counts: totals still valid, per-paragraph refused.
    #    A confidently wrong attribution is worse than an honest gap.
    d3 = pr.diff(after, before, pr.map_windows(after, spans)[:2],
                 pr.map_windows(before, spans))
    assert d3["paragraphs"] is None, "must not match paragraphs across differing counts"
    assert "skipped" in d3["note"] and "3" in d3["note"] and "2" in d3["note"]
    assert d3["delta"]["ai"] == -55.0, "document-level movement stays valid"

    # 9. Noise below the tolerance is 'unchanged', not a spurious win.
    near = response(spans, {1: 0.83}, fracs=(0.70, 0.20, 0.10))
    d4 = pr.diff(near, before, pr.map_windows(near, spans),
                 pr.map_windows(before, spans))
    assert d4["paragraphs"][1]["state"] == "unchanged"

    # 10. A response with no windows degrades rather than crashing.
    empty = {"stage": "STAGE_SUCCESS", "fraction_ai": 0.0, "windows": []}
    assert all(p["score"] is None for p in pr.map_windows(empty, spans))

    # 11. fractions() includes segment counts, mean_window_score, num_windows.
    f = pr.fractions(resp)
    assert f["num_ai"] == 2 and f["num_ai_assisted"] == 1 and f["num_human"] == 1
    assert f["num_windows"] == 1
    assert f["mean_window_score"] == 0.85

    # 12. diff() deltas segment counts and mean_window_score.
    before12 = response(spans, {1: 0.85}, fracs=(0.70, 0.20, 0.10), segs=(3, 1, 0))
    after12 = response(spans, {1: 0.20}, fracs=(0.15, 0.10, 0.75),
                        verdict="Human", segs=(0, 1, 3))
    d12 = pr.diff(after12, before12, pr.map_windows(after12, spans),
                  pr.map_windows(before12, spans))
    assert d12["delta"]["num_ai"] == -3
    assert d12["delta"]["num_ai_assisted"] == 0
    assert d12["delta"]["num_human"] == 3
    assert d12["delta"]["mean_window_score"] == round(0.20 - 0.85, 4)

    # 13. mean_window_score is None when a response has no windows.
    f_empty = pr.fractions(empty)
    assert f_empty["mean_window_score"] is None
    assert f_empty["num_windows"] == 0
    assert f_empty["num_ai"] == 0

    print("test_pangram_report: all assertions passed (no network, no key)")


if __name__ == "__main__":
    main()
