#!/usr/bin/env python3
"""Turn a Pangram response into a worklist, and diff a rewrite against its baseline.

A document-level "70% AI" tells you nothing you can act on. This maps the
overlapping per-window scores back to paragraphs and source line numbers, so the
output is a list of passages to rewrite rather than a grade.

Three subcommands:

  payload   Build the exact text to submit, from the shared paragraph
            extractor (markdown via md_paragraphs, YAML via ProseDocument).
            Prose only — code fences, tables, and front matter are neither
            written by a person in the sense a prose detector measures nor free
            to send, since billing counts started 1,000-word blocks. Writes a
            sidecar .spans.json recording each paragraph's character span in the
            submitted string; without it the response cannot be mapped back.

  paragraphs  Build per-paragraph items for the bulk API, packed into bags of
              ~1,000 words to minimise billable units. Each bag is one bulk item.
              Writes items JSON and a sidecar mapping bags back to paragraphs.

  report    Map a response onto those spans. With --baseline, diff against an
            earlier response and report what moved.

  scan      One-shot: payload + submit + report for a single file. The only
            subcommand that calls the API (it shells out to pangram.py, so it
            needs a key and spends billable units). --keep <dir> saves the
            payload, spans, and response; the default workdir is discarded.

One-shot measurement:

  pangram_report.py scan --article draft.md

Typical flow — single task (the baseline must be captured BEFORE the rewrite):

  pangram_report.py payload --article draft.md --out draft.payload.txt
  pangram.py --text draft.payload.txt --json > before.json
  # ... rewrite ...
  pangram_report.py payload --article draft.md --out draft.payload.txt
  pangram.py --text draft.payload.txt --json > after.json
  pangram_report.py report --response after.json --spans draft.payload.spans.json \\
                           --baseline before.json

Typical flow — bulk API (paragraph-level):

  pangram_report.py paragraphs --article draft.md --out draft.items.json
  pangram.py --bulk draft.items.json --json > results.json
  pangram_report.py report-bulk --results results.json \\
                                --bags draft.items.bags.json

A full comparison costs two scans. Nothing here enforces a quota: pangram.py
--check spends nothing, and the API answers 402 for exhausted credits and 429
for too many requests. Those answers are the source of truth, not a remembered
daily figure.

Stdlib only for markdown input; YAML input imports ruamel.yaml through
prose_document.py. Every subcommand except scan consumes pangram.py --json output
without calling the API, so that half is testable with no key and no credits;
scan is the one subcommand that submits.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

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


def _parse(path):
    """Paragraph extraction, format-dispatched (GH-346).

    Markdown keeps the direct md_paragraphs path (stdlib only). YAML goes
    through ProseDocument, whose to_parse_result() returns the same shape;
    its ruamel.yaml dependency is only imported for .yaml/.yml input.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        if SK not in sys.path:
            sys.path.insert(0, SK)
        try:
            from prose_document import ProseDocument
        except ImportError as e:
            sys.exit(f"could not import prose_document.py from {SK}: {e}")
        return ProseDocument.open(path).to_parse_result()
    return _md_paragraphs().parse_file(path)


def build_payload(path, min_words=0, sep="\n\n"):
    """Assemble prose-only submission text plus the span map.

    Returns (text, spans) where spans entries are
    {index, start, end, line_start, line_end, words, preview}.
    `start`/`end` are character offsets into the returned text, which is what
    Pangram's window offsets index into.
    """
    r = _parse(path)
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


def build_paragraph_payloads(path, min_words=0, word_limit=1000, sep="\n\n"):
    """Build bulk API items by packing paragraphs into ~word_limit-word bags.

    Returns (items, bags) where:
      items — list of {"id": "bag-N", "text": "..."} for submit_bulk
      bags  — list of {"id": "bag-N", "paragraphs": [...], "offsets": [...]}
              mapping each bag back to its source paragraphs with character
              offsets so bulk results can be mapped to individual paragraphs
    """
    r = _parse(path)
    paras = []
    for ls, le, txt in r.paragraphs:
        flat = " ".join(txt.split())
        words = len(flat.split())
        if words < min_words:
            continue
        paras.append({
            "index": len(paras),
            "line_start": ls,
            "line_end": le,
            "words": words,
            "text": flat,
            "preview": flat[:70],
        })

    items, bags = [], []
    bag_paras, bag_texts, bag_words, bag_num = [], [], 0, 0
    for p in paras:
        if bag_texts and bag_words + p["words"] > word_limit:
            item, bag = _emit_bag(bag_num, bag_paras, bag_texts, sep)
            items.append(item)
            bags.append(bag)
            bag_num += 1
            bag_paras, bag_texts, bag_words = [], [], 0
        bag_paras.append(p)
        bag_texts.append(p["text"])
        bag_words += p["words"]
    if bag_texts:
        item, bag = _emit_bag(bag_num, bag_paras, bag_texts, sep)
        items.append(item)
        bags.append(bag)
    return items, bags


def _emit_bag(bag_num, paras, texts, sep):
    combined = sep.join(texts)
    offsets, pos = [], 0
    for i, t in enumerate(texts):
        offsets.append({
            "para_index": paras[i]["index"],
            "line_start": paras[i]["line_start"],
            "line_end": paras[i]["line_end"],
            "start": pos,
            "end": pos + len(t),
            "words": paras[i]["words"],
            "preview": paras[i]["preview"],
        })
        pos += len(t) + len(sep)
    bag_id = f"bag-{bag_num}"
    item = {"id": bag_id, "text": combined}
    bag = {"id": bag_id, "paragraphs": [p["index"] for p in paras],
           "offsets": offsets}
    return item, bag


def map_bulk_results(result_items, bags):
    """Map bulk API per-bag results back to individual paragraphs.

    result_items: list from analyze_bulk — each has "id", "result" (or None
                  on failure), "stage", "error"
    bags: the bags sidecar from build_paragraph_payloads

    Returns a list of paragraph dicts with the same shape as map_windows output.
    """
    by_id = {r.get("id"): r for r in result_items}
    out = []
    for bag in bags:
        result = by_id.get(bag["id"])
        resp = (result or {}).get("result")
        for off in bag["offsets"]:
            entry = {
                "index": off["para_index"],
                "line_start": off["line_start"],
                "line_end": off["line_end"],
                "words": off["words"],
                "preview": off["preview"],
                "bag_id": bag["id"],
            }
            if not resp:
                entry.update(windows=0, score=None, label=None,
                             confidence=None, flagged=False,
                             error=(result or {}).get("error"))
            else:
                hits = []
                for w in resp.get("windows") or []:
                    ws = w.get("start_index")
                    we = w.get("end_index")
                    if ws is None or we is None:
                        continue
                    if ws < off["end"] and we > off["start"]:
                        hits.append(w)
                rank = {"High": 3, "Medium": 2, "Low": 1}
                best = max(hits, key=lambda w: w.get("ai_assistance_score") or 0.0) if hits else None
                conf = max((h.get("confidence") for h in hits),
                           key=lambda c: rank.get(c, 0), default=None)
                entry.update(
                    windows=len(hits),
                    score=(best or {}).get("ai_assistance_score"),
                    label=(best or {}).get("label"),
                    confidence=conf,
                    flagged=bool(best and (best.get("ai_assistance_score") or 0) >= FLAG_SCORE),
                )
            out.append(entry)
    return out


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
    _print_single(resp, paras)
    return 0


def _print_single(resp, paras):
    """The no-baseline report: verdict, fractions, mean window, flagged list."""
    f = fractions(resp)
    print(f"verdict: {f['verdict']}   AI {f['ai']}%  assisted {f['ai_assisted']}%  human {f['human']}%")
    mws = _mean_window_score(resp)
    if mws is not None:
        print(f"mean_window: {mws:.4f}")
    flagged = [p for p in paras if p["flagged"]]
    print(f"paragraphs: {len(paras)}   flagged at >= {FLAG_SCORE}: {len(flagged)}")
    for p in flagged:
        print(f"  L{p['line_start']:>4}  {p['score']:.2f} {p['confidence'] or '?':6} "
              f"{p['label'] or ''}  {p['preview'][:50]}")
    if not flagged:
        print("  no paragraph over the flag threshold")


def cmd_scan(a):
    text, spans = build_payload(a.article, min_words=a.min_words)
    if not spans:
        sys.exit(f"no prose paragraphs found in {a.article} — nothing to submit")
    work = a.keep or tempfile.mkdtemp(prefix="pangram-scan-")
    if a.keep:
        os.makedirs(work, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.article))[0]
    payload = os.path.join(work, stem + ".payload.txt")
    with open(payload, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(work, stem + ".payload.spans.json"), "w",
              encoding="utf-8") as f:
        json.dump({"article": os.path.abspath(a.article), "spans": spans},
                  f, indent=2)
    try:
        r = subprocess.run([sys.executable, os.path.join(SK, "pangram.py"),
                            "--text", payload, "--json"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            # pangram.py's stderr already distinguishes missing key, exhausted
            # credits (402), and network failure; relay it rather than guess.
            sys.exit("scan failed: "
                     + (r.stderr or "no response from pangram.py").strip()[:300])
        with open(os.path.join(work, stem + ".response.json"), "w",
                  encoding="utf-8") as f:
            f.write(r.stdout)
        resp = json.loads(r.stdout)
        if a.json:
            print(r.stdout.rstrip())
            return 0
        _print_single(resp, map_windows(resp, spans))
        if a.keep:
            print(f"kept: {work}")
        return 0
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


def cmd_paragraphs(a):
    items, bags = build_paragraph_payloads(a.article, min_words=a.min_words,
                                           word_limit=a.word_limit)
    if not items:
        sys.exit(f"no prose paragraphs found in {a.article} — nothing to submit")
    out = a.out or (os.path.splitext(a.article)[0] + ".items.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    sidecar = os.path.splitext(out)[0] + ".bags.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"article": os.path.abspath(a.article), "bags": bags}, f, indent=2)
    total_paras = sum(len(b["paragraphs"]) for b in bags)
    total_words = sum(o["words"] for b in bags for o in b["offsets"])
    print(f"items:   {out}  ({len(items)} bags from {total_paras} paragraphs)")
    print(f"bags:    {sidecar}")
    print(f"cost:    ~{len(items)} billable unit{'s' if len(items) != 1 else ''}"
          f"  ({total_words} words)")


def cmd_report_bulk(a):
    results = _load(a.results)
    bags = _load(a.bags)["bags"]
    paras = map_bulk_results(results, bags)
    if a.json:
        print(json.dumps(paras, indent=2))
        return 0
    flagged = [p for p in paras if p["flagged"]]
    failed = [p for p in paras if p.get("error")]
    print(f"paragraphs: {len(paras)}   flagged at >= {FLAG_SCORE}: {len(flagged)}"
          f"   failed: {len(failed)}")
    for p in flagged:
        print(f"  L{p['line_start']:>4}  {p['score']:.2f} {p['confidence'] or '?':6} "
              f"{p['label'] or ''}  {p['preview'][:50]}")
    if not flagged:
        print("  no paragraph over the flag threshold")
    for p in failed:
        print(f"  L{p['line_start']:>4}  ERROR: {p['error']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="map Pangram results onto paragraphs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("payload", help="build prose-only submission text + span map")
    p.add_argument("--article", required=True)
    p.add_argument("--out", help="payload path (default: <article>.payload.txt)")
    p.add_argument("--min-words", type=int, default=0)
    p.set_defaults(func=cmd_payload)

    sc = sub.add_parser("scan",
                        help="one-shot: payload + pangram.py submit + report")
    sc.add_argument("--article", required=True)
    sc.add_argument("--min-words", type=int, default=0)
    sc.add_argument("--keep", help="directory to save payload, spans, and "
                                   "response (default: tempdir, discarded)")
    sc.add_argument("--json", action="store_true",
                    help="emit the raw detector response instead of the report")
    sc.set_defaults(func=cmd_scan)

    pg = sub.add_parser("paragraphs",
                        help="build bulk API items packed into ~1000-word bags")
    pg.add_argument("--article", required=True)
    pg.add_argument("--out", help="items path (default: <article>.items.json)")
    pg.add_argument("--min-words", type=int, default=0)
    pg.add_argument("--word-limit", type=int, default=1000,
                    help="target words per bag (default: 1000)")
    pg.set_defaults(func=cmd_paragraphs)

    r = sub.add_parser("report", help="map a response; --baseline to diff")
    r.add_argument("--response", required=True, help="pangram.py --json output")
    r.add_argument("--spans", required=True, help="the .spans.json sidecar")
    r.add_argument("--baseline", help="an earlier response to compare against")
    r.add_argument("--baseline-spans", help="spans for the baseline (default: --spans)")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_report)

    rb = sub.add_parser("report-bulk",
                        help="map bulk results back to paragraphs")
    rb.add_argument("--results", required=True,
                    help="pangram.py --bulk output (JSON list of result items)")
    rb.add_argument("--bags", required=True, help="the .bags.json sidecar")
    rb.add_argument("--json", action="store_true")
    rb.set_defaults(func=cmd_report_bulk)

    a = ap.parse_args()
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()
