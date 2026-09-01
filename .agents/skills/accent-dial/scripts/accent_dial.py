#!/usr/bin/env python3
"""accent-dial: apply a controllable amount of the author's Serbian-L1 accent
to an article by accepting a ranked fraction of round-trip translation edits
(GH-69, sentence grain GH-73).

The EN->SR->EN round-trip is the only measured source of the accent (see
paper-stash writing-voice/l2-markers.yaml), but whole-text round-trip is
all-or-nothing. Here the round-trip is a CANDIDATE GENERATOR: units are
aligned, mechanically gated, ranked by Serbian-ness, and --dial p applies the
top fraction deterministically. Every candidate lands in the edit log with its
gate verdict and scores, so edits revert individually and survival can be
analyzed, in the inject-vernacular mold.

Two grains:
- sentence (default): candidates are 1:1-aligned sentences, selection is
  globally ranked but capped per paragraph — the accent disperses evenly
  instead of forming fully-translated paragraph walls (the GH-175 author-gate
  rejection of paragraph grain: "sounds too much like an ESL wrote it").
- paragraph: whole paragraphs swap, the original GH-69 behavior.

Mechanical gates pass what semantic review rejects: the run is not done until
an agent entailment-reviews the applied units (see SKILL.md).
"""
import argparse
import difflib
import json
import os
import re
import sys
import urllib.request

# Shared transport from match-voice (GH-184): every stage that goes through
# generate() gets the cohere: routing, the retry/backoff, and the typed-block
# parsing for free — the GH-137 rationale this script had missed by carrying
# its own /api/chat client.
_MV = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                    "..", "..", "match-voice", "scripts"))
if _MV not in sys.path:
    sys.path.insert(0, _MV)
from rewrite import generate as _generate  # noqa: E402

DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
# Deliberately NOT the Cohere default the other stages converged on (GH-184):
# the 2026-08-21 A/B measured a stronger return-leg translator polishing the
# accent away (gpt-oss L2 composite -0.009 vs gemma +0.726), and injecting
# accent is this skill's entire job. ACCENT_DIAL_MODEL (or --model) selects
# cohere:command-a-03-2025 when wanted — the shared transport routes it — but
# the default follows the measurement.
DEFAULT_MODEL = os.environ.get("ACCENT_DIAL_MODEL", "gemma4:31b-cloud")
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

# Non-greedy rather than `[^>]*` (GH-96): the class stops at the first `>`,
# so a marker carrying an arrow would not match. Anchored on lock|snark, so
# this one could never swallow an rst marker — hardened with the other site
# rather than left as the last instance of the pattern.
LOCK = re.compile(r"<!--\s*/?(?:lock|snark).*?-->")
SENT_SPLIT = re.compile(
    r"(?:(?<=[.!?])|(?<=[.!?][\"”]))\s+(?=[A-Z\"“'(\[*])")
QUOTED = re.compile(r"\"([^\"]{2,})\"|“([^”]{2,})”")


def chat(prompt, model, temperature=0.2, retries=3):
    """One generation through the shared transport. `retries` is honored by
    generate()'s own bounded retry; the parameter stays for call-site
    compatibility."""
    try:
        return _generate(prompt, endpoint=DEFAULT_ENDPOINT, model=model,
                         temperature=temperature, timeout=600).strip()
    except RuntimeError as e:
        raise SystemExit(str(e))


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

# The language dial (GH-186). Serbian is the calibrated default and keeps its
# native-language outbound prompt above; any other pivot gets these
# English-phrased templates. The calque gate below stays Serbian-calibrated
# either way — see prompts_for().
OUT_TEMPLATE = ("Translate the following text into {language}. Keep the "
                "paragraph structure: paragraphs are separated by a blank "
                "line, and the translation must have the same number of "
                "paragraphs. Copy numbers, names, and bracketed citations "
                "like [7] exactly. Output ONLY the translation, no "
                "commentary.\n\n")
BACK_TEMPLATE = ("Translate the following {language} text into English. Keep "
                 "the paragraph structure: paragraphs are separated by a "
                 "blank line, and the translation must have the same number "
                 "of paragraphs. Copy numbers, names, and bracketed citations "
                 "like [7] exactly. Output ONLY the translation, no "
                 "commentary.\n\n")


def prompts_for(language):
    """(outbound, back) prompts for a pivot language.

    Serbian — the default, and the language the scoring gate is calibrated
    for — keeps the prompts the 2026-08-21 calibration ran with, byte for
    byte. Any other pivot produces its own accent flavor, but score()'s
    calque term is a Serbian-L1 pattern bank and contributes nothing there:
    ranking degrades to restructuring distance alone. Reduced gate fidelity,
    not breakage; the caller prints the caveat."""
    if language.strip().lower() == "serbian":
        return SR_PROMPT, EN_PROMPT
    name = language.strip().title()
    return OUT_TEMPLATE.format(language=name), BACK_TEMPLATE.format(language=name)


def split_paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_sentences(para):
    return [s for s in SENT_SPLIT.split(" ".join(para.split())) if s]


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


# The fluency dial (GH-188). A bare immersion-years number is a NULL — four
# levels (5/10/20/30) produced near-identical fluent output; the model cannot
# calibrate fluency to a number. Describing what each level SOUNDS like works:
# the 2026-08-31 experiment got a visible, subtle gradient (fronted adverbs
# and dropped articles at fresh, faint formality at settled, idiomatic at
# native). The bands name concrete features; l2-markers.yaml is the canonical
# bank to grow them from.
FLUENCY_BANDS = {
    "fresh": (
        "Their English carries visible {l1} traces: articles (a/the) "
        "occasionally dropped or misplaced, present tense where English "
        "wants perfect, direct {l1} phrasings translated word-for-word where "
        "a native would use an idiom, slightly formal word choice where "
        "natives go casual. Grammatical, understandable, but recognizably "
        "L2."),
    "settled": (
        "Their English is fluent and comfortable but not native: an "
        "occasional slightly-off idiom or article, a preference for direct "
        "statement over English hedging, sentence rhythm a touch more even "
        "than a native's. One subtle trace per few sentences, no more."),
    "native": (
        "Their English is fully idiomatic after decades of immersion; at "
        "most one faint trace of directness per paragraph survives."),
}


def fluency_band(years):
    """Immersion years -> band name. The cutoffs are coarse on purpose: the
    experiment showed the model only distinguishes described bands, so finer
    year granularity would imply a precision the mechanism does not have."""
    return "fresh" if years <= 8 else ("settled" if years <= 22 else "native")


def fluency_return_prompt(language, band):
    """Return-leg prompt carrying a fluency persona. Separate from
    prompts_for(): the blind mechanical return leg stays byte-identical to
    the calibration when no fluency is requested."""
    l1 = language.strip().title()
    features = FLUENCY_BANDS[band].replace("{l1}", l1)
    return ("Translate the following " + l1 + " text into English as written "
            "by a native " + l1 + " speaker. " + features + " Keep the "
            "paragraph structure: paragraphs are separated by a blank line, "
            "and the translation must have the same number of paragraphs. "
            "Copy numbers, names, and bracketed citations like [7] exactly. "
            "Output ONLY the translation, no commentary.\n\n")


def roundtrip(paras, model, model_return=None, language="serbian",
              fluency=None):
    """EN -> pivot -> EN. The 2026-08-21 A/B located the accent effect on the
    RETURN leg — a strong translator polishes it away there — so the legs
    take separate models (GH-186): a strong outbound translator buys fidelity
    into the pivot without costing accent, as long as the return leg stays
    weak. model_return defaults to model, keeping single-model calls exact."""
    out_prompt, back_prompt = prompts_for(language)
    mode = "blind"
    if fluency:
        back_prompt = fluency_return_prompt(language, fluency)
        mode = f"fluency={fluency}"
    label = language.strip().title()
    print(f"leg 1: EN -> {label} ({model})", file=sys.stderr)
    mid = run_leg(paras, out_prompt, model)
    print(f"leg 2: {label} -> EN ({mode}, {model_return or model})", file=sys.stderr)
    return run_leg(mid, back_prompt, model_return or model)


def is_prose(p):
    head = p.lstrip()[:2]
    return not (head.startswith("#") or head.startswith(">")
                or head.startswith("!") or head.startswith("|")
                or head.startswith("``") or head.startswith("<"))


def para_gate(orig, rt):
    """Paragraph-level applicability; None when the pair may produce
    candidates, else the failure reason."""
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


def sent_gate(orig, rt, sim):
    """Sentence-level applicability. The length gate is also the split/merge
    guard: a half-translation of a split sentence fails the ratio."""
    if sim < 0.3:
        return "poor-alignment"
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
    for m in QUOTED.finditer(orig):
        span = m.group(1) or m.group(2)
        if span not in rt:
            return "quote-drift"
    return None


def score(orig, rt):
    """Serbian-ness of the candidate: calques dominate, restructuring breaks
    ties. Higher = applied earlier as the dial opens."""
    restructure = 1.0 - difflib.SequenceMatcher(None, orig, rt).ratio()
    return 10.0 * len(CALQUES.findall(rt)) + restructure


def align_sentences(orig_sents, rt_sents):
    """Monotone 1:1 alignment maximizing total similarity (DP). Returns
    [(orig_idx, rt_idx, similarity)]; sentences skipped by the alignment
    (splits/merges) simply produce no pair."""
    n, m = len(orig_sents), len(rt_sents)
    sim = [[difflib.SequenceMatcher(None, a, b).ratio()
            for b in rt_sents] for a in orig_sents]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1],
                           dp[i - 1][j - 1] + sim[i - 1][j - 1])
    pairs, i, j = [], n, m
    while i and j:
        if dp[i][j] == dp[i - 1][j - 1] + sim[i - 1][j - 1] \
                and sim[i - 1][j - 1] > 0:
            pairs.append((i - 1, j - 1, sim[i - 1][j - 1]))
            i, j = i - 1, j - 1
        elif dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


def select_capped(ranked, k, max_per_para):
    """Greedy prefix selection under the per-paragraph cap. Deterministic and
    prefix-monotone: a unit applied at a lower dial stays applied at every
    higher one."""
    applied, per_para = [], {}
    for c in ranked:
        if len(applied) >= k:
            break
        if per_para.get(c["para"], 0) >= max_per_para:
            continue
        applied.append(c)
        per_para[c["para"]] = per_para.get(c["para"], 0) + 1
    return applied


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
    ap.add_argument("--grain", choices=("sentence", "paragraph"),
                    default="sentence",
                    help="unit of change: sentence (dispersed, default) or "
                         "paragraph (GH-69 behavior)")
    ap.add_argument("--max-per-para", type=int, default=2,
                    help="sentence grain: cap of swapped sentences per "
                         "paragraph (the anti-wall mechanism)")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="outbound-leg translator (and return leg unless "
                         "--model-return is given)")
    ap.add_argument("--model-return",
                    default=os.environ.get("ACCENT_DIAL_MODEL_RETURN") or None,
                    help="return-leg translator; the accent is made or "
                         "destroyed on this leg, keep it weak "
                         "(env ACCENT_DIAL_MODEL_RETURN)")
    ap.add_argument("--fluency", choices=sorted(FLUENCY_BANDS),
                    help="return-leg persona band; absent = the blind "
                         "mechanical return leg (today's behavior)")
    ap.add_argument("--fluency-years", type=int,
                    help="immersion years, mapped to a band (<=8 fresh, "
                         "<=22 settled, else native); a bare number in the "
                         "prompt is a measured null, so years only select "
                         "a described band")
    ap.add_argument("--language", default="serbian",
                    help="pivot language for the round trip (default: "
                         "serbian, the only pivot the calque gate is "
                         "calibrated for)")
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
        if args.language.strip().lower() != "serbian":
            print(f"note: pivot '{args.language}' is outside the calque "
                  "gate's calibration — score() ranks by restructuring "
                  "distance alone for this run.", file=sys.stderr)
        fluency = args.fluency
        if fluency is None and args.fluency_years is not None:
            fluency = fluency_band(args.fluency_years)
            print(f"fluency: {args.fluency_years} years -> band '{fluency}'",
                  file=sys.stderr)
        rt = roundtrip(paras, args.model, args.model_return, args.language,
                       fluency)
        with open(rt_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(rt))
        print(f"round-trip cached: {rt_path}", file=sys.stderr)
    if len(rt) != len(paras):
        sys.exit(f"alignment lost: {len(paras)} original vs {len(rt)} "
                 f"round-trip paragraphs — regenerate the cache")

    fails = {}

    def fail(reason):
        fails[reason] = fails.get(reason, 0) + 1

    if args.grain == "paragraph":
        cands = []
        for i, (o, r) in enumerate(zip(paras, rt)):
            why = para_gate(o, r)
            if why:
                fail(why)
            cands.append({"para": i, "gate": why,
                          "score": round(score(o, r), 4) if why is None
                          else None})
        ranked = sorted((c for c in cands if c["gate"] is None),
                        key=lambda c: -c["score"])
        k = round(args.dial * len(ranked))
        chosen = ranked[:k]
        applied_paras = {c["para"] for c in chosen}
        for c in cands:
            c["applied"] = c["para"] in applied_paras
        out_paras = [rt[i] if i in applied_paras else p
                     for i, p in enumerate(paras)]
        n_applied, n_gated, unit = len(chosen), len(ranked), "paragraphs"
    else:
        cands = []
        for i, (o, r) in enumerate(zip(paras, rt)):
            why = para_gate(o, r)
            if why in ("locked-span", "not-prose", "unchanged"):
                fail(why)
                continue  # citation/number/length drift retried per-sentence
            osents, rsents = split_sentences(o), split_sentences(r)
            for oi, ri, sim in align_sentences(osents, rsents):
                why_s = sent_gate(osents[oi], rsents[ri], sim)
                if why_s:
                    fail(why_s)
                cands.append({"para": i, "sent": oi, "rt_sent": ri,
                              "gate": why_s, "sim": round(sim, 3),
                              "score": round(score(osents[oi], rsents[ri]), 4)
                              if why_s is None else None})
        ranked = sorted((c for c in cands if c["gate"] is None),
                        key=lambda c: -c["score"])
        k = round(args.dial * len(ranked))
        chosen = select_capped(ranked, k, args.max_per_para)
        chosen_keys = {(c["para"], c["sent"]) for c in chosen}
        for c in cands:
            c["applied"] = (c["para"], c["sent"]) in chosen_keys
        by_para = {}
        for c in chosen:
            by_para.setdefault(c["para"], []).append(c)
        out_paras = []
        for i, p in enumerate(paras):
            if i not in by_para:
                out_paras.append(p)  # byte-identical passthrough
                continue
            osents = split_sentences(p)
            rsents = split_sentences(rt[i])
            for c in by_para[i]:
                osents[c["sent"]] = rsents[c["rt_sent"]]
            out_paras.append(" ".join(osents))
        n_applied, n_gated, unit = len(chosen), len(ranked), "sentences"

    stem, ext = os.path.splitext(args.article)
    out_path = args.out or f"{stem}.dial{args.dial:g}{ext or '.txt'}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(out_paras) + "\n")

    log = {"article": args.article, "roundtrip": rt_path, "model": args.model,
           "dial": args.dial, "grain": args.grain,
           "max_per_para": args.max_per_para
           if args.grain == "sentence" else None,
           "paragraphs": len(paras), "gated": n_gated, "applied": n_applied,
           "candidates": cands}
    log_path = args.log or out_path + ".log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

    print(f"applied {n_applied}/{n_gated} gated {unit} "
          f"({args.grain} grain, {len(paras)} paragraphs; "
          f"gate failures: {fails})\nout: {out_path}\nlog: {log_path}")


if __name__ == "__main__":
    main()
