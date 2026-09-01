#!/usr/bin/env python3
"""Headless driver for the match-outline skill (whole-document voice analysis).

Three modes, composable:

  compare (default)      Qualitative comparison of a draft against the
                         corpus voice profile. One API call.
  --exemplar P [...]     Extract a voice persona blueprint from one or more
                         exemplar papers: one extraction call per exemplar,
                         plus a synthesis call when there are several.
                         Writes voice-blueprint-<slug>.md.
  --rewrite              Apply a blueprint (or the corpus profile) to the
                         whole draft in one pass. Writes
                         <draft-stem>-rewritten.md, then verifies content
                         preservation (citations, numbers) and runs the
                         similarity plagiarism guard.

All analysis instructions are read at runtime from the skill's own
references/ files — the same files the interactive skill uses — so there is
exactly one source of truth.

Usage:
    match_outline.py DRAFT.md                          # compare
    match_outline.py --exemplar P1 --exemplar P2       # extract blueprint
    match_outline.py DRAFT.md --rewrite                # rewrite w/ latest blueprint
    match_outline.py DRAFT.md --exemplar P1 --rewrite  # extract + rewrite

Requires: an Ollama endpoint for the default model (gpt-oss:120b-cloud).
Pass --model claude-sonnet-5 to use the Anthropic API instead.
"""

import argparse
import glob as globmod
import json
import os
import re
import subprocess
import sys
from datetime import date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCH_STRUCTURE = os.path.normpath(os.path.join(SKILL_DIR, "..", "match-structure", "scripts"))
STYLE_PY = os.path.join(MATCH_STRUCTURE, "style.py")
MATCH_VOICE = os.path.normpath(os.path.join(SKILL_DIR, "..", "match-voice", "scripts"))
ANALYSIS_MD = os.path.join(SKILL_DIR, "references", "voice-analysis-instructions.md")
APPLICATION_MD = os.path.join(SKILL_DIR, "references", "style-application-instructions.md")
REPORT_TEMPLATE = os.path.join(SKILL_DIR, "references", "comparison-report-template.md")

# Cohere default (GH-184). MATCH_OUTLINE_MODEL overrides; gpt-oss:120b-cloud
# is the keyless/local fallback. The cohere: prefix routes through the shared
# generate() inside _call_ollama, so no separate client exists here.
DEFAULT_MODEL = os.environ.get("MATCH_OUTLINE_MODEL", "cohere:command-a-03-2025")
DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
# --rewrite is a single generation call whose output scales with the document,
# so the ceiling has to move with the machine: a 1,427-word chapter took 604s at
# 14.2 tok/s on a resident local model, and warming does not help when
# generation itself is the cost (GH-23). rewrite.py already exposed its own
# timeout; passing 600 explicitly at the call site is what defeated it.
DEFAULT_TIMEOUT = int(os.environ.get("MATCH_OUTLINE_TIMEOUT", "600"))
MAX_EXCERPT_CHARS = 12000          # per paper in comparison and rewrite mode
MAX_CORPUS_CHARS = 350000          # ~100K tokens

sys.path.insert(0, MATCH_STRUCTURE)
import style  # noqa: E402  (section detection, corpus selection, similarity)

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

_FM = re.compile(r"\A---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL)


def read(path):
    with open(path) as f:
        return f.read()


def read_prose(path):
    """Read a markdown file, stripping YAML frontmatter."""
    return _FM.sub("", read(path))


def _is_claude(model):
    return model.startswith("claude-")


def _get_anthropic_client():
    try:
        import anthropic
    except ImportError:
        sys.exit("The anthropic package is required for claude-* models. "
                 "Install with: python3 -m pip install --user anthropic")
    return anthropic.Anthropic()


def _call_claude(client, model, system, content_blocks, max_tokens=16000):
    """One streamed Anthropic API call."""
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": content_blocks}],
    ) as stream:
        response = stream.get_final_message()
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text.strip():
        sys.exit(f"Empty response (stop_reason: {response.stop_reason})")
    return text, response.usage


def _call_ollama(endpoint, model, system, content_blocks, timeout=DEFAULT_TIMEOUT):
    """One Ollama generation call, matching the interface call_model uses."""
    if MATCH_VOICE not in sys.path:
        sys.path.insert(0, MATCH_VOICE)
    import rewrite as rw
    sys_text = system if isinstance(system, str) else "\n\n".join(
        b["text"] for b in system if b.get("type") == "text")
    user_text = "\n\n".join(
        b["text"] for b in content_blocks if b.get("type") == "text")
    prompt = f"{sys_text}\n\n{user_text}"
    text = rw.generate(prompt, endpoint=endpoint, model=model,
                       temperature=0.7, timeout=timeout)
    if not text or not text.strip():
        sys.exit("Empty response from Ollama")

    class _Usage:
        output_tokens = len(text.split()) * 2  # rough estimate
    return text.strip(), _Usage()


def call_model(backend, system, content_blocks, max_tokens=16000):
    """Dispatch to Claude or Ollama based on backend config."""
    if backend["type"] == "claude":
        return _call_claude(backend["client"], backend["model"],
                            system, content_blocks, max_tokens)
    return _call_ollama(backend["endpoint"], backend["model"],
                        system, content_blocks,
                        timeout=backend.get("timeout", DEFAULT_TIMEOUT))


def resolve_paper(spec, db_path):
    """Resolve an exemplar spec (path or citation id) to (id, absolute path)."""
    if os.path.exists(spec):
        return os.path.splitext(os.path.basename(spec))[0], os.path.abspath(spec)
    entries = style.load_db(db_path)
    db_dir = os.path.dirname(os.path.abspath(db_path))
    for e in entries:
        if e.get("id") == spec or e.get("arxiv_id") == spec:
            md_rel = e.get("md_path") or e.get("text_path")
            if not md_rel:
                sys.exit(f"Entry {spec} has no md_path. Run update-references repair.")
            path = os.path.join(db_dir, md_rel)
            if os.path.exists(path):
                return e["id"], path
            sys.exit(f"Markdown file missing for {spec}: {path}")
    sys.exit(f"Exemplar not found (neither a file nor a references.yaml id): {spec}")


def split_document(text):
    """Split a draft into ordered chunks, preserving headings verbatim.

    Returns a list of dicts: {heading, body, section} where heading is the
    literal heading line (or None for front matter) and section is the
    classified name used to pick few-shot excerpts.
    """
    matches = list(style.HEADING_RE.finditer(text))
    if not matches:
        return [{"heading": None, "body": text, "section": "other"}]

    def classify(title):
        t = title.lower()
        for name, pat in style.SECTION_PATTERNS:
            if re.search(pat, t):
                return name
        return "other"

    chunks = []
    if matches[0].start() > 0:
        chunks.append({"heading": None, "body": text[:matches[0].start()],
                       "section": "front"})
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append({"heading": m.group(0), "body": text[start:end],
                       "section": classify(m.group(2))})
    return chunks


# --------------------------------------------------------------------------- #
# Blueprint extraction (--exemplar)
# --------------------------------------------------------------------------- #

def extract_blueprint(backend, exemplars, db_dir, name=None):
    """Two-stage extraction. exemplars: list of (id, path). Returns blueprint path."""
    instructions = read(ANALYSIS_MD)
    usage_notes = []

    minis = []
    for ex_id, path in exemplars:
        text = read_prose(path)
        system = (
            "You are the exemplar-extraction stage of the match-outline skill. "
            "Follow Part 3 Stage 1 of the instructions below: produce a "
            "mini-blueprint for the single paper provided, quoting evidence "
            "for every claim. Do not summarize the content; analyze how it "
            f"is written.\n\n{instructions}"
        )
        content = [{
            "type": "text",
            "text": f"# Exemplar paper: {ex_id}\n\n{text}",
            "cache_control": {"type": "ephemeral"},
        }]
        print(f"Extracting style from {ex_id}...", file=sys.stderr)
        mini, usage = call_model(backend, system, content)
        minis.append((ex_id, mini))
        usage_notes.append({"call": f"extract:{ex_id}",
                            "output_tokens": usage.output_tokens})

    if len(minis) == 1:
        ex_id, mini = minis[0]
        blueprint = (
            f"---\nexemplars: [{ex_id}]\ndate: {date.today()}\n"
            "note: single-source — every pattern below is potentially "
            "idiosyncratic to this author\n---\n\n" + mini
        )
    else:
        joined = "\n\n---\n\n".join(
            f"# Mini-blueprint: {ex_id}\n\n{mini}" for ex_id, mini in minis)
        system = (
            "You are the synthesis stage of the match-outline skill. Follow "
            "Part 3 Stage 2 of the instructions below: merge the "
            "mini-blueprints into one consensus blueprint with explicit "
            "Consensus and Idiosyncrasy sections (idiosyncrasies flagged "
            f"with their source paper).\n\n{instructions}"
        )
        print(f"Synthesizing blueprint from {len(minis)} exemplars...",
              file=sys.stderr)
        merged, usage = call_model(backend, system,
                                   [{"type": "text", "text": joined}])
        ids = ", ".join(ex_id for ex_id, _ in minis)
        blueprint = (f"---\nexemplars: [{ids}]\ndate: {date.today()}\n---\n\n"
                     + merged)
        usage_notes.append({"call": "synthesis",
                            "output_tokens": usage.output_tokens})

    slug = name or "-".join(ex_id for ex_id, _ in exemplars)[:60]
    slug = re.sub(r"[^\w.-]", "-", slug)
    out_path = os.path.join(db_dir, f"voice-blueprint-{slug}.md")
    with open(out_path, "w") as f:
        f.write(blueprint)
    return out_path, usage_notes


# --------------------------------------------------------------------------- #
# Rewrite (--rewrite)
# --------------------------------------------------------------------------- #

def find_blueprint(db_dir, explicit=None):
    if explicit:
        if not os.path.exists(explicit):
            sys.exit(f"Blueprint not found: {explicit}")
        return explicit
    candidates = sorted(
        globmod.glob(os.path.join(db_dir, "voice-blueprint-*.md")),
        key=os.path.getmtime, reverse=True)
    if candidates:
        return candidates[0]
    corpus_profile = os.path.join(db_dir, "voice-profile.md")
    if os.path.exists(corpus_profile):
        return corpus_profile
    sys.exit("No blueprint or corpus voice-profile.md found. Run --exemplar "
             "extraction or the corpus profile step first.")


def exemplar_excerpts(source_papers, limit=3):
    """Whole-paper excerpts from source papers: (id, text) list."""
    out = []
    for ex_id, path in source_papers[:limit]:
        text = read_prose(path)
        if text.strip():
            out.append((ex_id, text.strip()[:MAX_EXCERPT_CHARS]))
    return out


def verify_document(original, rewritten):
    """Missing citations and numbers across the whole document."""
    orig_cites = set(style.CITATION_RE.findall(original))
    new_cites = set(style.CITATION_RE.findall(rewritten))
    orig_nums = set(NUMBER_RE.findall(
        style.CITATION_RE.sub(" ", style.strip_markdown(original))))
    new_nums = set(NUMBER_RE.findall(
        style.CITATION_RE.sub(" ", style.strip_markdown(rewritten))))
    return {
        "missing_citations": sorted(orig_cites - new_cites),
        "missing_numbers": sorted(orig_nums - new_nums),
    }


def _strip_added_bold(original, rewritten):
    """Remove bold spans the model added that the original did not have."""
    orig_bold = len(BOLD_RE.findall(original))
    new_bold = len(BOLD_RE.findall(rewritten))
    if new_bold > orig_bold:
        return BOLD_RE.sub(r"\2", rewritten)
    return rewritten


def rewrite_draft(backend, draft_path, blueprint_path, source_papers, mimic):
    """Whole-document rewrite. Returns (out_path, verification, out_tokens)."""
    draft_text = read(draft_path)
    blueprint = read(blueprint_path)
    application = read(APPLICATION_MD)

    mimic_note = (
        "Mimic mode is ON: apply both Consensus and Idiosyncrasy patterns."
        if mimic else
        "Mimic mode is OFF: apply Consensus patterns only; ignore "
        "Idiosyncrasy patterns."
    )

    excerpts = exemplar_excerpts(source_papers)
    excerpt_block = "\n\n---\n\n".join(
        f"### Exemplar: {ex_id} — do NOT reuse its phrasing\n\n{text}"
        for ex_id, text in excerpts) or "(no exemplar available)"

    system = [{
        "type": "text",
        "text": (f"{application}\n\n{mimic_note}\n\n"
                 f"# Voice blueprint\n\n{blueprint}\n\n"
                 f"# Exemplar papers\n\n{excerpt_block}\n\n"
                 "CRITICAL: Do not add bold (**) formatting that the "
                 "original does not have."),
        "cache_control": {"type": "ephemeral"},
    }]

    content = [{
        "type": "text",
        "text": (f"# Draft to rewrite\n\n{read_prose(draft_path)}\n\n"
                 "Rewrite the entire document now, following the critical "
                 "rules. Preserve all headings. You may freely restructure "
                 "paragraphs — merge, split, or reshuffle as the voice "
                 "demands. Output only the rewritten document."),
    }]
    print(f"Rewriting {draft_path} (whole document)...", file=sys.stderr)
    new_text, usage = call_model(backend, system, content, max_tokens=32000)

    new_text = _strip_added_bold(draft_text, new_text.strip())
    verification = verify_document(read_prose(draft_path), new_text)

    fm_match = _FM.match(draft_text)
    front_matter = fm_match.group(0) if fm_match else ""

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(draft_path)),
        os.path.splitext(os.path.basename(draft_path))[0] + "-rewritten.md")
    with open(out_path, "w") as f:
        f.write(front_matter + new_text)
    return out_path, verification, usage.output_tokens


# --------------------------------------------------------------------------- #
# Compare (default mode)
# --------------------------------------------------------------------------- #

def run_style(args_list):
    result = subprocess.run(
        [sys.executable, STYLE_PY] + args_list,
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0:
        sys.exit(f"style.py failed: {result.stderr.strip()}")
    return result.stdout


def excerpt_paper(path, section_texts):
    ordered = ["intro", "methodology", "results", "conclusion"]
    parts = []
    for name in ordered:
        if name in section_texts:
            parts.append(f"### [{name}]\n{section_texts[name].strip()}")
    if not parts:
        return read_prose(path)[:MAX_EXCERPT_CHARS]
    return "\n\n".join(parts)[:MAX_EXCERPT_CHARS]


def load_corpus(db_path, voice_dir=None, role=None, tags=None, pre_ai=None):
    if voice_dir:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        corpus = style.select_voice_corpus(voice_dir, role=role,
                                           tags=tag_list, pre_ai=pre_ai)
        if not corpus:
            sys.exit(f"No exemplars found in {voice_dir}/manifest.yaml "
                     f"matching role={role}, tags={tags}, stratum={pre_ai}")
    else:
        corpus = style.select_corpus(db_path)
        if not corpus:
            sys.exit("No corpus papers found (need status: summarized entries "
                     f"with md_path in {db_path}). Run update-references first.")
    blocks, total = [], 0
    for entry, md_path in corpus:
        label = entry.get("id") or os.path.basename(md_path)
        title = entry.get("title") or entry.get("notes") or ""
        text = read(md_path)
        excerpt = excerpt_paper(md_path, style.detect_sections(text))
        block = f"## Corpus paper: {label} — {title}\n\n{excerpt}"
        if total + len(block) > MAX_CORPUS_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks), len(blocks)


def run_compare(backend, args, db_dir):
    if not args.voice_dir:
        run_style(["--db", args.db, "corpus"])
        metric_diff = run_style(["--db", args.db, "compare", args.draft])
    else:
        metric_diff = "{}"
    pre_ai = (True if args.stratum == "pre-ai"
              else False if args.stratum == "ai-era" else None)
    corpus_block, n_papers = load_corpus(
        args.db, voice_dir=args.voice_dir, role=args.role,
        tags=args.anchor_tags, pre_ai=pre_ai)
    print(f"Corpus: {n_papers} papers; comparing {args.draft}", file=sys.stderr)

    system = (
        "You are the qualitative analysis layer of the match-outline skill. "
        "Follow the instructions and report template below exactly. "
        "Produce ONLY the comparison report markdown (Part 2), using the "
        "corpus papers to ground every claim with quotes.\n\n"
        f"{read(ANALYSIS_MD)}\n\n---\n\n{read(REPORT_TEMPLATE)}"
    )
    content = [
        {"type": "text",
         "text": f"# Corpus papers ({n_papers})\n\n{corpus_block}",
         "cache_control": {"type": "ephemeral"}},
        {"type": "text",
         "text": (f"# Quantitative diff (style.py compare)\n\n```json\n{metric_diff}\n```\n\n"
                  f"# Draft to compare\n\n{read_prose(args.draft)}\n\n"
                  f"Today's date: {date.today()}. Write the comparison report now.")},
    ]
    report, usage = call_model(backend, system, content)

    stem = os.path.splitext(os.path.basename(args.draft))[0]
    out_path = args.out or os.path.join(db_dir, "voice-reports", f"{stem}-voice.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)
    return {"report": out_path, "corpus_papers": n_papers,
            "output_tokens": usage.output_tokens}


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="Whole-document voice analysis, blueprint extraction, and rewrite")
    p.add_argument("draft", nargs="?", help="path to the draft markdown file")
    p.add_argument("--db", default="references.yaml")
    p.add_argument("--out", default=None, help="comparison report output path")
    p.add_argument("--exemplar", action="append", default=[],
                   help="exemplar paper (path or citation id); repeatable")
    p.add_argument("--name", default=None, help="slug for the blueprint filename")
    p.add_argument("--rewrite", action="store_true",
                   help="apply the blueprint (or corpus profile) to the draft")
    p.add_argument("--blueprint", default=None,
                   help="blueprint to apply (default: most recent voice-blueprint-*.md, else voice-profile.md)")
    p.add_argument("--mimic", action="store_true",
                   help="also apply single-author idiosyncrasies")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="model for generation (default: claude-sonnet-5 via "
                        "Anthropic API; pass a non-claude name to use Ollama)")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                   help="Ollama endpoint (ignored for claude-* models)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help="seconds to wait on one Ollama generation call "
                        "(default: %(default)s, or MATCH_OUTLINE_TIMEOUT). "
                        "--rewrite output scales with the document, so a long "
                        "chapter on a local model needs more than the default")
    p.add_argument("--voice-dir", default=None,
                   help="writing-voice directory (alternative to --db)")
    p.add_argument("--role", default=None,
                   choices=["author-voice", "venue-voice"],
                   help="filter voice corpus by role")
    p.add_argument("--anchor-tags", default=None,
                   help="comma-separated register tags for voice corpus")
    p.add_argument("--stratum", default=None,
                   choices=["pre-ai", "ai-era"],
                   help="filter voice corpus by era")
    args = p.parse_args()

    if not args.draft and not args.exemplar:
        p.error("provide a draft, --exemplar papers, or both")
    if args.rewrite and not args.draft:
        p.error("--rewrite requires a draft")

    db_dir = (os.path.abspath(args.voice_dir) if args.voice_dir
              else os.path.dirname(os.path.abspath(args.db)))

    if _is_claude(args.model):
        backend = {"type": "claude", "model": args.model,
                   "client": _get_anthropic_client()}
    else:
        if MATCH_VOICE not in sys.path:
            sys.path.insert(0, MATCH_VOICE)
        import rewrite as rw
        ok, msg = rw.check_server(args.endpoint, args.model)
        if not ok:
            sys.exit(msg)
        print(f"model: {msg}", file=sys.stderr)
        backend = {"type": "ollama", "model": args.model,
                   "endpoint": args.endpoint, "timeout": args.timeout}

    summary = {}

    exemplars = [resolve_paper(spec, args.db) for spec in args.exemplar]

    if exemplars:
        blueprint_path, usage_notes = extract_blueprint(
            backend, exemplars, db_dir, name=args.name)
        summary["blueprint"] = blueprint_path
        summary["extraction_calls"] = usage_notes
        if args.blueprint is None:
            args.blueprint = blueprint_path

    if args.rewrite:
        blueprint_path = find_blueprint(db_dir, args.blueprint)
        if exemplars:
            source_papers = exemplars
        elif args.voice_dir:
            pre_ai = (True if args.stratum == "pre-ai"
                      else False if args.stratum == "ai-era" else None)
            tag_list = ([t.strip() for t in args.anchor_tags.split(",")]
                        if args.anchor_tags else None)
            source_papers = [
                (e.get("id") or os.path.basename(p), p)
                for e, p in style.select_voice_corpus(
                    args.voice_dir, role=args.role, tags=tag_list,
                    pre_ai=pre_ai)][:3]
        else:
            source_papers = [
                (e.get("id"), path)
                for e, path in style.select_corpus(args.db)][:3]
        out_path, verification, out_tokens = rewrite_draft(
            backend, args.draft, blueprint_path, source_papers, args.mimic)
        summary["rewritten"] = out_path
        summary["blueprint_used"] = blueprint_path
        if verification["missing_citations"] or verification["missing_numbers"]:
            summary["verification"] = verification
        else:
            summary["verification"] = "all citations and numbers preserved"
        summary["output_tokens"] = out_tokens

        against = [(ex_id, read_prose(path)) for ex_id, path in source_papers]
        sim = style.similarity_report(
            read_prose(out_path), against, n=8, baseline_text=read_prose(args.draft))
        flagged = sim["total_flagged_matches"]
        summary["similarity"] = {
            "flagged_matches": flagged,
            "sources": [
                {"source": s["source"],
                 "matches": [m["text"] for m in s["matches"]],
                 "overlap_ratio": s["shingle_overlap_ratio"]}
                for s in sim["sources"] if s["matches"]
            ],
        }
        if flagged:
            print(f"\nWARNING: {flagged} passage(s) in the rewrite match a "
                  "source paper. Rephrase or quote them before using the "
                  "rewritten draft.", file=sys.stderr)

    elif args.draft:
        summary["compare"] = run_compare(backend, args, db_dir)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
