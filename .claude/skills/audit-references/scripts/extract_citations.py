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
# Inline @key outside any bracket. No trailing lookahead: bracket content is
# masked out before this runs (see mask_brackets), and a lookahead here would
# make the regex backtrack into the key rather than skip the match — which is
# how the last key of every multi-key bracket came out one character short.
INLINE_CITE = re.compile(r"(?<![\[\w])@([\w][\w:.#$%&\-+?<>~/]*)")

# A pandoc key may contain these internally but never ends with one, so a
# trailing run is sentence punctuation the greedy match swallowed.
KEY_TRAILING = ":.#$%&-+?<>~/"


def trim_key(cid):
    """Drop trailing punctuation the character class let in.

    `@nygard-2011.` at the end of a sentence must yield `nygard-2011`, not
    `nygard-2011.` — the latter resolves against nothing and is reported as a
    missing reference the author never wrote.
    """
    return cid.rstrip(KEY_TRAILING)


def mask_brackets(line):
    """Blank out bracketed citation spans, preserving offsets and length.

    Inline detection runs over the result. Masking rather than filtering is
    what keeps the two passes from seeing the same text: previously the
    lookahead tried to do this job and mutilated keys instead of skipping them.
    """
    out = line
    for m in BRACKET_CITE.finditer(line):
        out = out[:m.start()] + (" " * (m.end() - m.start())) + out[m.end():]
    return out


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
    # Fence state spans lines. Initialising it inside the loop reset it every
    # iteration, so the skip only ever applied to the fence line itself and
    # every citation inside a code block was extracted as real.
    in_code = False

    for line_num, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        def emit(cid):
            cid = trim_key(cid)
            if not cid:
                return
            key = (cid, line_num)
            if key in seen:
                return
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

        for m in BRACKET_CITE.finditer(line):
            for cid in CITE_ID.findall(m.group(1)):
                emit(cid)

        # Inline pass sees the line with bracket spans blanked, so a key inside
        # a bracket cannot be re-matched here in mangled form.
        for m in INLINE_CITE.finditer(mask_brackets(line)):
            emit(m.group(1))

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
