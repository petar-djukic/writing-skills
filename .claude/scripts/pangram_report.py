#!/usr/bin/env python3
"""Turn a Pangram response into a worklist, and diff a rewrite against its baseline.

A document-level "70% AI" tells you nothing you can act on. This maps the
overlapping per-window scores back to paragraphs and source line numbers, so the
output is a list of passages to rewrite rather than a grade.

Two subcommands:

  payload   Build the exact text to submit, from the shared markdown extractor.
            Prose only — code fences, tables, and front matter are neither
            written by a person in the sense a prose detector measures nor free
            to send, since billing counts started 1,000-word blocks. Writes a
            sidecar .spans.json recording each paragraph's character span in the
            submitted string; without it the response cannot be mapped back.

  report    Map a response onto those spans. With --baseline, diff against an
            earlier response and report what moved.

Typical flow (the baseline must be captured BEFORE the rewrite — there is no
way to reconstruct it afterwards):

  pangram_report.py payload --article draft.md --out draft.payload.txt
  pangram.py --text draft.payload.txt --json > before.json
  # ... rewrite ...
  pangram_report.py payload --article draft.md --out draft.payload.txt
  pangram.py --text draft.payload.txt --json > after.json
  pangram_report.py report --response after.json --spans draft.payload.spans.json \\
                           --baseline before.json

A full comparison costs two scans. Nothing here enforces a quota: pangram.py
--check spends nothing, and the API answers 402 for exhausted credits and 429
for too many requests. Those answers are the source of truth, not a remembered
daily figure.

Stdlib only. Consumes pangram.py --json output; never calls the API itself, so
this half is testable with no key and no credits.
"""

import argparse
import json
import os
import sys

SK = os.path.dirname(os.path.abspath(__file__))

# Windows carrying at least this score are worth a rewrite pass. Uncalibrated:
# the docs publish no thresholds, no accuracy figures, and no false-positive
# rate, so this is a starting point for triage, not a finding.
FLAG_SCORE = 0.5


def _md_paragraphs():
    shared = SK                      # a sibling at the shared root since GH-212
    if shared not in sys.path:
        sys.path.insert(0, shared)
    try:
        import md_paragraphs
        return md_paragraphs
    except ImportError as e:
        sys.exit(f"could not import md_paragraphs.py from {shared}: {e}")


def build_payload(path, min_words=0, sep="\n\n"):
    """Assemble prose-only submission text plus the span map.

    Returns (text, spans) where spans entries are
    {index, start, end, line_start, line_end, words, preview}.
    `start`/`end` are character offsets into the returned text, which is what
    Pangram's window offsets index into.
    """
    r = _md_paragraphs().parse_file(path)
    spans, chunks, pos = [], [], 0
    for i, (ls, le, txt) in enumerate(r.paragraphs):
        if len(txt.split()) < min_words:
            continue
        flat = " ".join(txt.split())
        if chunks:
            pos += len(sep)
        spans.append({
            "index": len(spans),
            "start": pos,
            "end": pos + len(flat),
            "line_start": ls,
            "line_end": le,
            "words": len(flat.split()),
            "preview": flat[:70],
        })
        chunks.append(flat)
        pos += len(flat)
    return sep.join(chunks), spans


def map_windows(response, spans):
    """Attach each window to every paragraph span it overlaps.

    Windows overlap by design, so a paragraph can collect several. We keep the
    maximum score rather than the mean: averaging a strong local signal against
    its quieter neighbours dilutes exactly the passage worth looking at.
    """
    out = []
    for s in spans:
        hits = []
        for w in response.get("windows") or []:
            ws, we = w.get("start_index"), w.get("end_index")
            if ws is None or we is None:
                continue
            if ws < s["end"] and we > s["start"]:      # half-open overlap
                hits.append(w)
        rank = {"High": 3, "Medium": 2, "Low": 1}
        best = max(hits, key=lambda w: w.get("ai_assistance_score") or 0.0) if hits else None
        conf = max((h.get("confidence") for h in hits),
                   key=lambda c: rank.get(c, 0), default=None)
        out.append({
            **s,
            "windows": len(hits),
            "score": (best or {}).get("ai_assistance_score"),
            "label": (best or {}).get("label"),
            "confidence": conf,
            "flagged": bool(best and (best.get("ai_assistance_score") or 0) >= FLAG_SCORE),
        })
    return out


def _pct(f):
    return None if f is None else round(float(f) * 100, 1)


def _mean_window_score(response):
    windows = response.get("windows") or []
    scores = [w["ai_assistance_score"] for w in windows
              if w.get("ai_assistance_score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def fractions(response):
    return {
        "ai": _pct(response.get("fraction_ai")),
        "ai_assisted": _pct(response.get("fraction_ai_assisted")),
        "human": _pct(response.get("fraction_human")),
        "num_ai": response.get("num_ai_segments", 0),
        "num_ai_assisted": response.get("num_ai_assisted_segments", 0),
        "num_human": response.get("num_human_segments", 0),
        "mean_window_score": _mean_window_score(response),
        "num_windows": len(response.get("windows") or []),
        "verdict": response.get("prediction_short") or None,
    }


def diff(current, baseline, cur_paras, base_paras):
    """Compare two responses. Per-paragraph only when the counts agree.

    A rewrite changes the text and therefore the offsets, so paragraph N in the
    baseline is not necessarily paragraph N now. When the counts differ we
    report totals and say plainly that per-paragraph matching was skipped: a
    confidently wrong paragraph attribution is worse than an honest gap.
    """
    c, b = fractions(current), fractions(baseline)
    delta = {k: (None if c[k] is None or b[k] is None else round(c[k] - b[k], 1))
             for k in ("ai", "ai_assisted", "human")}
    for k in ("num_ai", "num_ai_assisted", "num_human"):
        delta[k] = c[k] - b[k]
    if c["mean_window_score"] is not None and b["mean_window_score"] is not None:
        delta["mean_window_score"] = round(c["mean_window_score"] - b["mean_window_score"], 4)
    else:
        delta["mean_window_score"] = None
    out = {"baseline": b, "current": c, "delta": delta, "paragraphs": None,
           "note": None}

    if len(cur_paras) != len(base_paras):
        out["note"] = (
            f"per-paragraph matching skipped: {len(base_paras)} paragraphs in "
            f"the baseline, {len(cur_paras)} now. Document-level movement above "
            f"is still valid.")
        return out

    rows = []
    for cur, base in zip(cur_paras, base_paras):
        cs, bs = cur.get("score"), base.get("score")
        if cs is None and bs is None:
            state = "unflagged"
        elif bs is None:
            state = "regressed"
        elif cs is None:
            state = "improved"
        elif cs < bs - 0.05:
            state = "improved"
        elif cs > bs + 0.05:
            state = "regressed"
        else:
            state = "unchanged"
        rows.append({
            "index": cur["index"], "line_start": cur["line_start"],
            "was": bs, "now": cs, "state": state,
            "flagged": cur["flagged"], "preview": cur["preview"],
        })
    out["paragraphs"] = rows
    return out


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cmd_payload(a):
    text, spans = build_payload(a.article, min_words=a.min_words)
    if not spans:
        sys.exit(f"no prose paragraphs found in {a.article} — nothing to submit")
    out = a.out or (os.path.splitext(a.article)[0] + ".payload.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    sidecar = os.path.splitext(out)[0] + ".spans.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"article": os.path.abspath(a.article), "spans": spans}, f, indent=2)
    words = sum(s["words"] for s in spans)
    units = max(1, -(-words // 1000))     # billing: started 1,000-word blocks, min 1
    print(f"payload: {out}  ({len(spans)} paragraphs, {words} words)")
    print(f"spans:   {sidecar}")
    print(f"cost:    ~{units} billable unit{'s' if units != 1 else ''} per scan")


def cmd_report(a):
    resp = _load(a.response)
    spans = _load(a.spans)["spans"]
    paras = map_windows(resp, spans)

    if a.baseline:
        base_resp = _load(a.baseline)
        base_spans = _load(a.baseline_spans)["spans"] if a.baseline_spans else spans
        d = diff(resp, base_resp, paras, map_windows(base_resp, base_spans))
        if a.json:
            print(json.dumps(d, indent=2))
            return 0
        b, c, dl = d["baseline"], d["current"], d["delta"]
        arrow = lambda v: "--" if v is None else f"{v:+.1f}pt"
        darrow = lambda v: "--" if v is None else f"{v:+.4f}"
        segs = lambda f: f"{f['num_ai']}ai/{f['num_ai_assisted']}aa/{f['num_human']}h"
        mws = lambda f: "--" if f["mean_window_score"] is None else f"{f['mean_window_score']:.4f}"
        print(f"verdict:      {b['verdict']} -> {c['verdict']}")
        print(f"AI:           {b['ai']}% -> {c['ai']}%   ({arrow(dl['ai'])})")
        print(f"AI-assisted:  {b['ai_assisted']}% -> {c['ai_assisted']}%   ({arrow(dl['ai_assisted'])})")
        print(f"human:        {b['human']}% -> {c['human']}%   ({arrow(dl['human'])})")
        print(f"segments:     {segs(b)} -> {segs(c)}")
        print(f"mean_window:  {mws(b)} -> {mws(c)}   ({darrow(dl['mean_window_score'])})")
        if d["note"]:
            print(f"\n{d['note']}")
        else:
            for r in d["paragraphs"]:
                if r["state"] in ("improved", "regressed") or r["flagged"]:
                    w = "--" if r["was"] is None else f"{r['was']:.2f}"
                    n = "--" if r["now"] is None else f"{r['now']:.2f}"
                    print(f"  L{r['line_start']:>4} {r['state']:10} {w} -> {n}  "
                          f"{r['preview'][:50]}")
        still = [r for r in (d["paragraphs"] or []) if r["flagged"]]
        if still:
            print(f"\nstill flagged ({len(still)}) — the worklist for another pass")
        return 0

    if a.json:
        print(json.dumps({"fractions": fractions(resp), "paragraphs": paras}, indent=2))
        return 0
    f = fractions(resp)
    print(f"verdict: {f['verdict']}   AI {f['ai']}%  assisted {f['ai_assisted']}%  human {f['human']}%")
    flagged = [p for p in paras if p["flagged"]]
    print(f"paragraphs: {len(paras)}   flagged at >= {FLAG_SCORE}: {len(flagged)}")
    for p in flagged:
        print(f"  L{p['line_start']:>4}  {p['score']:.2f} {p['confidence'] or '?':6} "
              f"{p['label'] or ''}  {p['preview'][:50]}")
    if not flagged:
        print("  no paragraph over the flag threshold")
    return 0


def main():
    ap = argparse.ArgumentParser(description="map Pangram results onto paragraphs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("payload", help="build prose-only submission text + span map")
    p.add_argument("--article", required=True)
    p.add_argument("--out", help="payload path (default: <article>.payload.txt)")
    p.add_argument("--min-words", type=int, default=0)
    p.set_defaults(func=cmd_payload)

    r = sub.add_parser("report", help="map a response; --baseline to diff")
    r.add_argument("--response", required=True, help="pangram.py --json output")
    r.add_argument("--spans", required=True, help="the .spans.json sidecar")
    r.add_argument("--baseline", help="an earlier response to compare against")
    r.add_argument("--baseline-spans", help="spans for the baseline (default: --spans)")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_report)

    a = ap.parse_args()
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()
