#!/usr/bin/env python3
"""Extract citations from a markdown or LaTeX document.

Markdown: pandoc syntax ([@id], [@id1; @id2], inline @id).
LaTeX: natbib syntax (\\citep{a,b}, \\citet{a}, \\citep[see][]{a}).
Dispatched by file extension; both emit the same JSON schema — one object per
(citation_id, line) with the surrounding context and claim sentence.

Usage:
    python3 extract_citations.py <document.md | document.tex>

Output is JSON to stdout, one object per citation occurrence:
    [
      {
        "citation_id": "smith-agents-2025",
        "line": 42,
        "context": "the full paragraph containing the citation",
        "claim": "the sentence containing the citation"
      },
      ...
    ]

Pure stdlib — no dependencies.
"""

import json
import re
import sys

BRACKET_CITE = re.compile(r"\[([^\]]*@[^\]]+)\]")
NATBIB_TOKEN = re.compile(r"\[CITE:[pt]:([^\]]+)\]")
CITE_ID = re.compile(r"@([\w][\w:.#$%&\-+?<>~/]*)")
INLINE_CITE = re.compile(r"(?<!\[)@([\w][\w:.#$%&\-+?<>~/]*)(?![;\]@])")


def extract_sentences(text):
    """Split text into sentences, preserving abbreviations."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z@\[])", text)
    return [s.strip() for s in parts if s.strip()]


def find_claim(paragraph, citation_id):
    """Find the sentence containing the citation within a paragraph."""
    sentences = extract_sentences(paragraph)
    for sentence in sentences:
        if citation_id in sentence or f"@{citation_id}" in sentence:
            return sentence
    return paragraph.strip()


def extract_citations(filepath):
    with open(filepath) as f:
        lines = f.readlines()

    full_text = "".join(lines)
    paragraphs = re.split(r"\n\s*\n", full_text)
    para_starts = []
    pos = 0
    for para in paragraphs:
        idx = full_text.index(para, pos)
        start_line = full_text[:idx].count("\n") + 1
        para_starts.append((start_line, para))
        pos = idx + len(para)

    results = []
    seen = set()

    for line_num, line in enumerate(lines, 1):
        in_code = False
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        bracket_matches = BRACKET_CITE.finditer(line)
        for m in bracket_matches:
            bracket_content = m.group(1)
            ids = CITE_ID.findall(bracket_content)
            for cid in ids:
                key = (cid, line_num)
                if key in seen:
                    continue
                seen.add(key)
                para_context = ""
                for pstart, ptxt in para_starts:
                    if pstart <= line_num <= pstart + ptxt.count("\n"):
                        para_context = " ".join(ptxt.split())
                        break
                results.append({
                    "citation_id": cid,
                    "line": line_num,
                    "context": para_context or line.strip(),
                    "claim": find_claim(para_context or line, cid),
                })

        inline_matches = INLINE_CITE.finditer(line)
        for m in inline_matches:
            cid = m.group(1)
            key = (cid, line_num)
            if key in seen:
                continue
            seen.add(key)
            para_context = ""
            for pstart, ptxt in para_starts:
                if pstart <= line_num <= pstart + ptxt.count("\n"):
                    para_context = " ".join(ptxt.split())
                    break
            results.append({
                "citation_id": cid,
                "line": line_num,
                "context": para_context or line.strip(),
                "claim": find_claim(para_context or line, cid),
            })

    return results


def _clean(text):
    """Render detex citation tokens out of a context/claim string."""
    return " ".join(NATBIB_TOKEN.sub("", text).split()).strip()


def extract_natbib(filepath):
    """Extract natbib \\citep/\\citet citations from a .tex file.

    Uses the detex line-preserving prose view (keep_cites=True), where each
    cite becomes a [CITE:type:keys] token at its source line. Emits the same
    schema as the pandoc path: one object per (key, line), with the paragraph
    as context and the containing sentence as the claim, both markup-free.
    """
    import detex  # copied into this skill's scripts (same dir)
    with open(filepath) as f:
        tex = f.read()
    aligned = detex.detex_aligned(tex, keep_cites=True)  # index i -> source line i+1
    full_text = "\n".join(aligned)

    paragraphs = re.split(r"\n\s*\n", full_text)
    para_starts = []
    pos = 0
    for para in paragraphs:
        idx = full_text.index(para, pos)
        start_line = full_text[:idx].count("\n") + 1
        para_starts.append((start_line, para))
        pos = idx + len(para)

    results = []
    seen = set()
    for line_num, line in enumerate(aligned, 1):
        for m in NATBIB_TOKEN.finditer(line):
            for cid in (k.strip() for k in m.group(1).split(",") if k.strip()):
                key = (cid, line_num)
                if key in seen:
                    continue
                seen.add(key)
                para_context = ""
                for pstart, ptxt in para_starts:
                    if pstart <= line_num <= pstart + ptxt.count("\n"):
                        para_context = " ".join(ptxt.split())
                        break
                claim = find_claim(para_context or line, m.group(0))
                results.append({
                    "citation_id": cid,
                    "line": line_num,
                    "context": _clean(para_context or line),
                    "claim": _clean(claim),
                })
    return results


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} <document.md | document.tex>")
    filepath = sys.argv[1]
    if filepath.endswith(".tex"):
        citations = extract_natbib(filepath)
    else:
        citations = extract_citations(filepath)
    print(json.dumps(citations, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
