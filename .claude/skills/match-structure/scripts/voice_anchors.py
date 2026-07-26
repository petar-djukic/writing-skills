#!/usr/bin/env python3
"""writing-voice/ support for filter-tells: baseline profile and anchor retrieval.

The `writing-voice/` contract is documented in the repository rule of the same
name. This script implements the two mechanical halves:

  discover   walk up from a file to find the repo's writing-voice/ directory
  profile    build a style profile over the exemplars (cached, mtime-keyed) so
             detect-structural.py --voice-profile can report distances from
             the author's own register instead of only fixed thresholds
  anchors    retrieve the top-k topically nearest exemplar PASSAGES for a
             passage, to inject into rewrite/overshoot prompts as voice anchors

Retrieval is tf-idf cosine over paragraph-level passages — stdlib only, no
embeddings dependency. author-voice exemplars are preferred; venue-voice fills
in when the author has no near passage.

Profile computation reuses match-structure's style.py (imported from the sibling
skill directory, which is present in every mirrored surface) rather than
duplicating the metric definitions.

Usage:
  voice_anchors.py discover <file>
  voice_anchors.py profile [--voice-dir D | --for <file>] [--force]
  voice_anchors.py anchors --text <file>|- [--voice-dir D | --for <file>]
                           [-k 3] [--role author-voice]
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (pixi env supplies it).")

CACHE_NAME = ".voice-profile.json"
_WORD = re.compile(r"[a-z][a-z'-]+")
_STOP = set("""
the a an and or but if then than that this these those of in on at by for with
from to into over under is are was were be been being it its as not no so such
we our you your they their he she his her i me my which who whom whose what
when where while because although though can could may might must shall should
will would do does did done have has had having there here how why also more
most other some any each every both few many much own same too very just
""".split())


# --- discovery ---------------------------------------------------------------

def discover(start_path: str):
    """Walk up from a file (or dir) looking for writing-voice/. None if absent."""
    d = os.path.abspath(start_path)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        cand = os.path.join(d, "writing-voice")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_manifest(voice_dir: str):
    path = os.path.join(voice_dir, "manifest.yaml")
    if not os.path.exists(path):
        return []
    data = yaml.safe_load(open(path)) or {}
    return data.get("exemplars") or []


# Prose written once generative AI was widely available may carry AI diction,
# which makes it circular as a diction anchor. The default boundary; a manifest
# that states `pre_ai` per exemplar overrides it, because where the line falls
# for a given piece is the curator's knowledge, not arithmetic.
AI_ERA_YEAR = 2022


def is_pre_ai(ex: dict) -> bool:
    """Whether an exemplar is safe to anchor DICTION on.

    Explicit `pre_ai` wins: a curator may know a 2023 piece was drafted before
    they had model access, or that a 2021 piece was not. Absent, fall back to
    the year, and treat an undated sample as pre-AI — the corpora that predate
    this field are pre-AI by construction.
    """
    if "pre_ai" in ex:
        return bool(ex["pre_ai"])
    y = ex.get("year")
    return True if not isinstance(y, int) else y < AI_ERA_YEAR


def sample_paths(voice_dir: str, role: str = None, pre_ai: bool = None):
    """[(path, role)] for manifest exemplars whose file exists.

    pre_ai=True restricts to diction-safe samples ACROSS roles, which is the
    distinction role alone cannot express: the pre-AI punch anchors are
    venue-voice, and so are the AI-era samples that must never anchor diction
    (GH-217).
    """
    out = []
    for ex in load_manifest(voice_dir):
        if role and ex.get("role") != role:
            continue
        if pre_ai is not None and is_pre_ai(ex) != pre_ai:
            continue
        p = os.path.join(voice_dir, ex.get("file", ""))
        if os.path.exists(p):
            out.append((p, ex.get("role", "?")))
    return out


# --- baseline profile --------------------------------------------------------

def _style_module(script_dir: str):
    """Import style.py — same skill since GH-196 (anchors are profile work).

    Every agent surface carries the full skill set, so this relative sibling
    path resolves wherever the skill is installed.
    """
    sibling = os.path.normpath(
        os.path.join(script_dir))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import style  # noqa: F401
        return style
    except ImportError as e:
        sys.exit(f"could not import match-structure style.py from {sibling}: {e}")


def _fingerprint(paths):
    return {os.path.basename(p): int(os.path.getmtime(p)) for p, _ in paths}


def build_profile(voice_dir: str, force: bool = False):
    """Aggregate style profile over the exemplars, cached on sample mtimes."""
    paths = sample_paths(voice_dir)
    if not paths:
        return None, "no exemplars found in manifest"
    cache_path = os.path.join(voice_dir, CACHE_NAME)
    fp = _fingerprint(paths)
    if not force and os.path.exists(cache_path):
        try:
            cached = json.load(open(cache_path))
            if cached.get("_samples") == fp:
                return cached, "cached"
        except (OSError, json.JSONDecodeError):
            pass
    style = _style_module(os.path.dirname(os.path.abspath(__file__)))
    profiles = [style.profile_file(p) for p, _ in paths]
    profile = style.aggregate(profiles)
    profile["_samples"] = fp
    profile["_source"] = "writing-voice"
    with open(cache_path, "w") as f:
        json.dump(profile, f, indent=2)
    return profile, "built"


# --- anchor retrieval (tf-idf over paragraph passages) -----------------------

def _passages(path, min_words=40, max_words=220):
    """Prose paragraphs of a sample, skipping headings/lists/code."""
    text = open(path, encoding="utf-8", errors="replace").read()
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    out = []
    for para in re.split(r"\n\s*\n", text):
        p = " ".join(para.split())
        if not p or p.startswith(("#", "|", ">", "-", "*", "!")):
            continue
        n = len(p.split())
        if n < min_words:
            continue
        out.append(" ".join(p.split()[:max_words]))
    return out


def _tokens(s):
    return [w for w in _WORD.findall(s.lower()) if w not in _STOP and len(w) > 2]


def _tfidf_vectors(docs):
    tfs = [Counter(_tokens(d)) for d in docs]
    df = Counter()
    for tf in tfs:
        df.update(tf.keys())
    n = len(docs) or 1
    vecs = []
    for tf in tfs:
        total = sum(tf.values()) or 1
        vecs.append({w: (c / total) * math.log((1 + n) / (1 + df[w]) + 1)
                     for w, c in tf.items()})
    return vecs, df, n


def _cos(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[w] * b[w] for w in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


# How much an author-voice passage outranks a venue-voice one at equal
# similarity. A weight, not a partition: the previous sort key put role first
# in the tuple, so EVERY author-voice passage beat EVERY venue-voice passage
# regardless of score. Measured consequence (GH-216): for "Let the orchestrator
# run git, not the agents." the five nearest passages were Yegge at ~0.23 and
# the ranker returned Djukic papers at ~0.07 — it found the right anchors and
# discarded them, then the model faithfully reproduced the IEEE register it was
# shown.
#
# 1.5 keeps the original intent — with comparable scores the author's own prose
# wins, because it is the better diction target when it fits — while letting a
# passage substantially nearer the draft win on merit. The constant is a
# judgment, not a measurement; the tests pin both directions so it cannot
# silently become a partition again.
AUTHOR_VOICE_WEIGHT = 1.5


def anchors(voice_dir: str, passage: str, k: int = 3, role: str = None,
            pre_ai: bool = None):
    """Top-k exemplar passages most topically similar to `passage`.

    author-voice is weighted, not privileged absolutely: at comparable
    similarity it wins, but a clearly nearer venue-voice passage outranks it.
    An explicit `role` still filters hard.

    Each returned anchor carries its `score`, its `weighted` score, and its
    `role`, so an inappropriate mix is visible in the output rather than
    something an operator has to re-derive by hand.
    """
    cands = []
    for path, r in sample_paths(voice_dir, role=role, pre_ai=pre_ai):
        for p in _passages(path):
            cands.append({"file": os.path.basename(path), "role": r, "text": p})
    if not cands:
        return []
    vecs, df, n = _tfidf_vectors([c["text"] for c in cands])
    q_tf = Counter(_tokens(passage))
    total = sum(q_tf.values()) or 1
    qv = {w: (c / total) * math.log((1 + n) / (1 + df[w]) + 1)
          for w, c in q_tf.items()}
    for c, v in zip(cands, vecs):
        c["score"] = round(_cos(qv, v), 4)
        c["weighted"] = round(
            c["score"] * (AUTHOR_VOICE_WEIGHT if c["role"] == "author-voice" else 1.0), 4)
    cands.sort(key=lambda c: c["weighted"], reverse=True)
    return [c for c in cands[:k] if c["score"] > 0]


# --- cli ---------------------------------------------------------------------

def _resolve_dir(args):
    if getattr(args, "voice_dir", None):
        return args.voice_dir
    ref = getattr(args, "for_file", None) or os.getcwd()
    d = discover(ref)
    if not d:
        sys.exit(f"no writing-voice/ found from {ref} (voice features are optional)")
    return d


def cmd_discover(args):
    d = discover(args.file)
    print(json.dumps({"file": args.file, "writing_voice": d,
                      "exemplars": len(load_manifest(d)) if d else 0}, indent=2))
    sys.exit(0 if d else 1)


def cmd_profile(args):
    d = _resolve_dir(args)
    profile, how = build_profile(d, force=args.force)
    if not profile:
        sys.exit(how)
    print(json.dumps({"writing_voice": d, "status": how,
                      "cache": os.path.join(d, CACHE_NAME),
                      "papers": profile.get("papers"),
                      "metrics": profile.get("metrics")}, indent=2))


def cmd_anchors(args):
    d = _resolve_dir(args)
    text = sys.stdin.read() if args.text == "-" else open(args.text).read()
    got = anchors(d, text, k=args.k, role=args.role,
                  pre_ai=(True if args.stratum == "pre-ai"
                          else False if args.stratum == "ai-era" else None))
    print(json.dumps({"writing_voice": d, "k": args.k, "anchors": got},
                     indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="writing-voice support for filter-tells")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="find writing-voice/ from a file")
    d.add_argument("file")
    d.set_defaults(func=cmd_discover)

    pr = sub.add_parser("profile", help="build/refresh the baseline profile")
    pr.add_argument("--voice-dir")
    pr.add_argument("--for", dest="for_file", help="discover from this file")
    pr.add_argument("--force", action="store_true", help="ignore the cache")
    pr.set_defaults(func=cmd_profile)

    an = sub.add_parser("anchors", help="top-k nearest exemplar passages")
    an.add_argument("--text", required=True, help="file with the passage, or -")
    an.add_argument("--voice-dir")
    an.add_argument("--for", dest="for_file")
    an.add_argument("-k", type=int, default=3)
    an.add_argument("--role", choices=["author-voice", "venue-voice"])
    an.add_argument("--stratum", choices=["pre-ai", "ai-era"],
                    help="pre-ai restricts to diction-safe samples across roles")
    an.set_defaults(func=cmd_anchors)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
