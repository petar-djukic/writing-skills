#!/usr/bin/env python3
"""Obsidian keyword tagging and source linking for the update-references skill.

Extracts keywords from each paper and writes them as normalized Obsidian
`tags:` in the summary's YAML frontmatter, and adds relative links from the
summary to its PDF, converted markdown, and source URL (plus a back-link to the
PDF at the top of the converted markdown). Tags and links are merged
idempotently — a re-run adds nothing new and never drops a human-added tag.

Subcommands:
  tag   Walk the db, tag and link every summary. Use --dry-run to preview.

Stdlib only except PyYAML.
"""

import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with: python3 -m pip install --user pyyaml")

FREQ_MAX = 8
ROOT_TAG = "paper"

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "as", "at", "is", "are", "be", "we", "our", "this", "that", "these", "those",
    "from", "it", "its", "can", "which", "such", "using", "used", "use", "based",
    "than", "then", "also", "not", "but", "into", "over", "more", "most", "each",
    "via", "their", "they", "them", "he", "she", "his", "her", "was", "were",
    "has", "have", "had", "will", "would", "may", "might", "one", "two", "three",
    "paper", "method", "approach", "results", "show", "propose", "present", "new",
    "model", "models", "task", "tasks", "data", "set", "given", "however",
    "between", "both", "all", "some", "other", "when", "where", "how", "what",
}


def load_db(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "papers" in data:
        return data["papers"]
    return []


def normalize_tag(text):
    """Obsidian tag form: lowercase, hyphenated, alnum (hierarchy `/` kept)."""
    t = text.strip().lower()
    t = re.sub(r"[^a-z0-9/]+", "-", t)
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return t


def _declared_keywords(paper_text):
    """Keywords the paper declares in a Keywords / Index Terms line."""
    if not paper_text:
        return []
    m = re.search(r"(?im)^\s*(?:keywords|key words|index terms)\s*[:—-]\s*(.+)$",
                  paper_text)
    if not m:
        return []
    return re.split(r"[;,—]|\s{2,}", m.group(1))


def _frequency_terms(paper_text, limit=FREQ_MAX):
    """Lightweight fallback: most frequent content unigrams and bigrams."""
    if not paper_text:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", paper_text.lower())
    content = [w for w in words if w not in _STOPWORDS]
    counts = {}
    for w in content:
        counts[w] = counts.get(w, 0) + 1
    # adjacent content-word bigrams (from the original stream, no stopword gap)
    for a, b in zip(content, content[1:]):
        if a != b:
            counts[f"{a} {b}"] = counts.get(f"{a} {b}", 0) + 1
    # prefer multiword phrases and higher counts; require a phrase to recur
    ranked = sorted(counts.items(),
                    key=lambda kv: (kv[1] >= 3, " " in kv[0], kv[1]), reverse=True)
    return [term for term, n in ranked if n >= 3][:limit]


def extract(paper_text, topics):
    """Merged, normalized Obsidian tags for a paper.

    Declared keywords and the entry's topics are the primary source. The
    frequency fallback runs only when the paper declares no keywords, so a
    paper with an explicit keyword list is not diluted with noisy terms.
    """
    raw = list(topics or [])
    declared = _declared_keywords(paper_text)
    raw += declared
    if not declared:
        raw += _frequency_terms(paper_text)
    tags = {normalize_tag(t) for t in raw if t and normalize_tag(t)}
    tags.add(ROOT_TAG)
    return sorted(tags)


def _split_frontmatter(text):
    """Return (frontmatter_dict, body_str). Empty dict if no frontmatter."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm = yaml.safe_load(text[4:end + 1]) or {}
            if isinstance(fm, dict):
                return fm, text[end + 5:]
    return {}, text


def _compose(frontmatter, body):
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm}\n---\n{body}"


def _merge_tags(existing, new):
    """Union of existing (kept verbatim, hierarchy preserved) and new tags."""
    if isinstance(existing, str):
        existing = [existing]
    merged = {t for t in (existing or []) if t}
    merged.update(new)
    return sorted(merged)


def _source_line(entry):
    """A '**Source:**' line linking the pdf, converted markdown, and URL."""
    parts = []
    if entry.get("pdf_path"):
        parts.append(f"[PDF](../{entry['pdf_path']})")
    if entry.get("md_path"):
        parts.append(f"[full text](../{entry['md_path']})")
    if entry.get("URL"):
        parts.append(f"[source]({entry['URL']})")
    return "**Source:** " + " · ".join(parts) if parts else ""


def _apply_source_line(body, line):
    """Insert or replace the Source line at the top of the body, idempotent."""
    if not line:
        return body
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("**Source:**"):
            if ln == line:
                return body
            lines[i] = line
            return "\n".join(lines)
    # insert after leading blank lines
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    lines[idx:idx] = [line, ""]
    return "\n".join(lines)


def _backlink_paper(md_abs, entry, db_dir):
    """Add a single '[PDF](..)' back-link at the top of the paper markdown."""
    if not entry.get("pdf_path") or not os.path.exists(md_abs):
        return False
    with open(md_abs) as f:
        text = f.read()
    rel = os.path.relpath(os.path.join(db_dir, entry["pdf_path"]),
                          os.path.dirname(md_abs))
    if "](../pdfs/" in text[:400] or f"]({rel})" in text[:400]:
        return False
    with open(md_abs, "w") as f:
        f.write(f"[PDF]({rel})\n\n{text}")
    return True


def cmd_tag(args):
    db_dir = os.path.dirname(os.path.abspath(args.db))
    entries = load_db(args.db)
    tagged = 0
    report = []
    for entry in entries:
        summ_rel = entry.get("summary_file")
        if not summ_rel:
            continue
        summ_abs = os.path.join(db_dir, summ_rel)
        if not os.path.exists(summ_abs):
            continue

        paper_text = ""
        md_rel = entry.get("md_path")
        if md_rel and os.path.exists(os.path.join(db_dir, md_rel)):
            with open(os.path.join(db_dir, md_rel)) as f:
                paper_text = f.read()

        new_tags = extract(paper_text, entry.get("topics"))

        with open(summ_abs) as f:
            original = f.read()
        fm, body = _split_frontmatter(original)
        fm["tags"] = _merge_tags(fm.get("tags"), new_tags)
        body = _apply_source_line(body, _source_line(entry))
        updated = _compose(fm, body)

        changed = updated != original
        if args.dry_run:
            if changed:
                report.append({"summary": summ_rel, "tags": fm["tags"]})
        else:
            if changed:
                with open(summ_abs, "w") as f:
                    f.write(updated)
            if md_rel:
                _backlink_paper(os.path.join(db_dir, md_rel), entry, db_dir)
        if changed:
            tagged += 1

    print(json.dumps({"tagged": tagged, "dry_run": bool(args.dry_run),
                      "changes": report}, indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Obsidian keyword tagging for summaries")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tag", help="tag and link every summary in the db")
    t.add_argument("--dry-run", action="store_true",
                   help="preview the tags/links that would be written; change nothing")
    t.set_defaults(func=cmd_tag)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
