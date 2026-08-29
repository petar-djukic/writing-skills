#!/usr/bin/env python3
"""
drive.py — Headless driver for the filter-tells pipeline.

Orchestrates the filter-tells steps as a CLI so subagents and workflows
can invoke the pipeline without reading SKILL.md and calling each script
by hand.

Steps 1-2: lexical + structural scans (no model).
Step 3: semantic analysis via Ollama (12 perplexity prompts).
Steps 4-5: targeted rewrite of flagged passages, recursive validation.

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

_DIR = os.path.dirname(os.path.realpath(__file__))
_SKILL = os.path.normpath(os.path.join(_DIR, ".."))
_PROMPTS_PATH = os.path.join(_SKILL, "references", "perplexity-prompts.md")
_FM = re.compile(r"\A---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL)

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
# Paragraph extraction (shared scripts directory)
# ---------------------------------------------------------------------------

def _import_md_paragraphs():
    shared = os.path.normpath(os.path.join(_DIR, "..", "..", "..", "scripts"))
    if shared not in sys.path:
        sys.path.insert(0, shared)
    try:
        import md_paragraphs
        return md_paragraphs
    except ImportError:
        return None


def parse_paragraphs(article: str) -> list[list]:
    """Extract prose paragraphs as [[start_line, end_line, text], ...].

    Uses md_paragraphs.parse_file from the shared scripts directory.
    """
    mp = _import_md_paragraphs()
    if mp is None:
        raise RuntimeError(
            "md_paragraphs.py not found in .claude/scripts/")
    result = mp.parse_file(article)
    return result.paragraphs


# ---------------------------------------------------------------------------
# Steps 4-5: targeted rewrite and recursive validation
# ---------------------------------------------------------------------------

_REWRITE_PROMPT = """\
You are rewriting a passage to remove AI writing patterns while \
preserving exact meaning and matching the author's voice.

DETECTED ISSUES IN THIS PASSAGE:
{issue_report}

AUTHOR'S STYLE:
- Concise, active voice, Strunk & White style
- Specific and concrete, no vague qualifiers
- Takes positions, avoids hedging
- Varied sentence rhythm
- Technical precision without jargon inflation

PASSAGE TO REWRITE:
{passage}

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


def _issues_for_lines(scan: dict, start: int, end: int) -> str:
    """Collect scan issues that fall within a line range."""
    hits = []
    for h in scan.get("lexical", {}).get("issues", []):
        ln = h.get("line", 0)
        if start <= ln <= end:
            hits.append(f"L{ln} [{h.get('category','')}] {h.get('text','')[:100]}")
    for h in scan.get("structural", {}).get("issues", []):
        pos = h.get("position", "")
        hits.append(f"[{h.get('type','')}] {h.get('detail','')[:100]}")
    return "\n".join(hits) if hits else "(general AI patterns detected)"


# Pandoc [@key], numbered [1], and \citep{...}/\citet{...} markers. The gate
# compares multisets by identity: a rewrite that swaps [@park2024] for any
# other key — including a plausible-looking one — is damage, not preservation.
# match-voice's verify.py has enforced this per paragraph all along; the
# filter-tells splice had no citation check at all (GH-159).
_CITE_MARKERS = re.compile(r"\[@[^\]\s]+\]|\[\d+\]|\\cite[pt]?\{[^}]*\}")


def _citation_damage(original: str, rewritten: str) -> str | None:
    """A sentence naming what changed, or None when the markers survive."""
    from collections import Counter
    o, r = Counter(_CITE_MARKERS.findall(original)), Counter(_CITE_MARKERS.findall(rewritten))
    if o == r:
        return None
    lost = sorted((o - r).elements())
    invented = sorted((r - o).elements())
    parts = []
    if lost:
        parts.append(f"lost {', '.join(lost)}")
    if invented:
        parts.append(f"invented {', '.join(invented)}")
    return "citation markers damaged: " + "; ".join(parts)


def rewrite_passage(passage: str, issue_report: str,
                    endpoint: str, model: str, timeout: int) -> str:
    """Send a passage through the rewrite prompt via Ollama."""
    prompt = _REWRITE_PROMPT.format(passage=passage, issue_report=issue_report)
    return generate(prompt, endpoint=endpoint, model=model, timeout=timeout)


def _rewrite_error_cause(msg: str) -> str:
    """Bucket a rewrite error into a cause, mirroring match-voice's
    classify_rewrite_error so the two skills report failures in the same
    vocabulary. Local rather than imported: match-voice's copy lives in its
    driver script, and importing a driver for one dictionary couples the
    skills at the wrong joint."""
    m = (msg or "").lower()
    if "empty output" in m:
        return "empty/sanitized-to-empty"
    if "refusing" in m or "denylist" in m:
        return "refused-model"
    if "api key" in m:
        return "no-api-key"
    if "unreachable" in m:
        return "server-unreachable"
    if "timed out" in m or "timeout" in m:
        return "timeout"
    if "http" in m or "request failed" in m:
        return "api-error"
    return "other"


# Causes that will recur identically for every paragraph: a refused model, a
# missing key, an unreachable server. One of these stops the run; anything
# else costs only its own paragraph (GH-157).
RUN_FATAL_CAUSES = frozenset({"refused-model", "no-api-key", "server-unreachable"})


def run_rewrite(article_path: str, scan: dict, semantic: dict | None,
                endpoint: str, model: str, timeout: int,
                voice_profile: str | None = None,
                max_passes: int = 3) -> dict:
    """Steps 4-5: rewrite flagged passages and validate recursively."""
    with open(article_path) as f:
        original_text = f.read()

    fm_match = _FM.match(original_text)
    front_matter = fm_match.group(0) if fm_match else ""
    lines = original_text.split("\n")

    try:
        paras = parse_paragraphs(article_path)
    except RuntimeError as e:
        return {"error": str(e), "passes": []}

    if not paras:
        return {"error": "no paragraphs extracted", "passes": []}

    # Identify which paragraphs to rewrite based on scan issues
    targets = []
    for start, end, text in paras:
        issues = _issues_for_lines(scan, start, end)
        if issues != "(general AI patterns detected)" or \
                scan.get("verdict") in ("likely-ai", "suspicious",
                                        "suspicious-overshoot"):
            targets.append((start, end, text, issues))

    if not targets:
        return {"rewrites": 0, "passes": [],
                "message": "no passages targeted for rewrite"}

    out_dir = os.path.dirname(os.path.abspath(article_path))
    base = os.path.splitext(os.path.basename(article_path))[0]
    draft_path = os.path.join(out_dir, f"{base}.ft-draft.md")
    passes = []
    prev_issue_count = (scan["lexical"]["issue_count"] +
                        scan["structural"]["issue_count"])
    # Seed the draft with the original. Every pass then reads and writes THIS
    # file, so the paragraph positions in `targets` (re-derived from the same
    # file each pass) always match the buffer being spliced. The prior version
    # carried a stale in-memory `current_lines` across passes and spliced a
    # multi-line rewrite in as a single list element, so after pass 1 the list
    # was no longer one-line-per-element and every later index was wrong —
    # progressive corruption that ballooned the draft (GH-147).
    with open(draft_path, "w") as f:
        f.write(original_text)

    for pass_num in range(1, max_passes + 1):
        # Read the current draft fresh so splice indices match `targets`.
        current_lines = open(draft_path).read().split("\n")
        rewrites_applied = 0
        # One paragraph's failure costs that paragraph, not the pass: before
        # GH-157 a single RuntimeError broke out of this loop and silently
        # left every remaining paragraph unprocessed, with one bare error
        # string in the pass record. match-voice already isolates failures
        # per paragraph; this matches it. Only a cause that must recur for
        # every paragraph (RUN_FATAL_CAUSES) stops the run.
        errors = []
        fatal = None
        for start, end, text, issues in reversed(targets):
            try:
                rewritten = rewrite_passage(text, issues,
                                            endpoint, model, timeout)
            except RuntimeError as e:
                cause = _rewrite_error_cause(str(e))
                errors.append({"line": start, "cause": cause,
                               "error": str(e)[:200]})
                if cause in RUN_FATAL_CAUSES:
                    fatal = cause
                    break
                continue
            if rewritten and rewritten.strip() != text.strip():
                damage = _citation_damage(text, rewritten)
                if damage:
                    # The rewrite is refused, the original paragraph stays.
                    errors.append({"line": start, "cause": "citation-damage",
                                   "error": damage})
                    continue
                # Expand a multi-line rewrite into multiple list elements, or
                # current_lines stops being one-line-per-element. reversed()
                # (bottom-up) keeps earlier indices valid even when a rewrite
                # changes the paragraph's line count.
                current_lines[start - 1:end] = rewritten.split("\n")
                rewrites_applied += 1

        with open(draft_path, "w") as f:
            f.write("\n".join(current_lines))

        # Validate by re-running Steps 1-2 on the written draft.
        lex = run_lexical(draft_path)
        struct = run_structural(draft_path, voice_profile)
        val = combine(lex, struct)
        new_count = val["lexical"]["issue_count"] + val["structural"]["issue_count"]

        pass_record = {
            "pass": pass_num,
            "rewrites_applied": rewrites_applied,
            "issue_count": new_count,
            "prev_issue_count": prev_issue_count,
            "verdict": val["verdict"],
        }
        if errors:
            pass_record["errors"] = errors
        passes.append(pass_record)

        if fatal:
            # The paragraphs already rewritten this pass are kept — the draft
            # was written above — but nothing further can succeed.
            pass_record["stopped"] = f"fatal: {fatal}"
            break
        if val["verdict"] == "clean":
            break
        if new_count >= prev_issue_count:
            pass_record["stopped"] = "no improvement"
            break

        prev_issue_count = new_count
        # Re-parse + re-target from the written draft for the next pass.
        try:
            paras = parse_paragraphs(draft_path)
        except RuntimeError:
            break
        targets = []
        for start, end, text in paras:
            issues = _issues_for_lines(val, start, end)
            if issues != "(general AI patterns detected)":
                targets.append((start, end, text, issues))
        if not targets:
            break

    return {
        "draft_path": draft_path,
        "passes": passes,
        "before": {"issue_count": (scan["lexical"]["issue_count"] +
                                   scan["structural"]["issue_count"]),
                   "verdict": scan["verdict"]},
        "after": {"issue_count": passes[-1]["issue_count"] if passes else 0,
                  "verdict": passes[-1]["verdict"] if passes else scan["verdict"]},
    }


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
    ap.add_argument("--lexicon",
                    choices=["newsletter", "book", "industry", "academic",
                             "none"],
                    help="Venue lexicon for the lexical scan (GH-337); "
                         "usually a venue profile's tell_lexicon value. "
                         "Default: newsletter.")
    args = ap.parse_args()

    # Exported rather than threaded: detect-lexical.sh reads
    # FILTER_TELLS_LEXICON as its default, so the re-scan inside the rewrite
    # loop uses the same lexicon without every caller passing it down.
    if args.lexicon:
        os.environ["FILTER_TELLS_LEXICON"] = args.lexicon

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
    server_ok = False
    if scan["needs_step3"]:
        ok, msg = check_server(args.endpoint, args.model)
        if not ok:
            print(f"Error: {msg}", file=sys.stderr)
            scan["step3_error"] = msg
        else:
            server_ok = True
            prompts = load_prompts()
            with open(args.article) as f:
                article_text = f.read()
            semantic = run_semantic(article_text, scan, prompts,
                                   args.endpoint, args.model, args.timeout)
            scan["semantic"] = semantic

    if args.no_rewrite:
        output = json.dumps(scan, indent=2)
        if args.out:
            with open(args.out, "w") as f:
                f.write(output + "\n")
        else:
            print(output)
        sys.exit(0 if scan["verdict"] == "clean" else
                 2 if scan["verdict"] == "error" else 1)

    # Steps 4-5: targeted rewrite and recursive validation
    rewrite_result = None
    if scan["verdict"] != "clean" and server_ok:
        rewrite_result = run_rewrite(
            args.article, scan, semantic,
            args.endpoint, args.model, args.timeout,
            voice_profile=args.voice_profile)
        scan["rewrite"] = rewrite_result

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
