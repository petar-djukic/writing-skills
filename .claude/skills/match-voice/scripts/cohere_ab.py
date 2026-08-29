#!/usr/bin/env python3
"""Cohere A/B harness: does a system/user split change what survives a rewrite?

GH-153 proposed routing Cohere with the rules in a `system` message and only
the content in `user`, on the strength of a single-passage A/B where the split
preserved a citation 4/4 and the current single-message shape dropped it 4/4.
A replication did not reproduce that. This harness settles it on a real draft.

Two measurements:

  sweep       every citation- or number-bearing paragraph of a draft, through
              the real match-voice prompt, 2 models x 2 arms.
  replicate   GH-153's own passage and prompt (filter-tells' _REWRITE_PROMPT),
              repeated, so the disputed result is tested directly.

Arms:
  A  everything in one `user` message         (what the code does today)
  B  rules in `system`, content in `user`     (what GH-153 proposes)

Pacing matters: a Cohere trial key allows 20 calls/minute, and an unpaced
sweep fills with 429s that look like failures.

Usage:
  COHERE_SECRETS_FILE=... python3 cohere_ab.py sweep <draft.md> [--out results.json]
  COHERE_SECRETS_FILE=... python3 cohere_ab.py replicate [--trials 6]
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts")))
import rewrite as rw  # noqa: E402
import md_paragraphs as mp  # noqa: E402

MODELS = ("cohere:command-a-03-2025", "cohere:command-a-plus-05-2026")
# 20 calls/minute on a trial key. 3.2s leaves headroom for jitter.
PACE_SECONDS = float(os.environ.get("COHERE_AB_PACE", "3.2"))

CITE = re.compile(r"\[@[A-Za-z0-9_:-]+\]|\[\d+\]")
# Trailing punctuation is not part of the number: "43," and "43" are the same
# figure, and treating them as different reports every rewrite as damaging.
NUM = re.compile(r"(?<![\w@-])\d+(?:[.,]\d+)*%?(?![\w-])")
# Meta the rewrite must not contain. Narrower than rewrite.py's sanitizer,
# because here we want to COUNT leakage, not remove it.
META = ("we need to", "let me ", "let's ", "rewritten paragraph", "<eos_token>",
        "here is the", "the passage has been", "i should ", "as an ai")


def _split_match_voice_prompt(paragraph, anchors):
    """(rules, content) for the match-voice prompt.

    Arm A concatenates these; arm B sends the first as `system`. The rules half
    is everything the model must obey, the content half is the one paragraph it
    is being asked to transform."""
    full = rw.build_prompt(paragraph, anchors)
    marker = "PARAGRAPH TO REWRITE:\n"
    head, _, tail = full.partition(marker)
    return head.rstrip(), tail.strip()


FT_RULES = """\
You are rewriting a passage to remove AI writing patterns while \
preserving exact meaning and matching the author's voice.

AUTHOR'S STYLE:
- Concise, active voice, Strunk & White style
- Specific and concrete, no vague qualifiers
- Takes positions, avoids hedging
- Varied sentence rhythm
- Technical precision without jargon inflation

CONSTRAINTS:
1. Fix ONLY the flagged issues
2. Preserve all technical meaning
3. Do NOT introduce any patterns from the banned list
4. Vary sentence length (target std > 5)
5. Do NOT use mechanical transitions
6. Do NOT hedge or both-sides
7. Sound like a human expert wrote this in one draft
8. Plain sentences are allowed and required
9. Do NOT close every paragraph on a flourish
10. Prefer the boring accurate sentence over the clever compressed one

OUTPUT: The rewritten passage only. No commentary."""


def _ft_content(passage, issues):
    return f"DETECTED ISSUES IN THIS PASSAGE:\n{issues}\n\nPASSAGE TO REWRITE:\n{passage}"


def call(rules, content, model, arm, temperature=0.3):
    """One rewrite through the real generate(). Arm A concatenates, arm B splits."""
    if arm == "A":
        return rw.generate(rules + "\n\n" + content, model=model,
                           temperature=temperature)
    return rw.generate(content, model=model, temperature=temperature,
                       system=rules)


def score(original, produced):
    """What survived. Citations and numbers are multisets: a rewrite that drops
    one of two [3]s has not preserved them."""
    low = (produced or "").lower()
    return {
        "cites_in": sorted(CITE.findall(original)),
        "cites_out": sorted(CITE.findall(produced or "")),
        "cites_kept": sorted(CITE.findall(original)) == sorted(CITE.findall(produced or "")),
        "nums_in": sorted(NUM.findall(original)),
        "nums_kept": sorted(NUM.findall(original)) == sorted(NUM.findall(produced or "")),
        "meta_hits": [m for m in META if m in low],
        "words_in": len(original.split()),
        "words_out": len((produced or "").split()),
    }


def _run(rules, content, original, model, arm, idx):
    try:
        out = call(rules, content, model, arm)
        rec = score(original, out)
        rec.update(ok=True, text=out)
    except RuntimeError as e:
        rec = {"ok": False, "error": str(e)[:200]}
    rec.update(model=model.split(":", 1)[1], arm=arm, item=idx)
    flag = ("ERR" if not rec["ok"]
            else ("ok " if rec["cites_kept"] and rec["nums_kept"] and not rec["meta_hits"]
                  else "BAD"))
    print(f"  [{flag}] {rec['model'][:12]:12s} arm {arm} item {idx:02d}"
          + ("" if not rec["ok"] else
             f"  cites={'Y' if rec['cites_kept'] else 'N'}"
             f" nums={'Y' if rec['nums_kept'] else 'N'}"
             f" meta={len(rec['meta_hits'])}"), flush=True)
    time.sleep(PACE_SECONDS)
    return rec


def _text_of(p):
    """md_paragraphs.paragraphs() yields [start, end, text] triples. Taking
    str(p) on one sends the model a Python list repr — line numbers, escaped
    newlines and all — and scores the rewrite against that repr rather than
    against the prose. It looks like it works: the output stays plausible and
    only the number check goes strange."""
    if isinstance(p, str):
        return p
    if isinstance(p, (list, tuple)):
        return next((x for x in reversed(p) if isinstance(x, str)), "")
    return getattr(p, "text", "")


def sweep(path, out_path):
    paras = [t for t in (_text_of(p) for p in
                         mp.paragraphs(open(path).read(), min_words=25)) if t]
    anchors = "\n\n".join(paras[:3])          # constant across every arm
    targets = [p for p in paras[3:] if CITE.search(p) or NUM.search(p)]
    print(f"draft: {path}\nanchors: 3 paragraphs (constant)\n"
          f"targets: {len(targets)} paragraphs -> {len(targets) * 4} calls "
          f"at {PACE_SECONDS}s pacing\n")
    results = []
    for i, para in enumerate(targets):
        rules, content = _split_match_voice_prompt(para, anchors)
        for model in MODELS:
            for arm in ("A", "B"):
                results.append(_run(rules, content, para, model, arm, i))
    _report(results, "SWEEP (match-voice prompt, real draft)")
    if out_path:
        json.dump(results, open(out_path, "w"), indent=1)
        print(f"\nwrote {out_path}")
    return results


def replicate(trials, out_path=None):
    """GH-153's own passage and prompt, repeated."""
    passage = ("Google DORA research highlights a correlation between AI adoption "
               "and increased throughput, but also notes a decrease in delivery "
               "stability [2].")
    issues = "[dash-heavy] 3.9 per 500w\n[hedge] both-sides framing"
    content = _ft_content(passage, issues)
    print(f"replication: GH-153 passage, filter-tells prompt, {trials} trials/arm "
          f"-> {trials * 4} calls\n")
    results = []
    for i in range(trials):
        for model in MODELS:
            for arm in ("A", "B"):
                results.append(_run(FT_RULES, content, passage, model, arm, i))
    _report(results, "REPLICATION (filter-tells prompt, GH-153 passage)")
    if out_path:
        json.dump(results, open(out_path, "w"), indent=1)
        print(f"\nwrote {out_path}")
    return results


def _report(results, title):
    print(f"\n## {title}\n")
    print("| model | arm | n | citations kept | numbers kept | meta-leak | errors | mean words |")
    print("|---|---|--:|--:|--:|--:|--:|--:|")
    for model in (m.split(":", 1)[1] for m in MODELS):
        for arm in ("A", "B"):
            rs = [r for r in results if r["model"] == model and r["arm"] == arm]
            ok = [r for r in rs if r["ok"]]
            if not rs:
                continue
            cite = [r for r in ok if r["cites_in"]]
            cs = (f"{sum(r['cites_kept'] for r in cite)}/{len(cite)}" if cite else "n/a")
            ns = f"{sum(r['nums_kept'] for r in ok)}/{len(ok)}" if ok else "n/a"
            mw = round(sum(r["words_out"] for r in ok) / len(ok), 1) if ok else 0
            print(f"| {model} | {arm} | {len(rs)} | {cs} | {ns} | "
                  f"{sum(1 for r in ok if r['meta_hits'])} | {len(rs) - len(ok)} | {mw} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sw = sub.add_parser("sweep"); sw.add_argument("draft"); sw.add_argument("--out")
    rp = sub.add_parser("replicate")
    rp.add_argument("--trials", type=int, default=6)
    rp.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "sweep":
        sweep(a.draft, a.out)
    else:
        replicate(a.trials, a.out)


if __name__ == "__main__":
    main()
