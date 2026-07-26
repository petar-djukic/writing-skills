#!/usr/bin/env python3
"""Count the register markers that separate assistant prose from a voice.

Four counts per 1,000 words, chosen because they moved together in the GH-220
measurement — the AI draft, a faithful rules-based tightening of a rewrite, and
the draft again all landed within a tenth of a point of each other on these:

  passive       be-verb + past participle ("is executed", "was noted")
  agentive      the passive with its actor attached ("is executed by the...")
  nominalization  -tion/-ment/-ance/... nouns burying a verb
  connectives   sentence-initial However/Therefore/Moreover/Furthermore/...

A fifth is reported beside them but is not one of the four:

  filler        just/actually/really/basically/... — the OTHER machine register,
                the one a rewrite lands in when it stops sounding corporate
                (GH-233). Judged by movement against the document's own earlier
                rate, never by level: published human essays run 2.1-15.6 per
                500 words, so a threshold that catches a regression to 2.8 also
                condemns the whole anchor corpus. It stays out of distance() so
                the calibrated four-axis statistic keeps meaning what it meant.

Cheap, offline, deterministic. This is the local half of "did the pass move
toward the assistant register" — the half that costs nothing per look, unlike a
detector scan. A falling AI score with these rising is the GH-219/GH-220
failure mode, and printing them together is what makes it visible.

Usage:
  register_markers.py <file.md|file.tex> [more files ...] [--json]
  register_markers.py --compare <before> <after> [--json]

Library: markers(text) -> dict. Stdlib only.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Irregular past participles that the -ed/-en suffix pattern misses.
_IRREGULAR = ("done|made|given|taken|shown|seen|known|held|kept|left|set|put|"
              "run|built|sent|found|brought|thought|caught|taught|bought|"
              "written|driven|chosen|drawn|grown|thrown|broken|spoken|stolen|"
              "hidden|forbidden|understood|read|said|paid|laid|meant|led|fed|"
              "lost|won|begun|sung|hung|struck|split|spread|cut|hit|let")
_BE = r"(?:is|are|was|were|be|been|being)"
PASSIVE = re.compile(
    rf"\b{_BE}\s+(?:\w+ly\s+)?(?:\w+(?:ed|en)|{_IRREGULAR})\b", re.IGNORECASE)
AGENTIVE = re.compile(
    rf"\b{_BE}\s+(?:\w+ly\s+)?(?:\w+(?:ed|en)|{_IRREGULAR})\s+by\s+(?:the|a|an|its?|their|our|me|us|you|him|her|them)\b",
    re.IGNORECASE)
# -al nominalizations are listed, not suffix-matched: the suffix alone would
# sweep in every adjective (structural, general, formal).
_AL_NOMS = ("removal|approval|denial|refusal|arrival|proposal|disposal|"
            "withdrawal|dismissal|retrieval|renewal|reversal|rehearsal")
NOMINALIZATION = re.compile(
    rf"\b(?:\w{{4,}}(?:tion|tions|ment|ments|ance|ances|ence|ences|ity|ities|ness|ism|isms)|{_AL_NOMS})\b",
    re.IGNORECASE)
CONNECTIVE = re.compile(
    r"(?:^|[.!?]\s+)(However|Therefore|Moreover|Furthermore|Additionally|"
    r"Consequently|Nevertheless|Nonetheless|Thus|Hence)\b,?", re.MULTILINE)
# Conversational filler: the register a rewrite lands in once it stops sounding
# corporate (GH-233). Counted as a rate for the same reason the lexical scan
# does not denylist these — the author's own prose carries them, so only the
# rate distinguishes a voice from a machine imitating one. Kept in step with
# CONVERSATIONAL_FILLER in filter-tells/scripts/detect-lexical.sh.
FILLER = re.compile(
    r"\b(?:just|actually|really|basically|simply|honestly|literally|"
    r"pretty much|kind of|sort of|a bit)\b", re.IGNORECASE)
# Filler is judged by MOVEMENT, not level. Calibration refused an absolute
# threshold (GH-233): the reference venue-voice corpus — Dan Luu, Evans,
# Krugman, Rands, Yegge — runs 2.1 to 15.6 filler per 500 words in published
# human essays, while this repository's documentation runs 0.0 to 1.7 and the
# author's own articles 0.2 to 0.3. A level tells you which register a document
# is in; it cannot tell you whether the document got worse. A rewrite that took
# one article from 0.3 to 2.8 and another from 0.2 to 6.8 did get worse, and
# both are still inside the essay corpus's ordinary range.
#
# So: flag a rise by this factor over the document's own earlier rate, once the
# rate clears a floor. The floor keeps 0.05 -> 0.2 from reading as a 4x
# regression when both numbers are noise.
FILLER_RISE_FACTOR = 2.0
FILLER_RISE_FLOOR = 1.0

# Not passives: adjectival "is interested/concerned/..." would inflate the
# count on ordinary prose. Small list, held to clear cases.
_ADJECTIVAL = re.compile(
    rf"\b{_BE}\s+(?:interested|concerned|worried|pleased|surprised|excited|"
    rf"tired|satisfied|confused|involved|related|limited|based|used to)\b",
    re.IGNORECASE)


def _prose(path):
    """Prose view via the shared extractor; .tex through detex."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.endswith(".tex"):
        import detex
        text = "\n".join(detex.detex_aligned(text))
    import md_paragraphs
    return "\n\n".join(p[2] for p in md_paragraphs.parse(text).paragraphs)


def markers(text):
    """The four counts, absolute and per 1,000 words."""
    words = len(text.split())
    passive = len(PASSIVE.findall(text)) - len(_ADJECTIVAL.findall(text))
    counts = {
        "passive": max(0, passive),
        "agentive": len(AGENTIVE.findall(text)),
        "nominalization": len(NOMINALIZATION.findall(text)),
        "connectives": len(CONNECTIVE.findall(text)),
        "filler": len(FILLER.findall(text)),
    }
    per_1000 = {k: round(v / words * 1000, 1) if words else 0.0
                for k, v in counts.items()}
    # Filler is also reported per 500 words, because that is the unit the
    # lexical scan gates on and two units for one number invites a mistake.
    per_500_filler = (round(counts["filler"] / words * 500, 1) if words else 0.0)
    return {"words": words, "counts": counts, "per_1000": per_1000,
            "filler_per_500": per_500_filler}


def filler_regressed(before, after):
    """Did filler rise enough, from a high enough base, to call it a regression?

    The pair (factor, floor) is the whole judgment. 0.3 -> 2.8 is a regression;
    3.8 -> 4.0 in an essay that was always chatty is not; 0.05 -> 0.2 is noise
    doubling and must not read as a 4x collapse.
    """
    b, a = before["filler_per_500"], after["filler_per_500"]
    return bool(a >= FILLER_RISE_FLOOR and b * FILLER_RISE_FACTOR < a)


def markers_file(path):
    return markers(_prose(path))


# Typical magnitudes differ by an order of magnitude between markers, so a raw
# Euclidean distance is really a nominalization distance. Scaling by these puts
# each axis on comparable footing. Measured across the reference corpora:
# nominalization runs 20-90 per 1000 words, passive 2-20, the rest 0-5.
_SCALE = {"passive": 10.0, "agentive": 3.0, "nominalization": 40.0,
          "connectives": 3.0}


def distance(a, b, scaled=True):
    """Distance between two per_1000 vectors (larger = farther apart).

    Scaled by default. Unscaled, this statistic is dominated by whichever
    marker carries the biggest absolute number: in the GH-229 A/B it reported
    the similarity arm as closer to the author's original while that arm had
    nearly DOUBLED the passive rate and the tag arm had held it — the verdict
    came entirely from nominalization noise an order of magnitude larger.

    Filler is reported but deliberately NOT an axis here. These four were
    chosen because they moved together in one measurement, and the scale
    constants are calibrated to that set; adding a fifth axis would silently
    change every distance this function has ever reported, including the ones
    quoted in GH-229. Filler is gated in the lexical scan and shown in the
    comparison instead.
    """
    keys = ("passive", "agentive", "nominalization", "connectives")
    return round(sum(((a["per_1000"][k] - b["per_1000"][k])
                      / (_SCALE[k] if scaled else 1.0)) ** 2
                     for k in keys) ** 0.5, 3)


def _print_one(path, m):
    p = m["per_1000"]
    print(f"{path}: {m['words']} words")
    for k in ("passive", "agentive", "nominalization", "connectives", "filler"):
        print(f"  {k:15} {p[k]:6}   ({m['counts'][k]})")
    print(f"  {'filler/500w':15} {m['filler_per_500']:6}   "
          f"(level only; movement is what is judged)")


def main():
    ap = argparse.ArgumentParser(description="register markers per 1,000 words")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.compare:
        b, c = (markers_file(p) for p in a.compare)
        if a.json:
            print(json.dumps({"before": b, "after": c,
                              "distance": distance(b, c),
                              "filler_regressed": filler_regressed(b, c)},
                             indent=2))
            return
        print(f"register markers per 1,000 words "
              f"({a.compare[0]} -> {a.compare[1]}):")
        worse = []
        for k in ("passive", "agentive", "nominalization", "connectives",
                  "filler"):
            bv, cv = b["per_1000"][k], c["per_1000"][k]
            up = cv > bv
            print(f"  {k:15} {bv:6} -> {cv:<6}{'  UP' if up else ''}")
            if up:
                worse.append(k)
        # Movement, in the unit the lexical scan reports. This is the filler
        # instrument: a level cannot separate essay register from a regression.
        bf, cf = b["filler_per_500"], c["filler_per_500"]
        reg = filler_regressed(b, c)
        print(f"  {'filler/500w':15} {bf:6} -> {cf:<6}"
              f"{'  REGRESSED' if reg else ''}")
        if reg:
            worse.append("filler")
        print(f"  distance: {distance(b, c)}")
        if worse:
            print("  Rising markers mean movement TOWARD the assistant "
                  "register — the direction a falling AI score can hide.",
                  file=sys.stderr)
        return

    if not a.files:
        ap.error("give files, or --compare BEFORE AFTER")
    out = {}
    for p in a.files:
        m = markers_file(p)
        out[p] = m
        if not a.json:
            _print_one(p, m)
    if a.json:
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
