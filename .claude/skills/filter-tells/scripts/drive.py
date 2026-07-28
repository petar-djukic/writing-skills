#!/usr/bin/env python3
"""
drive.py — Headless driver for the filter-tells pipeline.

Orchestrates the filter-tells steps as a CLI so subagents and workflows
can invoke the pipeline without reading SKILL.md and calling each script
by hand.

Usage:
    python3 drive.py --article <path> --scan-only
    python3 drive.py --article <path> --no-rewrite [--model <model>]
    python3 drive.py --article <path> [--voice-profile <path>] [--out <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL = os.path.normpath(os.path.join(_DIR, ".."))
_PROMPTS_PATH = os.path.join(_SKILL, "references", "perplexity-prompts.md")

DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("FILTER_TELLS_MODEL", "gpt-oss:120b-cloud")
DEFAULT_TIMEOUT = int(os.environ.get("FILTER_TELLS_TIMEOUT", "600"))


# ---------------------------------------------------------------------------
# Ollama client (imported from match-voice when available, inline fallback)
# ---------------------------------------------------------------------------

def _import_generate():
    """Import generate() from match-voice/scripts/rewrite.py."""
    mv = os.path.normpath(os.path.join(_DIR, "..", "..", "match-voice", "scripts"))
    if mv not in sys.path:
        sys.path.insert(0, mv)
    try:
        from rewrite import generate, check_server
        return generate, check_server
    except ImportError:
        return None, None


_generate_fn, _check_server_fn = _import_generate()


def generate(prompt: str, endpoint: str = DEFAULT_ENDPOINT,
             model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT) -> str:
    if _generate_fn is not None:
        return _generate_fn(prompt, endpoint=endpoint, model=model,
                            temperature=0.3, timeout=timeout)
    raise RuntimeError(
        "Could not import generate() from match-voice/scripts/rewrite.py. "
        "Ensure the skill set is complete.")


def check_server(endpoint: str, model: str) -> tuple[bool, str]:
    if _check_server_fn is not None:
        return _check_server_fn(endpoint, model)
    return False, "check_server not importable"


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts() -> dict[str, str]:
    """Parse perplexity-prompts.md into {prompt_id: template_text}."""
    with open(_PROMPTS_PATH) as f:
        text = f.read()
    prompts = {}
    blocks = re.split(r"^## Prompt (\d+\w?):", text, flags=re.MULTILINE)
    for i in range(1, len(blocks), 2):
        pid = blocks[i].strip()
        body = blocks[i + 1]
        code = re.findall(r"```\n(.*?)```", body, re.DOTALL)
        if code:
            prompts[pid] = code[0].strip()
    return prompts


# ---------------------------------------------------------------------------
# Steps 1-2: lexical + structural scans
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 3: semantic analysis via Ollama
# ---------------------------------------------------------------------------

def _fmt_issues(issues: list) -> str:
    """Format issues list as a readable summary for prompt injection."""
    if not issues:
        return "(none)"
    lines = []
    for h in issues[:30]:
        cat = h.get("category", h.get("type", ""))
        line = h.get("line", h.get("position", ""))
        text = h.get("text", h.get("detail", ""))[:120]
        lines.append(f"  L{line} [{cat}] {text}")
    return "\n".join(lines)


def _fmt_metrics(metrics: dict) -> str:
    if not metrics:
        return "(none)"
    return "\n".join(f"  {k}: {v}" for k, v in metrics.items())


def _filter_hits(candidates: list, category: str) -> str:
    hits = [h for h in candidates if h.get("category") == category]
    if not hits:
        return "(none)"
    return "\n".join(f"  L{h.get('line','')} {h.get('text','')[:100]}"
                     for h in hits[:15])


def run_semantic(article_text: str, scan: dict, prompts: dict,
                 endpoint: str, model: str, timeout: int) -> dict:
    """Run Step 3 prompts in the order specified by SKILL.md/prompt-catalog."""
    results = {}
    lex = scan.get("lexical", {})
    struct = scan.get("structural", {})
    metrics = struct.get("metrics", {})

    def call(pid: str, extra_vars: dict | None = None) -> str | None:
        tmpl = prompts.get(pid)
        if tmpl is None:
            return None
        variables = {"text": article_text}
        if extra_vars:
            variables.update(extra_vars)
        filled = tmpl
        for k, v in variables.items():
            filled = filled.replace("{" + k + "}", str(v))
        # Clear unfilled placeholders
        filled = re.sub(r"\{[a-z_]+\}", "(not available)", filled)
        try:
            return generate(filled, endpoint=endpoint, model=model,
                            timeout=timeout)
        except RuntimeError as e:
            return f"[error] {e}"

    # Prompt 0: cold read (first, before anything else)
    results["prompt_0"] = call("0")

    # Prompts 1-3: independent assessments (sequential in this driver)
    results["prompt_1"] = call("1")
    results["prompt_2"] = call("2")
    results["prompt_3"] = call("3")

    # Prompt 4: CoT leakage detection (after lexical results)
    results["prompt_4"] = call("4")

    # Prompt 6 + 6b: antithesis and set-piece enumeration (after structural)
    results["prompt_6"] = call("6")
    results["prompt_6b"] = call("6b")

    # Prompt 7: overshoot assessment (after structural, seeded with metrics)
    perf_metrics = {k: v for k, v in metrics.items()
                    if k in ("plain_sentence_rate", "intensity_variance",
                             "mean_performance_score")}
    results["prompt_7"] = call("7", {
        "performance_metrics": _fmt_metrics(perf_metrics),
        "punch_candidates": _fmt_issues(
            [i for i in struct.get("issues", [])
             if "punch" in i.get("type", "")]),
        "salad_candidates": _fmt_issues(
            [i for i in struct.get("issues", [])
             if "salad" in i.get("type", "")]),
        "repeated_formulae": json.dumps(
            struct.get("repeated_formulae", [])[:10], indent=2),
        "ornate_hits": _filter_hits(
            lex.get("candidates", []), "ornate-register"),
        "voice_anchors": "(not available)",
    })

    # Prompt 8 + 8b: definedness/circularity and empty phrases
    results["prompt_8"] = call("8")
    coinage = struct.get("coinage_candidates", [])
    results["prompt_8b"] = call("8b", {
        "coinage_candidates": json.dumps(coinage[:10], indent=2)
            if coinage else "(none)",
        "editorializing_hits": _filter_hits(
            lex.get("candidates", []), "editorializing"),
        "reader_directive_hits": _filter_hits(
            lex.get("candidates", []), "reader-directive"),
        "meta_narration_hits": _filter_hits(
            lex.get("candidates", []), "meta-narration"),
    })

    # Prompt 9: paragraph schema (seeded by structural metrics)
    schema_metrics = {k: v for k, v in metrics.items()
                      if k in ("topic_overlap", "cohesion", "subject_churn")}
    results["prompt_9"] = call("9", {
        "schema_metrics": _fmt_metrics(schema_metrics)
            if schema_metrics else "(no paragraph schema proxies available)",
    })

    # Prompt 5: integrator — runs LAST with all evidence
    results["prompt_5"] = call("5", {
        "lexical_results": _fmt_issues(lex.get("issues", [])),
        "structural_results": (
            f"Verdict: {struct.get('verdict', 'unknown')}\n"
            f"Issues: {_fmt_issues(struct.get('issues', []))}\n"
            f"Metrics: {_fmt_metrics(metrics)}"),
        "perplexity_results": "\n".join(
            f"Prompt {k}: {(v or '')[:200]}"
            for k, v in sorted(results.items())
            if k.startswith("prompt_") and k not in ("prompt_5",)),
        "cot_results": (results.get("prompt_4") or "(not run)")[:500],
        "overshoot_results": (results.get("prompt_7") or "(not run)")[:500],
    })

    # Extract rewrite priority from Prompt 5 output
    priority = _extract_priority(results.get("prompt_5", ""))

    # Extract overall verdict signals from Prompt 5
    ai_prob = _extract_field(results.get("prompt_5", ""), "AI_PROBABILITY")
    confidence = _extract_field(results.get("prompt_5", ""), "CONFIDENCE")
    cold_verdict = _extract_field(results.get("prompt_0", ""), "COLD_VERDICT")

    return {
        "prompts_run": [k.replace("prompt_", "") for k in sorted(results)
                        if results[k] is not None],
        "cold_verdict": cold_verdict,
        "ai_probability": ai_prob,
        "confidence": confidence,
        "rewrite_priority": priority,
        "prompt_results": results,
    }


def _extract_priority(text: str) -> list[str]:
    """Extract REWRITE_PRIORITY lines from Prompt 5 output."""
    if not text:
        return []
    m = re.search(r"REWRITE_PRIORITY[:\s]*(.*?)(?:\n\n|\Z)",
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    block = m.group(1).strip()
    lines = [ln.strip().lstrip("0123456789.-) ") for ln in block.split("\n")
             if ln.strip() and not ln.strip().startswith("---")]
    return [ln for ln in lines if ln]


def _extract_field(text: str, field: str) -> str:
    """Extract a labeled field value from prompt output."""
    if not text:
        return ""
    m = re.search(rf"{field}[:\s]+(.+?)(?:\n|$)", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Model for semantic analysis (default: {DEFAULT_MODEL})")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                    help=f"Ollama endpoint (default: {DEFAULT_ENDPOINT})")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"Per-prompt timeout in seconds (default: {DEFAULT_TIMEOUT})")
    ap.add_argument("--no-rewrite", action="store_true",
                    help="Run Steps 1-3, report only, skip rewrite passes")
    ap.add_argument("--voice-dir",
                    help="Path to writing-voice/ directory (future)")
    args = ap.parse_args()

    if not os.path.isfile(args.article):
        print(f"Error: file not found: {args.article}", file=sys.stderr)
        sys.exit(2)

    # Steps 1-2: lexical + structural scans
    lexical = run_lexical(args.article)
    structural = run_structural(args.article, args.voice_profile)
    scan = combine(lexical, structural)

    if args.scan_only:
        output = json.dumps(scan, indent=2)
        if args.out:
            with open(args.out, "w") as f:
                f.write(output + "\n")
        else:
            print(output)
        sys.exit(0 if scan["verdict"] == "clean" else
                 2 if scan["verdict"] == "error" else 1)

    # Step 3: semantic analysis (skip when clean)
    semantic = None
    if scan["needs_step3"]:
        ok, msg = check_server(args.endpoint, args.model)
        if not ok:
            print(f"Error: {msg}", file=sys.stderr)
            scan["step3_error"] = msg
        else:
            prompts = load_prompts()
            with open(args.article) as f:
                article_text = f.read()
            semantic = run_semantic(article_text, scan, prompts,
                                   args.endpoint, args.model, args.timeout)
            scan["semantic"] = semantic

    result = scan
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
