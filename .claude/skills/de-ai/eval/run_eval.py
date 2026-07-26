#!/usr/bin/env python3
"""Calibration harness for de-ai's two scripts against the labeled eval corpus.

Runs detect-lexical.sh and detect-structural.py over eval/human/ and eval/ai/,
aggregates per-detector hit rates on each class, and reports suite-level
verdict accuracy: human files should not scan `likely-ai`; ai files should not
scan `clean`. Diffs against baseline.json when present.

Scope: the two scripts only. The semantic prompts (Step 3) need a model and
are outside automated eval — a detector that "passes" here has passed the
surface layer, nothing more.

Usage:
    python3 run_eval.py [--update-baseline]

Exit codes: 0 = no regressions vs baseline (or baseline updated);
1 = regression (a detector's human-class fire rate rose, or verdict accuracy
fell); 2 = corpus/setup problem.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
BASELINE = os.path.join(HERE, "baseline.json")

# A detector that fires on more than this fraction of human files is noise:
# retune it or demote it to advisory (documented gate, see README).
HUMAN_FIRE_GATE = 0.20

# Samples written after this year may carry AI diction. We do not filter on it —
# what belongs in the corpus is the curator's decision — but we say so.
AI_ERA_YEAR = 2022


def corpus_files(cls):
    d = os.path.join(HERE, cls)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if f.endswith((".md", ".tex")) and not f.startswith(".")
    )


def human_from_writing_voice(start=None, role="author-voice"):
    """Author-designated human prose from the consuming repository.

    `.claude/` is a symlink into the shared skills repo, so eval/human/ is not
    a per-repo directory — anything dropped there lands in the public skills
    repo. That is why it has stayed empty, and it is the wrong place to ask
    anyone to put their own writing.

    The samples already exist somewhere better. A repository that uses these
    skills carries writing-voice/, whose author-voice exemplars are exactly
    what this class needs: prose the author designated as theirs, certified by
    the manifest, sitting in their own repo. We walk up to find it with the
    same discovery rule voice_anchors.py uses, and read rather than copy — the
    text never enters the skills repo, so a private corpus stays private.

    Returns (files, meta). meta carries the provenance the baseline records
    instead of the text.
    """
    sys.path.insert(0, SCRIPTS) if SCRIPTS not in sys.path else None
    try:
        import voice_anchors
    except ImportError:
        return [], {"source": None, "reason": "voice_anchors.py not importable"}

    d = voice_anchors.discover(start or os.getcwd())
    if not d:
        return [], {"source": None,
                    "reason": "no writing-voice/ found from the working directory"}
    try:
        exemplars = voice_anchors.load_manifest(d)   # returns the exemplar list
    except Exception as e:                           # malformed manifest is not fatal
        return [], {"source": d, "reason": f"manifest unreadable: {e}"}

    files, years, late = [], [], []
    for ex in exemplars:
        if ex.get("role") != role:
            continue
        p = os.path.join(d, ex.get("file", ""))
        if not os.path.isfile(p):
            continue
        files.append(p)
        y = ex.get("year")
        years.append(y)
        # Curating the corpus is the curator's job, not ours — we use what the
        # manifest lists. But a sample written after generative AI arrived may
        # carry AI diction, and as ground truth for "what human prose looks
        # like" that is circular. Warn; do not silently drop.
        if isinstance(y, int) and y > AI_ERA_YEAR:
            late.append(f"{ex.get('id') or os.path.basename(p)} ({y})")

    known = [y for y in years if isinstance(y, int)]
    meta = {
        "source": d,
        "role": role,
        "files": len(files),
        "years": [min(known), max(known)] if known else None,
    }
    if late:
        meta["warning"] = (
            f"{len(late)} sample(s) dated after {AI_ERA_YEAR} are in the human "
            f"class: {', '.join(late)}. Post-{AI_ERA_YEAR} prose may carry AI "
            f"diction, which makes it circular as ground truth. Left in — "
            f"curating the corpus is the curator's call.")
    return sorted(files), meta


def run_lexical(path):
    """Set of lexical categories that fired on the file."""
    r = subprocess.run(
        ["bash", os.path.join(SCRIPTS, "detect-lexical.sh"), path, "--json"],
        capture_output=True, text=True)
    try:
        hits = json.loads(r.stdout)
    except json.JSONDecodeError:
        return set()
    return {h["category"] for h in hits if isinstance(h, dict)}


def run_structural(path):
    """(verdict, set of structural issue types + advisory blocks present)."""
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "detect-structural.py"),
         path, "--json"],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return "error", set()
    if isinstance(d, list):
        d = d[0]
    fired = {i["type"] for i in d.get("issues", [])}
    if d.get("repeated_formulae"):
        fired.add("repeated_formulae")
    if d.get("coinage_candidates"):
        fired.add("coinage_candidates")
    if d.get("tail_echo_candidates"):
        fired.add("tail_echo_candidates")
    return d.get("verdict", "?"), fired


# Length bands for the matched-length pass. The lowest is the ai class's own
# range; the highest is a long article. Detector thresholds were tuned around
# the short end, so the bands show what happens as a draft grows.
LENGTH_BANDS = (400, 800, 1500, 2500)

# Below this fraction of the target the excerpt is not representative of the
# band, so the document is skipped for it and counted rather than padded.
BAND_TOLERANCE = 0.7


def word_count(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return len(f.read().split())
    except OSError:
        return 0


def length_stats(paths):
    """n / median / min / max words. The distribution the first measurement hid."""
    w = sorted(word_count(p) for p in paths)
    if not w:
        return {"n": 0, "median": None, "min": None, "max": None}
    mid = len(w) // 2
    median = w[mid] if len(w) % 2 else (w[mid - 1] + w[mid]) // 2
    return {"n": len(w), "median": median, "min": w[0], "max": w[-1]}


def excerpt(path, target):
    """Consecutive whole paragraphs totalling ~target words, or None.

    Deterministic: same file and target give the same excerpt every run, or
    rates wander between runs for reasons nobody can trace. Whole paragraphs
    only — a word-slice would hand the detectors truncated sentences and
    measure the truncation.

    Starts after the first two body paragraphs to skip abstract-like openings,
    which are their own register and would bias short bands.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    paras = [p for p in re.split(r"\n\s*\n", text)
             if len(p.split()) >= 40 and not p.strip().startswith(("#", "|", "```"))]
    if len(paras) < 3:
        return None
    acc, total = [], 0
    for p in paras[2:]:
        acc.append(p)
        total += len(p.split())
        if total >= target:
            break
    if total < target * BAND_TOLERANCE:
        return None
    return "\n\n".join(acc)


def measure_bands(class_paths, bands=LENGTH_BANDS):
    """Fire rates per class per length band, comparing like with like.

    A detector at 0.00 in one band and 0.96 in another is the whole signal —
    averaging the bands together destroys exactly what this exists to show.
    """
    out = {}
    tmp = tempfile.mkdtemp(prefix="eval-bands-")
    try:
        for band in bands:
            row = {}
            for cls, paths in class_paths.items():
                hits, verdicts, used, skipped = [], [], 0, 0
                for p in paths:
                    ex = excerpt(p, band)
                    if ex is None:
                        skipped += 1
                        continue
                    f = os.path.join(tmp, f"{cls}-{band}-{used}.md")
                    with open(f, "w", encoding="utf-8") as fh:
                        fh.write(ex)
                    verdict, s_fired = run_structural(f)
                    hits.append(s_fired | run_lexical(f))
                    verdicts.append(verdict)
                    used += 1
                dets = {}
                if used:
                    for det in sorted(set().union(*hits) if hits else set()):
                        n = sum(1 for h in hits if det in h)
                        dets[det] = round(n / used, 2)
                # Report the verdict spread, not just a binary. "suspicious"
                # and "likely-ai" are different experiences for a writer, and
                # collapsing them makes the headline rate mean whichever one
                # the reader assumes.
                row[cls] = {
                    "documents": used,
                    "skipped_too_short": skipped,
                    "verdicts": dict(Counter(verdicts)),
                    "non_clean_rate": (
                        round(sum(1 for v in verdicts
                                  if v not in ("clean", "minor-issues")) / used, 2)
                        if used else None),
                    "ai_verdict_rate": (
                        round(sum(1 for v in verdicts
                                  if v in ("likely-ai", "suspicious-overshoot")) / used, 2)
                        if used else None),
                    "avg_detectors_fired": (
                        round(sum(len(h) for h in hits) / used, 1) if used else None),
                    "detectors": dets,
                }
            out[str(band)] = row
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def evaluate(bands=False):
    report = {"classes": {}, "detectors": {}, "verdict_accuracy": {}}
    per_class_hits = {}

    human_meta = None
    for cls in ("human", "ai"):
        files = corpus_files(cls)
        if cls == "human" and not files:
            files, human_meta = human_from_writing_voice()
        per_file = {}
        verdicts = {}
        for f in files:
            fired = run_lexical(f)
            verdict, s_fired = run_structural(f)
            per_file[os.path.basename(f)] = sorted(fired | s_fired)
            verdicts[os.path.basename(f)] = verdict
        per_class_hits[cls] = per_file
        report["classes"][cls] = {
            "files": len(files),
            "verdicts": verdicts,
            "length": length_stats(files),
        }
        report["classes"][cls]["_paths"] = list(files)
        if cls == "human" and human_meta:
            # Provenance, not text: where the samples came from, so a baseline
            # is interpretable without the private corpus being present.
            report["classes"][cls]["source"] = human_meta

    # per-detector fire rates per class
    all_detectors = set()
    for cls in per_class_hits:
        for hits in per_class_hits[cls].values():
            all_detectors.update(hits)
    for det in sorted(all_detectors):
        row = {}
        for cls in ("human", "ai"):
            files = per_class_hits[cls]
            n = len(files)
            fired = sum(1 for hits in files.values() if det in hits)
            row[cls] = {"fired": fired, "of": n,
                        "rate": round(fired / n, 2) if n else None}
        report["detectors"][det] = row

    # suite verdict accuracy
    ai_v = report["classes"].get("ai", {}).get("verdicts", {})
    hu_v = report["classes"].get("human", {}).get("verdicts", {})
    report["verdict_accuracy"] = {
        "ai_flagged": {
            "count": sum(1 for v in ai_v.values() if v not in ("clean", "minor-issues")),
            "of": len(ai_v),
        },
        "human_clean": {
            "count": sum(1 for v in hu_v.values() if v in ("clean", "minor-issues")),
            "of": len(hu_v),
        },
    }
    # The confound that produced the original 20-over-gate figure: comparing a
    # 5,889-word median against a 332-word one and calling the difference a
    # false-positive rate. Name it in the output so it cannot hide again.
    hl = report["classes"].get("human", {}).get("length", {})
    al = report["classes"].get("ai", {}).get("length", {})
    if hl.get("median") and al.get("median"):
        ratio = max(hl["median"], al["median"]) / min(hl["median"], al["median"])
        if ratio >= 2:
            report["length_mismatch"] = {
                "human_median": hl["median"], "ai_median": al["median"],
                "ratio": round(ratio, 1),
                "note": (f"class medians differ by {ratio:.1f}x "
                         f"(human {hl['median']}, ai {al['median']}). Overall "
                         f"per-detector rates below are not a false-positive "
                         f"rate — they partly measure length. Use the "
                         f"length_bands section, which compares like with like."),
            }

    if bands:
        report["length_bands"] = measure_bands(
            {c: report["classes"][c].get("_paths", []) for c in ("human", "ai")})

    for c in ("human", "ai"):
        report["classes"].get(c, {}).pop("_paths", None)

    if not hu_v:
        why = (human_meta or {}).get("reason") or "no human samples found"
        report["verdict_accuracy"]["human_clean"]["note"] = (
            f"human corpus empty ({why}). Run from a repository that carries "
            "writing-voice/, or see README. False-positive rates are unmeasured "
            "until then, which makes the <=20% human-fire gate vacuous — every "
            "detector passes that half for free.")
    return report


def main():
    update = "--update-baseline" in sys.argv
    bands = "--bands" in sys.argv
    report = evaluate(bands=bands)

    if not corpus_files("ai") and not report["classes"]["human"]["files"]:
        print("No corpus files found under eval/ai, and no human samples "
              "discovered from the working directory.", file=sys.stderr)
        sys.exit(2)

    # To stderr so it is seen even when stdout is piped into jq or a baseline.
    src = report["classes"]["human"].get("source") or {}
    if src.get("warning"):
        print(f"WARNING: {src['warning']}", file=sys.stderr)

    regressions = []
    if os.path.exists(BASELINE) and not update:
        base = json.load(open(BASELINE))
        # The human corpus lives in whichever repository you run from, so two
        # runs can be measuring different prose. Comparing human rates across
        # different corpora reports genre differences as detector regressions.
        now_src = (report["classes"]["human"].get("source") or {}).get("source")
        was_src = (base.get("classes", {}).get("human", {}).get("source") or {}).get("source")
        same_corpus = now_src == was_src
        if not same_corpus:
            report["baseline_corpus_mismatch"] = {
                "baseline": was_src, "current": now_src,
                "note": ("human-rate comparison skipped: the baseline was built "
                         "from a different corpus. ai-class rates and verdict "
                         "accuracy are still comparable."),
            }
        # regression: a detector's human fire rate rose above baseline,
        # or verdict accuracy dropped.
        if same_corpus:
            for det, row in report["detectors"].items():
                hr = row["human"]["rate"]
                br = base.get("detectors", {}).get(det, {}).get("human", {}).get("rate")
                if hr is not None and br is not None and hr > br:
                    regressions.append(f"{det}: human fire rate {br} -> {hr}")
        for key in ("ai_flagged", "human_clean"):
            now = report["verdict_accuracy"][key]
            was = base.get("verdict_accuracy", {}).get(key, {})
            if was.get("of") and now["of"] and \
               now["count"] / now["of"] < was["count"] / was["of"]:
                regressions.append(f"verdict {key}: {was['count']}/{was['of']} -> {now['count']}/{now['of']}")
        report["regressions_vs_baseline"] = regressions

    # gate warnings (informational; the gate applies to NEW detectors per README)
    noisy = [d for d, row in report["detectors"].items()
             if row["human"]["rate"] is not None and row["human"]["rate"] > HUMAN_FIRE_GATE]
    if noisy:
        report["human_gate_exceeded"] = sorted(noisy)

    print(json.dumps(report, indent=2))

    if update:
        with open(BASELINE, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nbaseline written: {BASELINE}", file=sys.stderr)
        sys.exit(0)
    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
