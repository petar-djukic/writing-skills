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
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
BASELINE = os.path.join(HERE, "baseline.json")

# A detector that fires on more than this fraction of human files is noise:
# retune it or demote it to advisory (documented gate, see README).
HUMAN_FIRE_GATE = 0.20


def corpus_files(cls):
    d = os.path.join(HERE, cls)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if f.endswith((".md", ".tex")) and not f.startswith(".")
    )


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
    return d.get("verdict", "?"), fired


def evaluate():
    report = {"classes": {}, "detectors": {}, "verdict_accuracy": {}}
    per_class_hits = {}

    for cls in ("human", "ai"):
        files = corpus_files(cls)
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
        }

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
    if not hu_v:
        report["verdict_accuracy"]["human_clean"]["note"] = (
            "human corpus empty — populate eval/human/ (see README); "
            "false-positive rates unmeasured until then")
    return report


def main():
    update = "--update-baseline" in sys.argv
    report = evaluate()

    if not corpus_files("ai") and not corpus_files("human"):
        print("No corpus files found under eval/human or eval/ai.", file=sys.stderr)
        sys.exit(2)

    regressions = []
    if os.path.exists(BASELINE) and not update:
        base = json.load(open(BASELINE))
        # regression: a detector's human fire rate rose above baseline,
        # or verdict accuracy dropped.
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
