#!/usr/bin/env python3
"""Headless voice-comparison driver for the match-voice skill.

Runs the qualitative comparison layer as a single Anthropic API call, so
voice analysis can run from CI, cron, or a mage target with no interactive
agent session. The quantitative layer (style.py) runs locally first; its
diff is fed to the model alongside corpus excerpts and the draft.

The analysis instructions are read at runtime from the skill's own
references/voice-analysis-instructions.md — the same file the interactive
skill uses — so there is exactly one source of truth.

Usage:
    python3 match_voice.py DRAFT.md [--db references.yaml] [--out report.md]

Requires: ANTHROPIC_API_KEY (or an active `ant auth login` profile),
the `anthropic` package, and PyYAML.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

try:
    import anthropic
except ImportError:
    sys.exit("The anthropic package is required. Install with: python3 -m pip install --user anthropic")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_PY = os.path.join(SKILL_DIR, "scripts", "style.py")
INSTRUCTIONS = os.path.join(SKILL_DIR, "references", "voice-analysis-instructions.md")
REPORT_TEMPLATE = os.path.join(SKILL_DIR, "references", "comparison-report-template.md")

MODEL = "claude-opus-4-8"
MAX_EXCERPT_CHARS = 12000          # per paper
MAX_CORPUS_CHARS = 350000          # ~100K tokens


def run_style(args_list):
    result = subprocess.run(
        [sys.executable, STYLE_PY] + args_list,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"style.py failed: {result.stderr.strip()}")
    return result.stdout


def excerpt_paper(path, section_texts):
    """Excerpt a paper: intro + methodology + results + conclusion.

    Methodology and results are always included since they carry the
    section-analysis weight; falls back to the head of the file when no
    sections were detected.
    """
    ordered = ["intro", "methodology", "results", "conclusion"]
    parts = []
    for name in ordered:
        if name in section_texts:
            parts.append(f"### [{name}]\n{section_texts[name].strip()}")
    if not parts:
        with open(path) as f:
            return f.read()[:MAX_EXCERPT_CHARS]
    text = "\n\n".join(parts)
    return text[:MAX_EXCERPT_CHARS]


def load_corpus(db_path):
    """Load corpus papers (status: summarized, with md_path) and excerpt them."""
    sys.path.insert(0, os.path.dirname(STYLE_PY))
    import style  # reuse selection + section detection

    corpus = style.select_corpus(db_path)
    if not corpus:
        sys.exit("No corpus papers found (need status: summarized entries "
                 f"with md_path in {db_path}). Run update-references first.")

    blocks = []
    total = 0
    for entry, md_path in corpus:
        with open(md_path) as f:
            text = f.read()
        sections = style.detect_sections(text)
        excerpt = excerpt_paper(md_path, sections)
        block = f"## Corpus paper: {entry.get('id')} — {entry.get('title', '')}\n\n{excerpt}"
        if total + len(block) > MAX_CORPUS_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks), len(blocks)


def main():
    p = argparse.ArgumentParser(description="Headless voice comparison")
    p.add_argument("draft", help="path to the draft markdown file")
    p.add_argument("--db", default="references.yaml")
    p.add_argument("--out", default=None,
                   help="report output path (default: <db-dir>/voice-reports/<stem>-voice.md)")
    args = p.parse_args()

    db_dir = os.path.dirname(os.path.abspath(args.db))

    # 1. Quantitative layer: refresh corpus profile, compare draft.
    run_style(["--db", args.db, "corpus"])
    metric_diff = run_style(["--db", args.db, "compare", args.draft])

    # 2. Assemble prompt parts.
    with open(INSTRUCTIONS) as f:
        instructions = f.read()
    with open(REPORT_TEMPLATE) as f:
        template = f.read()
    with open(args.draft) as f:
        draft_text = f.read()

    corpus_block, n_papers = load_corpus(args.db)
    print(f"Corpus: {n_papers} papers; comparing {args.draft}", file=sys.stderr)

    system = (
        "You are the qualitative analysis layer of the match-voice skill. "
        "Follow the instructions and report template below exactly. "
        "Produce ONLY the comparison report markdown (Part 2), using the "
        "corpus papers to ground every claim with quotes.\n\n"
        f"{instructions}\n\n---\n\n{template}"
    )

    # Corpus block is stable across runs while drafts change — cache it.
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"# Corpus papers ({n_papers})\n\n{corpus_block}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"# Quantitative diff (style.py compare)\n\n```json\n{metric_diff}\n```\n\n"
                    f"# Draft to compare\n\n{draft_text}\n\n"
                    f"Today's date: {date.today()}. Write the comparison report now."
                ),
            },
        ],
    }]

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=messages,
    ) as stream:
        response = stream.get_final_message()

    report = next((b.text for b in response.content if b.type == "text"), "")
    if not report.strip():
        sys.exit(f"Empty response (stop_reason: {response.stop_reason})")

    stem = os.path.splitext(os.path.basename(args.draft))[0]
    out_path = args.out or os.path.join(db_dir, "voice-reports", f"{stem}-voice.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)

    print(json.dumps({
        "report": out_path,
        "corpus_papers": n_papers,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": response.usage.cache_read_input_tokens,
            "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
        },
    }, indent=2))


if __name__ == "__main__":
    main()
