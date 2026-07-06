#!/usr/bin/env python3
"""Headless voice driver for the match-voice skill.

Three modes, composable:

  compare (default)      Qualitative comparison of a draft against the
                         corpus voice profile. One API call.
  --exemplar P [...]     Extract a voice persona blueprint from one or more
                         exemplar papers: one extraction call per exemplar,
                         plus a synthesis call when there are several.
                         Writes voice-blueprint-<slug>.md.
  --rewrite              Apply a blueprint (or the corpus profile) to the
                         draft, section by section, one API call per
                         section. Writes <draft-stem>-rewritten.md, then
                         verifies content preservation (citations, numbers)
                         and runs the similarity plagiarism guard.

All analysis instructions are read at runtime from the skill's own
references/ files — the same files the interactive skill uses — so there is
exactly one source of truth.

Usage:
    match_voice.py DRAFT.md                          # compare
    match_voice.py --exemplar P1 --exemplar P2       # extract blueprint
    match_voice.py DRAFT.md --rewrite                # rewrite w/ latest blueprint
    match_voice.py DRAFT.md --exemplar P1 --rewrite  # extract + rewrite

Requires: ANTHROPIC_API_KEY (or an active `ant auth login` profile),
the `anthropic` package, and PyYAML.
"""

import argparse
import glob as globmod
import json
import os
import re
import subprocess
import sys
from datetime import date

try:
    import anthropic
except ImportError:
    sys.exit("The anthropic package is required. Install with: python3 -m pip install --user anthropic")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_PY = os.path.join(SKILL_DIR, "scripts", "style.py")
ANALYSIS_MD = os.path.join(SKILL_DIR, "references", "voice-analysis-instructions.md")
APPLICATION_MD = os.path.join(SKILL_DIR, "references", "style-application-instructions.md")
REPORT_TEMPLATE = os.path.join(SKILL_DIR, "references", "comparison-report-template.md")

MODEL = "claude-opus-4-8"
MAX_EXCERPT_CHARS = 12000          # per paper in comparison mode
MAX_CORPUS_CHARS = 350000          # ~100K tokens
FEWSHOT_CHARS = 2500               # per exemplar excerpt in rewrite prompts

sys.path.insert(0, os.path.dirname(STYLE_PY))
import style  # noqa: E402  (section detection, corpus selection, similarity)

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def read(path):
    with open(path) as f:
        return f.read()


def call_model(client, system, content_blocks, max_tokens=16000):
    """One streamed API call; system may be a string or content-block list."""
    with client.messages.stream(
        model=MODEL,
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

def extract_blueprint(client, exemplars, db_dir, name=None):
    """Two-stage extraction. exemplars: list of (id, path). Returns blueprint path."""
    instructions = read(ANALYSIS_MD)
    usage_notes = []

    minis = []
    for ex_id, path in exemplars:
        text = read(path)
        system = (
            "You are the exemplar-extraction stage of the match-voice skill. "
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
        mini, usage = call_model(client, system, content)
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
            "You are the synthesis stage of the match-voice skill. Follow "
            "Part 3 Stage 2 of the instructions below: merge the "
            "mini-blueprints into one consensus blueprint with explicit "
            "Consensus and Idiosyncrasy sections (idiosyncrasies flagged "
            f"with their source paper).\n\n{instructions}"
        )
        print(f"Synthesizing blueprint from {len(minis)} exemplars...",
              file=sys.stderr)
        merged, usage = call_model(client, system,
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


def fewshot_excerpts(source_papers, section_name, limit=3):
    """Excerpts of a given section type from source papers: (id, text) list."""
    out = []
    for ex_id, path in source_papers[:limit]:
        sections = style.detect_sections(read(path))
        sec = sections.get(section_name)
        if sec and len(sec.strip()) > 200:
            out.append((ex_id, sec.strip()[:FEWSHOT_CHARS]))
    return out


def verify_section(original, rewritten):
    """Missing citations and numbers: what the rewrite dropped."""
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


def rewrite_draft(client, draft_path, blueprint_path, source_papers, mimic):
    """Section-by-section rewrite. Returns (out_path, verification, out_tokens)."""
    draft_text = read(draft_path)
    blueprint = read(blueprint_path)
    application = read(APPLICATION_MD)

    mimic_note = (
        "Mimic mode is ON: apply both Consensus and Idiosyncrasy patterns."
        if mimic else
        "Mimic mode is OFF: apply Consensus patterns only; ignore "
        "Idiosyncrasy patterns."
    )
    system = [{
        "type": "text",
        "text": (f"{application}\n\n{mimic_note}\n\n"
                 f"# Voice blueprint\n\n{blueprint}"),
        "cache_control": {"type": "ephemeral"},
    }]

    chunks = split_document(draft_text)
    rewritten_parts = []
    verification = {}
    total_out = 0

    for idx, chunk in enumerate(chunks):
        body = chunk["body"]
        if chunk["section"] == "front" or len(body.strip()) < 200:
            rewritten_parts.append((chunk["heading"] or "") + body)
            continue

        excerpts = fewshot_excerpts(source_papers, chunk["section"])
        excerpt_block = "\n\n".join(
            f"### Style demonstration ({ex_id}, {chunk['section']}) — do NOT reuse its phrasing\n\n{text}"
            for ex_id, text in excerpts) or "(no exemplar excerpt available for this section type)"

        content = [{
            "type": "text",
            "text": (f"# Exemplar excerpts for section type '{chunk['section']}'\n\n"
                     f"{excerpt_block}\n\n"
                     f"# Draft section to rewrite (type: {chunk['section']})\n\n"
                     f"{body}\n\n"
                     "Rewrite this section now, following the critical rules. "
                     "Output only the rewritten section body."),
        }]
        print(f"Rewriting section {idx}: {chunk['section']}...", file=sys.stderr)
        new_body, usage = call_model(client, system, content)
        total_out += usage.output_tokens

        heading = (chunk["heading"] + "\n") if chunk["heading"] else ""
        rewritten_parts.append(f"{heading}\n{new_body.strip()}\n")

        key = f"{idx}:{chunk['section']}"
        verification[key] = verify_section(body, new_body)

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(draft_path)),
        os.path.splitext(os.path.basename(draft_path))[0] + "-rewritten.md")
    with open(out_path, "w") as f:
        f.write("\n".join(rewritten_parts))
    return out_path, verification, total_out


# --------------------------------------------------------------------------- #
# Compare (default mode, from #39)
# --------------------------------------------------------------------------- #

def run_style(args_list):
    result = subprocess.run(
        [sys.executable, STYLE_PY] + args_list,
        capture_output=True, text=True,
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
        return read(path)[:MAX_EXCERPT_CHARS]
    return "\n\n".join(parts)[:MAX_EXCERPT_CHARS]


def load_corpus(db_path):
    corpus = style.select_corpus(db_path)
    if not corpus:
        sys.exit("No corpus papers found (need status: summarized entries "
                 f"with md_path in {db_path}). Run update-references first.")
    blocks, total = [], 0
    for entry, md_path in corpus:
        text = read(md_path)
        excerpt = excerpt_paper(md_path, style.detect_sections(text))
        block = f"## Corpus paper: {entry.get('id')} — {entry.get('title', '')}\n\n{excerpt}"
        if total + len(block) > MAX_CORPUS_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks), len(blocks)


def run_compare(client, args, db_dir):
    run_style(["--db", args.db, "corpus"])
    metric_diff = run_style(["--db", args.db, "compare", args.draft])
    corpus_block, n_papers = load_corpus(args.db)
    print(f"Corpus: {n_papers} papers; comparing {args.draft}", file=sys.stderr)

    system = (
        "You are the qualitative analysis layer of the match-voice skill. "
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
                  f"# Draft to compare\n\n{read(args.draft)}\n\n"
                  f"Today's date: {date.today()}. Write the comparison report now.")},
    ]
    report, usage = call_model(client, system, content)

    stem = os.path.splitext(os.path.basename(args.draft))[0]
    out_path = args.out or os.path.join(db_dir, "voice-reports", f"{stem}-voice.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)
    return {"report": out_path, "corpus_papers": n_papers,
            "output_tokens": usage.output_tokens}


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="Headless voice analysis, blueprint extraction, and rewrite")
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
    args = p.parse_args()

    if not args.draft and not args.exemplar:
        p.error("provide a draft, --exemplar papers, or both")
    if args.rewrite and not args.draft:
        p.error("--rewrite requires a draft")

    db_dir = os.path.dirname(os.path.abspath(args.db))
    client = anthropic.Anthropic()
    summary = {}

    exemplars = [resolve_paper(spec, args.db) for spec in args.exemplar]

    if exemplars:
        blueprint_path, usage_notes = extract_blueprint(
            client, exemplars, db_dir, name=args.name)
        summary["blueprint"] = blueprint_path
        summary["extraction_calls"] = usage_notes
        if args.blueprint is None:
            args.blueprint = blueprint_path

    if args.rewrite:
        blueprint_path = find_blueprint(db_dir, args.blueprint)
        source_papers = exemplars or [
            (e.get("id"), path) for e, path in style.select_corpus(args.db)][:3]
        out_path, verification, out_tokens = rewrite_draft(
            client, args.draft, blueprint_path, source_papers, args.mimic)
        summary["rewritten"] = out_path
        summary["blueprint_used"] = blueprint_path
        summary["verification"] = {
            k: v for k, v in verification.items()
            if v["missing_citations"] or v["missing_numbers"]
        } or "all citations and numbers preserved"
        summary["output_tokens"] = out_tokens

        # Plagiarism guard: rewritten vs every source, baseline = original.
        against = [(ex_id, read(path)) for ex_id, path in source_papers]
        sim = style.similarity_report(
            read(out_path), against, n=8, baseline_text=read(args.draft))
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
        summary["compare"] = run_compare(client, args, db_dir)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
