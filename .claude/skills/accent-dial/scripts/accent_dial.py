#!/usr/bin/env python3
"""accent-dial: apply a controllable amount of the author's Serbian-L1 accent
to an article by accepting a ranked fraction of round-trip translation edits
(GH-69).

The EN->SR->EN round-trip is the only measured source of the accent (see
paper-stash writing-voice/l2-markers.yaml), but whole-text round-trip is
all-or-nothing. Here the round-trip is a CANDIDATE GENERATOR: paragraphs are
aligned 1:1, mechanically gated, ranked by Serbian-ness, and --dial p applies
the top fraction deterministically. Every candidate lands in the edit log with
its gate verdict and scores, so edits revert individually and survival can be
analyzed, in the inject-vernacular mold.

Mechanical gates pass what semantic review rejects: the run is not done until
an agent entailment-reviews the applied paragraphs (see SKILL.md).
"""
import argparse
import difflib
import json
import os
import re
import sys
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma4:31b-cloud"
CHUNK = 6

# Serbian-L1 calque patterns, mirrored from paper-stash
# writing-voice/l2-markers.yaml (calque_rate); that bank is canonical — grow
# the list there first, then mirror here.
CALQUES = re.compile(
    r"\b(?:survive[ds]?\s+before\s+(?:it|them|him|her)"
    r"|in\s+(?:one's|his|her|my|your)\s+head"
    r"|answered\s+in\s+advance"
    r"|feel\s+the\s+void"
    r"|a\s+guy\s+from\s+\w+)\b", re.I)

LOCK = re.compile(r"<!--\s*/?(?:lock|snark)[^>]*-->")


def chat(prompt, model, temperature=0.2, retries=3):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    err = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001 — retry any transport failure
            err = e
    raise SystemExit(f"ollama unreachable after retries: {err}")


SR_PROMPT = ("Prevedi sledeci tekst na srpski jezik (latinica). Sacuvaj podelu "
             "na pasuse: pasusi su razdvojeni praznim redom, i prevod mora "
             "imati isti broj pasusa. Brojeve, imena i citate u uglastim "
             "zagradama poput [7] prepisi tacno. Ispisi SAMO prevod, bez "
             "komentara.\n\n")
EN_PROMPT = ("Translate the following Serbian text into English. Keep the "
             "paragraph structure: paragraphs are separated by a blank line, "
             "and the translation must have the same number of paragraphs. "
             "Copy numbers, names, and bracketed citations like [7] exactly. "
             "Output ONLY the translation, no commentary.\n\n")


def split_paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def run_leg(paras, prompt, model):
    out = []
    for i in range(0, len(paras), CHUNK):
        chunk = paras[i:i + CHUNK]
        got = split_paras(chat(prompt + "\n\n".join(chunk), model))
        if len(got) != len(chunk):
            got = [" ".join(split_paras(chat(prompt + p, model)))
                   for p in chunk]
        out.extend(got)
        print(f"  {min(i + CHUNK, len(paras))}/{len(paras)}", file=sys.stderr)
    return out


def roundtrip(paras, model):
    print("leg 1: EN -> SR", file=sys.stderr)
    sr = run_leg(paras, SR_PROMPT, model)
    print("leg 2: SR -> EN (blind)", file=sys.stderr)
    return run_leg(sr, EN_PROMPT, model)


def is_prose(p):
    head = p.lstrip()[:2]
    return not (head.startswith("#") or head.startswith(">")
                or head.startswith("!") or head.startswith("|")
                or head.startswith("``") or head.startswith("<"))


def gate(orig, rt):
    """Return None if the pair is applicable, else the failure reason."""
    if LOCK.search(orig):
        return "locked-span"
    if not is_prose(orig):
        return "not-prose"
    if sorted(re.findall(r"\[\d+\]", orig)) != sorted(
            re.findall(r"\[\d+\]", rt)):
        return "citation-drift"
    if sorted(re.findall(r"\d+", orig)) != sorted(re.findall(r"\d+", rt)):
        return "number-drift"
    ow, rw = len(orig.split()), len(rt.split())
    if not ow or not 0.6 <= rw / ow <= 1.6:
        return "length-drift"
    if orig.strip() == rt.strip():
        return "unchanged"
    return None


def score(orig, rt):
    """Serbian-ness of the candidate: calques dominate, restructuring breaks
    ties. Higher = applied earlier as the dial opens."""
    restructure = 1.0 - difflib.SequenceMatcher(None, orig, rt).ratio()
    return 10.0 * len(CALQUES.findall(rt)) + restructure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True,
                    help="markdown/payload file; paragraphs blank-line "
                         "separated")
    ap.add_argument("--roundtrip",
                    help="cached round-trip file, paragraph-aligned; default "
                         "<stem>.roundtrip.txt beside the article, generated "
                         "via Ollama when absent")
    ap.add_argument("--dial", type=float, required=True,
                    help="0..1: fraction of gated candidates to apply, "
                         "best-ranked first")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", help="default <stem>.dial<p><ext>")
    ap.add_argument("--log", help="default <out>.log.json")
    args = ap.parse_args()
    if not 0.0 <= args.dial <= 1.0:
        sys.exit("--dial must be in [0, 1]")

    with open(args.article, encoding="utf-8") as f:
        paras = split_paras(f.read())

    rt_path = args.roundtrip or (
        os.path.splitext(args.article)[0] + ".roundtrip.txt")
    if os.path.exists(rt_path):
        with open(rt_path, encoding="utf-8") as f:
            rt = split_paras(f.read())
    else:
        rt = roundtrip(paras, args.model)
        with open(rt_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(rt))
        print(f"round-trip cached: {rt_path}", file=sys.stderr)
    if len(rt) != len(paras):
        sys.exit(f"alignment lost: {len(paras)} original vs {len(rt)} "
                 f"round-trip paragraphs — regenerate the cache")

    cands = []
    for i, (o, r) in enumerate(zip(paras, rt)):
        why = gate(o, r)
        cands.append({"index": i, "gate": why,
                      "score": round(score(o, r), 4) if why is None else None})
    gated = sorted((c for c in cands if c["gate"] is None),
                   key=lambda c: -c["score"])
    k = round(args.dial * len(gated))
    applied = {c["index"] for c in gated[:k]}
    for c in cands:
        c["applied"] = c["index"] in applied

    out_paras = [rt[i] if i in applied else p
                 for i, p in enumerate(paras)]
    stem, ext = os.path.splitext(args.article)
    out_path = args.out or f"{stem}.dial{args.dial:g}{ext or '.txt'}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(out_paras) + "\n")

    log = {"article": args.article, "roundtrip": rt_path, "model": args.model,
           "dial": args.dial, "paragraphs": len(paras),
           "gated": len(gated), "applied": k, "candidates": cands}
    log_path = args.log or out_path + ".log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

    fails = {}
    for c in cands:
        if c["gate"]:
            fails[c["gate"]] = fails.get(c["gate"], 0) + 1
    print(f"applied {k}/{len(gated)} gated candidates "
          f"(of {len(paras)} paragraphs; gate failures: {fails})\n"
          f"out: {out_path}\nlog: {log_path}")


if __name__ == "__main__":
    main()
