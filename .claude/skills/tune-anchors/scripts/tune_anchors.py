#!/usr/bin/env python3
"""tune-anchors: sweep anchor selections and report the selection rule.

Three commands:
  sweep   run match-voice over (article × arm) pairs, tighten, record markers
  rank    score arms on the register composite, emit blind manifest
  verify  scan top K with Pangram, record detector results

Pipeline per trial (full sweep):
  1. drive.py  — voice rewrite via anchor-selected passages
  2. tighten.py — remove AI-register artifacts (same model family)
  3. measure   — register markers on the tightened output

Usage:
  tune_anchors.py sweep --voice-dir D --articles a.md,b.md \
                        --arms "tags~clipped","role=venue-voice" \
                        [--n 24] [--model gemma4:12b] [--out ledger.yaml] \
                        [--dry-run] [--no-tighten]
  tune_anchors.py rank  --ledger ledger.yaml [--blind]
  tune_anchors.py verify --ledger ledger.yaml --top 3 [--budget 10]
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
MATCH_VOICE = os.path.normpath(os.path.join(HERE, "..", "..", "match-voice", "scripts"))
TIGHTEN = os.path.normpath(os.path.join(HERE, "..", "..", "tighten-style", "scripts"))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
STYLO = os.path.normpath(os.path.join(HERE, "..", "..", "match-structure", "scripts"))

sys.path.insert(0, HERE)
import ledger  # noqa: E402


def _voice_anchors():
    if STYLO not in sys.path:
        sys.path.insert(0, STYLO)
    try:
        import voice_anchors
        return voice_anchors
    except ImportError as e:
        sys.exit(f"could not import voice_anchors from {STYLO}: {e}")


def _register_markers():
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    try:
        import register_markers
        return register_markers
    except ImportError as e:
        sys.exit(f"could not import register_markers from {SHARED}: {e}")


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace", **kw)


def _extract_markers(rm, path):
    """Extract register markers from a draft file into the ledger format.

    Returns a flat dict with keys matching _RANK_KEYS plus filler_per_500.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    m = rm.markers(text)
    p = m["per_1000"]
    return {
        "passive_per_1k": round(p["passive"], 2),
        "agentive_per_1k": round(p["agentive"], 2),
        "nominalization_per_1k": round(p["nominalization"], 2),
        "connectives_per_1k": round(p["connectives"], 2),
        "filler_per_500": round(m["filler_per_500"], 2),
    }


# --- sweep -------------------------------------------------------------------

def _sweep_dry_run(voice_dir, articles, arms, k, out_path):
    """Retrieval-only sweep: no model, no cost. Shows what anchors WOULD be
    selected for each (article, arm) pair."""
    va = _voice_anchors()
    lg = ledger.Ledger.load(out_path) if out_path else ledger.Ledger()

    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    try:
        import prose_document as pd
    except ImportError as e:
        sys.exit(f"could not import prose_document from {SHARED}: {e}")

    for art_path in articles:
        art_path = os.path.abspath(art_path)
        if not os.path.exists(art_path):
            print(f"skip {art_path}: not found", file=sys.stderr)
            continue
        doc = pd.ProseDocument.open(art_path)
        r = doc.to_parse_result()
        paras = [p for _s, _e, p in r.paragraphs if len(p.split()) >= 12]
        if not paras:
            print(f"skip {art_path}: no rewritable paragraphs")
            continue

        for arm_label, kwargs in arms:
            paths = va.sample_paths(voice_dir, **kwargs)
            pool_size = len(paths)
            if not paths:
                print(f"  {arm_label}: EMPTY POOL — skipping")
                continue

            from collections import Counter
            roles, sources, total_anchors = Counter(), Counter(), 0
            for txt in paras:
                got = va.anchors(voice_dir, txt, k=k, **kwargs)
                for a in got:
                    roles[a.get("role", "?")] += 1
                    sources[a.get("file", "?")] += 1
                    total_anchors += 1

            trial = ledger.Trial(
                article=os.path.basename(art_path),
                arm=arm_label,
                model=None,
                dry_run=True,
                anchor_count=total_anchors,
                pool_size=pool_size,
            )
            lg.append(trial)

            top = ", ".join(f"{f} x{n}" for f, n in sources.most_common(3))
            print(f"  {os.path.basename(art_path)} × {arm_label}:")
            print(f"    pool {pool_size}, anchors selected {total_anchors} "
                  f"over {len(paras)} paragraphs")
            print(f"    roles {dict(roles)}")
            print(f"    top sources: {top}")

    if out_path:
        lg.save(out_path)
        print(f"\nledger: {out_path} ({len(lg.trials)} trials)")


def _sweep_full(voice_dir, articles, arms, n, model, out_path, tighten,
                sent_floor=None):
    """Full sweep: runs drive.py then tighten.py per (article, arm), captures
    register markers and structural metrics. Requires Ollama."""
    rm = _register_markers()
    lg = ledger.Ledger.load(out_path) if out_path else ledger.Ledger()

    drive_py = os.path.join(MATCH_VOICE, "drive.py")
    if not os.path.exists(drive_py):
        sys.exit(f"drive.py not found at {drive_py}")

    tighten_py = os.path.join(TIGHTEN, "tighten.py")
    if tighten and not os.path.exists(tighten_py):
        sys.exit(f"tighten.py not found at {tighten_py}")

    structural_py = os.path.normpath(os.path.join(
        HERE, "..", "..", "filter-tells", "scripts", "detect-structural.py"))

    for art_path in articles:
        art_path = os.path.abspath(art_path)
        if not os.path.exists(art_path):
            print(f"skip {art_path}: not found", file=sys.stderr)
            continue

        for arm_label, kwargs in arms:
            print(f"\n--- {os.path.basename(art_path)} × {arm_label} ---")
            cmd = [sys.executable, drive_py, "--article", art_path,
                   "--model", model]
            if "role" in kwargs:
                cmd += ["--role", kwargs["role"]]
            if "tags" in kwargs:
                cmd += ["--anchor-tags", ",".join(kwargs["tags"])]
            if kwargs.get("pre_ai") is True:
                cmd += ["--stratum", "pre-ai"]
            elif kwargs.get("pre_ai") is False:
                cmd += ["--stratum", "ai-era"]
            cmd += ["--voice-dir", voice_dir]

            r = _run(cmd)
            if r.returncode != 0:
                print(f"  drive.py failed: {(r.stderr or r.stdout)[:300]}",
                      file=sys.stderr)
                continue
            print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)

            # The voice draft is the input to tighten
            draft = art_path.replace(".md", ".vr-draft.md")
            if not os.path.exists(draft):
                print(f"  no draft produced — skipping", file=sys.stderr)
                continue

            # Run tighten on the voice draft
            tightened = False
            if tighten:
                tight_out = draft.replace(".md", ".tight.md")
                tcmd = [sys.executable, tighten_py, "--article", draft,
                        "--model", model, "--out", tight_out]
                if sent_floor:
                    tcmd += ["--sent-floor", str(sent_floor[0]),
                             str(sent_floor[1])]
                tr = _run(tcmd)
                if tr.returncode == 0 and os.path.exists(tight_out):
                    draft = tight_out
                    tightened = True
                    print(f"  tightened: {os.path.basename(tight_out)}")
                    if tr.stdout.strip():
                        lines = tr.stdout.strip().split("\n")
                        for line in lines[-6:]:
                            print(f"    {line}")
                else:
                    print(f"  tighten failed (using voice draft): "
                          f"{(tr.stderr or tr.stdout)[:200]}",
                          file=sys.stderr)

            # Capture register markers from the final draft
            reg = _extract_markers(rm, draft)

            # Capture structural metrics
            struct = {}
            if os.path.exists(structural_py):
                sr = _run([sys.executable, structural_py, draft, "--json"])
                if sr.returncode in (0, 1) and sr.stdout.strip():
                    try:
                        data = json.loads(sr.stdout)
                        rec = data[0] if isinstance(data, list) else data
                        sm = (rec or {}).get("metrics", {})
                        for k in ("sentence_length_std", "dash_density_per_500w",
                                  "contrast_flip_per_500w"):
                            if sm.get(k) is not None:
                                struct[k] = round(sm[k], 2)
                    except (json.JSONDecodeError, IndexError, TypeError):
                        pass

            # Preserve the draft under a unique name (GH-254).
            import hashlib, shutil
            drafts_dir = os.path.join(os.path.dirname(out_path or "ledger.yaml"), "drafts")
            os.makedirs(drafts_dir, exist_ok=True)
            art_stem = os.path.splitext(os.path.basename(art_path))[0]
            arm_hash = hashlib.sha256(arm_label.encode()).hexdigest()[:8]
            dest = os.path.join(drafts_dir, f"{art_stem}-{arm_hash}.md")
            shutil.copy2(draft, dest)
            saved_draft = dest
            print(f"  draft saved: {dest}")

            va = _voice_anchors()
            pool_size = len(va.sample_paths(voice_dir, **kwargs))
            trial = ledger.Trial(
                article=os.path.basename(art_path),
                arm=arm_label,
                model=model,
                dry_run=False,
                anchor_count=0,
                pool_size=pool_size,
                register_markers=reg,
                structural_metrics=struct,
                draft_path=saved_draft,
                tightened=tightened,
            )
            lg.append(trial)

    if out_path:
        lg.save(out_path)
        print(f"\nledger: {out_path} ({len(lg.trials)} trials)")


def cmd_sweep(args):
    va = _voice_anchors()
    voice_dir = args.voice_dir
    if not voice_dir:
        voice_dir = va.discover(args.articles[0] if args.articles else os.getcwd())
    if not voice_dir or not os.path.isdir(voice_dir):
        sys.exit("no writing-voice/ found — tune-anchors requires a corpus")

    arms = ledger.parse_arms(args.arms)
    if not arms:
        sys.exit("no arms specified")

    articles = []
    for a in args.articles:
        if os.path.isdir(a):
            for root, _, files in os.walk(a):
                articles += [os.path.join(root, f) for f in files
                             if f.endswith(".md") and not f.startswith(".")]
        else:
            articles.append(a)
    if not articles:
        sys.exit("no articles specified")

    out_path = args.out or "ledger.yaml"
    tighten = not args.no_tighten
    print(f"sweep: {len(articles)} articles × {len(arms)} arms"
          f"{' (dry-run)' if args.dry_run else ''}"
          f"{' (no-tighten)' if not tighten else ''}")
    print(f"voice-dir: {voice_dir}\n")

    if args.dry_run:
        _sweep_dry_run(voice_dir, articles, arms, args.k, out_path)
    else:
        _sweep_full(voice_dir, articles, arms, args.n, args.model, out_path,
                    tighten, sent_floor=args.sent_floor)


# --- rank --------------------------------------------------------------------

_RANK_KEYS = ("passive_per_1k", "agentive_per_1k",
              "nominalization_per_1k", "connectives_per_1k")
_RANK_SCALE = {"passive_per_1k": 10.0, "agentive_per_1k": 3.0,
               "nominalization_per_1k": 40.0, "connectives_per_1k": 3.0}


def _register_magnitude(markers_dict):
    """Scaled Euclidean distance from zero — how far toward assistant register.

    Uses the same scale factors as register_markers.distance() so the axes
    contribute comparably. Lower = closer to human-only prose.
    """
    return round(sum((markers_dict.get(k, 0.0) / _RANK_SCALE[k]) ** 2
                     for k in _RANK_KEYS) ** 0.5, 3)


def cmd_rank(args):
    lg = ledger.Ledger.load(args.ledger)
    if not lg.trials:
        sys.exit("ledger is empty")

    results = []
    for arm_label in lg.arms():
        trials = lg.trials_for_arm(arm_label)
        full_trials = [t for t in trials if not t.dry_run and t.register_markers]
        if not full_trials:
            continue
        distances = []
        fillers = []
        detectors = []
        for t in full_trials:
            d = _register_magnitude(t.register_markers)
            distances.append(d)
            fillers.append(t.register_markers.get("filler_per_500", 0.0))
            if t.detector_result is not None:
                detectors.append(t.detector_result)
        median_d = sorted(distances)[len(distances) // 2]
        median_f = sorted(fillers)[len(fillers) // 2]
        median_det = (sorted(detectors)[len(detectors) // 2]
                      if detectors else None)
        results.append({
            "arm": arm_label,
            "trials": len(full_trials),
            "median_distance": round(median_d, 3),
            "median_filler": round(median_f, 2),
            "median_detector": round(median_det, 1) if median_det is not None else None,
        })

    results.sort(key=lambda r: r["median_distance"])

    if args.blind:
        import hashlib
        import random
        random.shuffle(results)
        for r in results:
            h = hashlib.sha256(r["arm"].encode()).hexdigest()[:8]
            r["label"] = h
            del r["arm"]

    print(f"rank: {len(results)} arms with full trials\n")
    for i, r in enumerate(results, 1):
        label = r.get("label", r.get("arm"))
        det = f"  detector {r['median_detector']}%" if r.get("median_detector") is not None else ""
        print(f"  {i}. {label}  distance={r['median_distance']}  "
              f"filler={r['median_filler']}/500w{det}  "
              f"({r['trials']} trials)")
        # Disagreement: low distance but high detector
        if (r.get("median_detector") is not None and
                r["median_distance"] < 1.0 and r["median_detector"] > 50):
            print(f"     WARNING: low register distance but high detector "
                  f"score — signals disagree")
        # Disagreement: high distance but low detector
        if (r.get("median_detector") is not None and
                r["median_distance"] > 2.0 and r["median_detector"] < 20):
            print(f"     WARNING: high register distance but low detector "
                  f"score — signals disagree")

    if not args.blind and results:
        print(f"\nbest arm: {results[0]['arm']}")


# --- verify ------------------------------------------------------------------

def cmd_verify(args):
    lg = ledger.Ledger.load(args.ledger)
    if not lg.trials:
        sys.exit("ledger is empty")

    # Count how many scans we need
    full_trials = [t for t in lg.trials
                   if not t.dry_run and t.detector_result is None]
    # Sort by register magnitude to pick the "top" (best) arms
    scored = []
    for t in full_trials:
        if t.register_markers:
            d = _register_magnitude(t.register_markers)
            scored.append((d, t))
    scored.sort(key=lambda x: x[0])
    to_scan = scored[:args.top]

    # Budget guard
    scans_needed = len(to_scan)
    if scans_needed > args.budget:
        sys.exit(f"verify needs {scans_needed} scans but budget is {args.budget} — "
                 f"raise --budget or lower --top")
    if scans_needed == 0:
        print("verify: nothing to scan (all trials already have detector results "
              "or no full trials exist)")
        return

    print(f"verify: scanning {scans_needed} drafts (budget {args.budget})")

    pangram_py = os.path.join(SHARED, "pangram.py")
    if not os.path.exists(pangram_py):
        sys.exit(f"pangram.py not found at {pangram_py}")

    for _dist, trial in to_scan:
        print(f"  scanning {trial.article} × {trial.arm}...")
        if not trial.draft_path or not os.path.exists(trial.draft_path):
            print(f"    SKIP — no draft file (re-run sweep to generate one)")
            continue
        r = _run([sys.executable, pangram_py, "--text", trial.draft_path, "--json"])
        if r.returncode != 0 or not r.stdout.strip():
            print(f"    scan failed: {(r.stderr or 'no response').strip()[:200]}")
            continue
        try:
            result = json.loads(r.stdout)
            fraction = result.get("fraction_ai")
            if fraction is not None:
                trial.detector_result = round(fraction * 100, 1)
                print(f"    AI: {trial.detector_result}%")
        except (json.JSONDecodeError, TypeError):
            print(f"    could not parse response")

    if args.ledger:
        lg.save(args.ledger)
        print(f"\nledger updated: {args.ledger}")


# --- main --------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="tune-anchors: sweep and rank anchor selections")
    sub = p.add_subparsers(dest="cmd", required=True)

    sw = sub.add_parser("sweep", help="run match-voice over (article × arm) pairs")
    sw.add_argument("--voice-dir", help="writing-voice/ directory")
    sw.add_argument("--articles", required=True, nargs="+",
                    help="article paths or directories")
    sw.add_argument("--arms", required=True, nargs="+",
                    help="arm expressions (role=X, pre_ai=X, tags~X)")
    sw.add_argument("--n", type=int, default=24,
                    help="sample pool to this size for comparability")
    sw.add_argument("-k", type=int, default=3,
                    help="anchors per paragraph (dry-run mode)")
    # TUNE_ANCHORS_MODEL, not MATCH_VOICE_MODEL: the borrowed env var meant
    # configuring match-voice silently reconfigured sweeps here — and sweep
    # verdicts rank anchors under whatever model this resolves to, so it must
    # follow the pipeline default (GH-198). Cohere is a hosted API: every
    # sweep arm bills per token. gemma4:12b is the keyless/local fallback.
    sw.add_argument("--model", default=os.environ.get(
        "TUNE_ANCHORS_MODEL", "cohere:command-a-03-2025"),
        help="rewrite model for sweep arms (env TUNE_ANCHORS_MODEL; hosted "
             "Cohere default bills per arm — gemma4:12b for a free local sweep)")
    sw.add_argument("--out", help="ledger path (default: ledger.yaml)")
    sw.add_argument("--dry-run", action="store_true",
                    help="retrieval only — no model, no cost")
    sw.add_argument("--no-tighten", action="store_true",
                    help="skip the tighten step (rank on raw voice draft)")
    sw.add_argument("--sent-floor", nargs=2, type=float, metavar=("MEAN", "SD"),
                    help="pass --sent-floor to tighten.py (minimum sentence stats)")
    sw.set_defaults(func=cmd_sweep)

    rk = sub.add_parser("rank", help="score arms on register composite")
    rk.add_argument("--ledger", required=True, help="ledger.yaml path")
    rk.add_argument("--blind", action="store_true",
                    help="hash-label arms, shuffle for blind judging")
    rk.set_defaults(func=cmd_rank)

    vr = sub.add_parser("verify", help="scan top K with Pangram")
    vr.add_argument("--ledger", required=True, help="ledger.yaml path")
    vr.add_argument("--top", type=int, default=3,
                    help="scan only the top N trials by register distance")
    vr.add_argument("--budget", type=int, default=10,
                    help="maximum Pangram scans allowed")
    vr.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
