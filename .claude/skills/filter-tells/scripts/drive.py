#!/usr/bin/env python3
"""
drive.py — Headless driver for the filter-tells pipeline.

Orchestrates the filter-tells steps as a CLI so subagents and workflows
can invoke the pipeline without reading SKILL.md and calling each script
by hand.  Sub-issue #302 covers Steps 1-2 (lexical + structural scans);
later sub-issues add Steps 3-5.

Usage:
    python3 drive.py --article <path> --scan-only
    python3 drive.py --article <path> [--voice-profile <path>] [--out <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))


def run_lexical(article: str) -> dict:
    """Run detect-lexical.sh --json and parse its output."""
    script = os.path.join(_DIR, "detect-lexical.sh")
    proc = subprocess.run(
        ["bash", script, article, "--json"],
        capture_output=True, text=True)
    if proc.returncode == 2:
        return {"error": proc.stderr.strip(), "exit_code": 2,
                "issues": [], "candidates": []}
    try:
        hits = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "failed to parse lexical JSON",
                "raw": proc.stdout[:500], "exit_code": proc.returncode,
                "issues": [], "candidates": []}
    issues = [h for h in hits if h.get("severity") != "candidate"]
    candidates = [h for h in hits if h.get("severity") == "candidate"]
    return {"exit_code": proc.returncode, "issues": issues,
            "candidates": candidates}


def run_structural(article: str, voice_profile: str | None = None) -> dict:
    """Run detect-structural.py --json and return its parsed dict."""
    script = os.path.join(_DIR, "detect-structural.py")
    cmd = [sys.executable, script, article, "--json"]
    if voice_profile:
        cmd.append(f"--voice-profile={voice_profile}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 2:
        return {"error": proc.stderr.strip(), "exit_code": 2,
                "verdict": "error", "issues": [], "metrics": {}}
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "failed to parse structural JSON",
                "raw": proc.stdout[:500], "exit_code": proc.returncode,
                "verdict": "error", "issues": [], "metrics": {}}
    result["exit_code"] = proc.returncode
    return result


def combine(lexical: dict, structural: dict) -> dict:
    """Merge lexical and structural results into a single scan summary."""
    lex_issues = lexical.get("issues", [])
    lex_candidates = lexical.get("candidates", [])
    struct_issues = structural.get("issues", [])
    struct_verdict = structural.get("verdict", "error")

    has_issues = bool(lex_issues) or bool(struct_issues)
    if structural.get("error") or lexical.get("error"):
        verdict = "error"
    elif has_issues:
        verdict = struct_verdict if struct_verdict in (
            "likely-ai", "suspicious", "suspicious-overshoot"
        ) else "issues-found"
    else:
        verdict = struct_verdict

    categories = {}
    for hit in lex_issues:
        cat = hit.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "verdict": verdict,
        "needs_step3": verdict not in ("clean", "error"),
        "lexical": {
            "exit_code": lexical.get("exit_code", -1),
            "issue_count": len(lex_issues),
            "candidate_count": len(lex_candidates),
            "categories": categories,
            "issues": lex_issues,
            "candidates": lex_candidates,
        },
        "structural": {
            "exit_code": structural.get("exit_code", -1),
            "verdict": struct_verdict,
            "issue_count": len(struct_issues),
            "issues": struct_issues,
            "metrics": structural.get("metrics", {}),
            "advisory": structural.get("advisory", []),
            "repeated_formulae": structural.get("repeated_formulae", []),
            "coinage_candidates": structural.get("coinage_candidates", []),
        },
    }


def main():
    ap = argparse.ArgumentParser(
        description="filter-tells headless driver")
    ap.add_argument("--article", required=True,
                    help="Path to the markdown file to analyze")
    ap.add_argument("--scan-only", action="store_true",
                    help="Run Steps 1-2 only, print JSON, and exit")
    ap.add_argument("--voice-profile",
                    help="Path to a voice-profile.json for distance check")
    ap.add_argument("--out", help="Write JSON output to this file")
    ap.add_argument("--model", help="Model for semantic analysis (future)")
    ap.add_argument("--endpoint", help="Ollama endpoint (future)")
    ap.add_argument("--no-rewrite", action="store_true",
                    help="Report only, skip rewrite passes (future)")
    ap.add_argument("--voice-dir",
                    help="Path to writing-voice/ directory (future)")
    args = ap.parse_args()

    if not os.path.isfile(args.article):
        print(f"Error: file not found: {args.article}", file=sys.stderr)
        sys.exit(2)

    lexical = run_lexical(args.article)
    structural = run_structural(args.article, args.voice_profile)
    result = combine(lexical, structural)

    output = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(output + "\n")
    else:
        print(output)

    if result["verdict"] == "error":
        sys.exit(2)
    elif result["verdict"] == "clean":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
