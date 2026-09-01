#!/usr/bin/env python3
"""critic-apply — rule-based application of a converged critic sheet
(GH-206).

Consumes a converge.py sheet and an article, applies the operator policy
(2026-09-01) mechanically, and reports applied/kept/declined-by-rule
counts for the generation: block. The rules, as code:

  accept    every convergent target (2+ distinct critics on one passage)
  accept    a single-critic CUT whose paragraph the reverse-outline sheet
            ranked cheap (cross-instrument agreement counts as
            convergence for deletions)
  skip      split panels — a proposal beside a dissent (KEEP / NO CHANGE)
            is not convergence
  decline   targets inside a protected or locked span, with cause; the
            constitution outranks the panel
  prefer    the omission when remedies conflict inside a convergence —
            a deletion authors no prose

Application mechanics, learned the hard way: rst markers are stripped
before the model call and reattached after (their digits fail the number
gate — measured); each rewrite target gets a narrow one-sentence
instruction through the rewrite transport, never persona prose spliced
in; every candidate passes a mechanical gate (number multiset, citation
multiset, em-dash/colon budget, 0.5–1.35 size band) or the original is
kept; deletions apply directly with mechanical punctuation
normalization.
"""

import argparse
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
MATCH_VOICE = os.path.normpath(os.path.join(HERE, "..", "..", "match-voice",
                                            "scripts"))
sys.path.insert(0, SHARED)
import md_paragraphs  # noqa: E402

THRESHOLD = 0.8
RST = re.compile(r"<!--\s*rst:.*?-->\s*", re.S)
DISSENT = re.compile(r"^\s*(KEEP|NO CHANGE|LEAVE|AS IS)\b", re.I)
CUT = re.compile(r"^\s*CUT\b")
NUM = re.compile(r"\d[\d,\.]*")
CITE = re.compile(r"\[@[^\]\s]+\]|\[\d{1,3}\]")


def norm(s):
    return " ".join(s.lower().split())


def parse_sheet(text):
    """Convergent and single-critic targets out of a converge.py sheet."""
    targets = []
    m = re.search(r"^## Convergent[^\n]*\n(.*?)(?=^## |\Z)", text,
                  re.M | re.S)
    if m:
        for block in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
            qm = re.match(r'"(.*?)"\s*\n', block, re.S)
            if not qm:
                continue
            entries = []
            for c, b, w in re.findall(
                    r"^- \*\*([^:*]+):\*\*\s*(.*?)(?:\s+—\s+\*(.*?)\*)?\s*$",
                    block, re.M):
                entries.append({"critic": c.strip(), "body": b.strip(),
                                "why": (w or "").strip()})
            if entries:
                targets.append({"quote": qm.group(1), "convergent": True,
                                "entries": entries})
    m = re.search(r"^## Single-critic[^\n]*\n(.*?)(?=^## |\Z)", text,
                  re.M | re.S)
    if m:
        critic = None
        for line in m.group(1).splitlines():
            hm = re.match(r"^### (\S+)", line)
            if hm:
                critic = hm.group(1)
                continue
            im = re.match(
                r'^\d+\.\s+"(.*)"\s+→\s+(.*?)(?:\s+—\s+\*(.*)\*)?\s*$', line)
            if im and critic:
                targets.append({
                    "quote": im.group(1), "convergent": False,
                    "entries": [{"critic": critic,
                                 "body": im.group(2).strip(),
                                 "why": (im.group(3) or "").strip()}]})
    return targets


def strip_rst(text):
    """(clean_text, markers) — markers reattach verbatim, in order, at the
    paragraph head after a rewrite. Their digits otherwise fail the
    number gate (measured on the first automated run)."""
    markers = RST.findall(text)
    return RST.sub("", text).strip(), [m.strip() for m in markers]


def find_paragraph(paras, quote):
    """1-based prose paragraph containing the quote, else None."""
    q = norm(quote)
    for n, (s, e, txt) in enumerate(paras, 1):
        t = norm(strip_rst(txt)[0])
        if q in t:
            return n
    best, best_n = 0.0, None
    for n, (s, e, txt) in enumerate(paras, 1):
        r = difflib.SequenceMatcher(
            None, q, norm(strip_rst(txt)[0]), autojunk=False).ratio()
        if r > best:
            best, best_n = r, n
    return best_n if best >= 0.6 else None


def _flexible_pattern(quote):
    return r"\s+".join(re.escape(w) for w in quote.split())


def normalize_punct(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"([,;:]) *([,.;:])", r"\2", text)
    return text.strip()


def delete_quote(par_text, quote):
    """Remove the quoted sentence from the paragraph; '' if nothing is
    left. Whitespace-flexible so a reflowed paragraph still matches."""
    clean, markers = strip_rst(par_text)
    new = re.sub(_flexible_pattern(quote), " ", clean, count=1)
    if norm(new) == norm(clean):
        return None
    new = normalize_punct(new)
    if not new:
        return ""
    return "\n".join(markers + [new]) if markers else new


def gate(orig_clean, cand):
    """Mechanical gate. Returns (ok, reason)."""
    if sorted(NUM.findall(CITE.sub(" ", cand))) != \
            sorted(NUM.findall(CITE.sub(" ", orig_clean))):
        return False, "number multiset changed"
    if sorted(CITE.findall(cand)) != sorted(CITE.findall(orig_clean)):
        return False, "citation multiset changed"
    for ch, name in (("—", "em-dash"), (":", "colon")):
        if cand.count(ch) > orig_clean.count(ch):
            return False, f"{name} budget exceeded"
    ow, cw = len(orig_clean.split()), len(cand.split())
    if not ow or not (0.5 <= cw / ow <= 1.35):
        return False, f"size band ({cw}/{ow} words)"
    return True, ""


def build_prompt(par_clean, quote, instruction):
    return ("Rewrite the paragraph below, changing ONLY the quoted "
            "sentence, per the instruction. Keep every citation, number, "
            "and quoted phrase exactly. Return only the rewritten "
            "paragraph, no preamble.\n"
            f"Instruction: {instruction}\n"
            f'Sentence to change: "{quote}"\n'
            f"Paragraph:\n{par_clean}")


def decide_and_apply(article_text, targets, generate=None,
                     protected=(), cheap=frozenset()):
    """The whole policy. Returns (new_text, records)."""
    parsed = md_paragraphs.parse(article_text)
    paras = parsed.paragraphs
    records, edits = [], {}   # n -> replacement text ('' = drop block)

    for t in targets:
        rec = {"quote": t["quote"][:80],
               "critics": sorted({e["critic"] for e in t["entries"]})}
        records.append(rec)
        n = find_paragraph(paras, t["quote"])
        rec["paragraph"] = n
        bodies = [e["body"] for e in t["entries"]]
        is_cut = any(CUT.match(b) for b in bodies)

        if t["convergent"] and any(DISSENT.match(b) for b in bodies) \
                and not all(DISSENT.match(b) for b in bodies):
            rec["status"] = "skipped-split-panel"
            continue
        if not t["convergent"] and not (is_cut and n in cheap):
            rec["status"] = "skipped-not-convergent"
            continue
        if not t["convergent"]:
            rec["cross_instrument"] = "reverse-outline-cheap"
        if n is None:
            rec["status"] = "kept-target-not-found"
            continue
        if n in edits:
            rec["status"] = "kept-paragraph-already-edited"
            continue

        par_text = paras[n - 1][2]
        hit = next((p for p in protected
                    if norm(p) and norm(p) in norm(par_text)), None)
        if hit:
            rec["status"] = "declined-constitution"
            rec["cause"] = f"protected span: {hit[:60]}"
            continue

        if is_cut:
            new = delete_quote(par_text, t["quote"])
            if new is None:
                rec["status"] = "kept-quote-not-in-paragraph"
                continue
            edits[n] = new
            rec["status"] = "applied-deletion"
            continue

        # Rewrite through the transport; a remedy conflict without a CUT
        # is still one shared finding — the instruction is the why.
        if generate is None:
            rec["status"] = "kept-no-model"
            continue
        clean, markers = strip_rst(par_text)
        instruction = next((e["why"] for e in t["entries"] if e["why"]),
                           t["entries"][0]["body"])
        try:
            cand = generate(build_prompt(clean, t["quote"], instruction))
        except Exception as e:  # transport errors keep the original
            rec["status"] = "kept-rewrite-error"
            rec["cause"] = str(e)[:120]
            continue
        cand = (cand or "").strip().strip("`").strip()
        ok, why_not = gate(clean, cand)
        if not ok:
            rec["status"] = "kept-gate"
            rec["cause"] = why_not
            continue
        edits[n] = "\n".join(markers + [cand]) if markers else cand
        rec["status"] = "applied-rewrite"

    # Splice bottom-up so earlier line ranges stay valid.
    lines = article_text.split("\n")
    for n in sorted(edits, reverse=True):
        s, e, _txt = paras[n - 1]
        if edits[n] == "":
            del lines[s - 1:e]
            # a deleted paragraph takes its rst marker line with it
            i = s - 2
            while i >= 0 and not lines[i].strip():
                i -= 1
            if i >= 0 and RST.match(lines[i].strip()):
                del lines[i]
        else:
            lines[s - 1:e] = edits[n].split("\n")
    return "\n".join(lines), records


def counts(records):
    c = {}
    for r in records:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return {"applied": sum(v for k, v in c.items() if k.startswith("applied")),
            "kept": sum(v for k, v in c.items() if k.startswith("kept")),
            "declined_by_rule": sum(v for k, v in c.items()
                                    if k.startswith(("declined", "skipped"))),
            "by_status": c}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--article", required=True)
    ap.add_argument("--sheet", required=True,
                    help="converge.py sheet (<stem>.critic-sheet.md)")
    ap.add_argument("--out", help="default: <article stem>.applied.md")
    ap.add_argument("--protected", help="file of verbatim spans the "
                    "constitution protects; one per line")
    ap.add_argument("--cheap-paragraphs",
                    help="reverse-outline-ranked cheap paragraphs, e.g. "
                         "'3,7' — cross-instrument convergence for "
                         "single-critic deletions")
    ap.add_argument("--model", default=os.environ.get(
        "CRITIC_APPLY_MODEL", "cohere:command-a-03-2025"))
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and report; no model calls, no writes")
    a = ap.parse_args()

    text = open(a.article, encoding="utf-8").read()
    targets = parse_sheet(open(a.sheet, encoding="utf-8").read())
    protected = []
    if a.protected:
        protected = [ln.strip() for ln in open(a.protected, encoding="utf-8")
                     if ln.strip() and not ln.startswith("#")]
    cheap = set()
    if a.cheap_paragraphs:
        cheap = {int(x) for x in a.cheap_paragraphs.split(",") if x.strip()}

    generate = None
    if not a.dry_run:
        sys.path.insert(0, MATCH_VOICE)
        import rewrite as _rw

        def generate(prompt):
            kw = {"model": a.model, "temperature": 0.3}
            if a.endpoint:
                kw["endpoint"] = a.endpoint
            return _rw.generate(prompt, **kw)

    new_text, records = decide_and_apply(
        text, targets, generate=generate, protected=protected, cheap=cheap)

    out = a.out or os.path.splitext(a.article)[0] + ".applied.md"
    if not a.dry_run:
        open(out, "w", encoding="utf-8").write(new_text)
    log = out + ".critic-apply.json"
    summary = counts(records)
    json.dump({"article": a.article, "sheet": a.sheet, "model": a.model,
               "summary": summary, "targets": records},
              open(log, "w", encoding="utf-8"), indent=2)

    print(f"{'DRY RUN — ' if a.dry_run else ''}targets: {len(records)}")
    for k, v in sorted(summary["by_status"].items()):
        print(f"  {k}: {v}")
    print(f"applied: {summary['applied']}  kept: {summary['kept']}  "
          f"declined-by-rule: {summary['declined_by_rule']}")
    if not a.dry_run:
        print(f"out: {out}")
    print(f"log: {log}")


if __name__ == "__main__":
    main()
