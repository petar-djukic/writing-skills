#!/usr/bin/env python3
"""abstract-check.py — mechanical checks for de-ai's abstract mode.

Locates the abstract, counts words against the venue limit, and runs the
content-traceability check: every number in the abstract must appear in the
paper body (no new claims in a rewrite). The four-move analysis and any
rewrite are the model's job (see perplexity-prompts.md); this script covers
what is mechanical.

Usage:
    abstract-check.py PAPER_OR_ABSTRACT.md [--body FILE ...] [--limit 200] [--json]

Locator order: \\begin{abstract} ... \\end{abstract}, pandoc front-matter
`abstract:` key, an "Abstract" heading's section, else the whole file is
treated as the abstract (explicit-path mode).

Exit codes: 0 = all checks pass, 1 = over limit or untraceable numbers,
2 = usage / abstract not found.
"""

import argparse
import json
import re
import sys

import detex  # LaTeX -> prose preprocessing (same dir)

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*%?")
CITE_RE = re.compile(r"\[@[^\]]+\]|\\cite\w*\{[^}]*\}|\[\d+(?:\s*,\s*\d+)*\]")
SECTION_REF_RE = re.compile(r"\b[Ss]ection\s+\d|\\ref\{|Figure\s+\d|Table\s+\d")


def locate_abstract(text):
    """Return (abstract_text, how). Falls back to the whole file."""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL)
    if m:
        # Strip the LaTeX inside the environment (inline \textbf, \citep, etc.)
        # to the prose view, so word counts and number traceability are clean.
        inner = detex.detex(m.group(1))[0]
        return inner.strip(), "latex-environment"

    m = re.search(r"(?:^|\n)abstract:\s*(\||>-?)?\n((?:[ \t]+\S[^\n]*\n?)+)",
                  text)
    if m:
        return re.sub(r"\n[ \t]+", " ", m.group(2)).strip(), "front-matter"

    m = re.search(r"(?:^|\n)(?:#{1,4}\s*|\*\*)[Aa]bstract\b[*:]*[^\n]*\n+(.*?)(?=\n#{1,4}\s|\Z)",
                  text, re.DOTALL)
    if m:
        return m.group(1).strip(), "heading"

    return text.strip(), "whole-file"


def strip_noise(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    return text


def numbers_in(text):
    """Numbers with light normalization; years inside citations excluded."""
    text = CITE_RE.sub(" ", text)
    return set(NUMBER_RE.findall(text))


def self_containedness(abstract):
    """Zobel sweep: things an abstract must not lean on."""
    findings = []
    for c in CITE_RE.findall(abstract):
        findings.append({"kind": "citation", "text": c})
    for m in SECTION_REF_RE.finditer(abstract):
        findings.append({"kind": "internal-reference", "text": m.group(0)})
    return findings


def main():
    p = argparse.ArgumentParser(description="Mechanical abstract checks")
    p.add_argument("paper", help="file containing the abstract (or the abstract itself)")
    p.add_argument("--body", nargs="*", default=[],
                   help="paper body files — source of truth for numbers")
    p.add_argument("--limit", type=int, default=200, help="venue word limit")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    text = open(args.paper).read()
    abstract, how = locate_abstract(text)
    if not abstract:
        print("Abstract not found.", file=sys.stderr)
        sys.exit(2)
    abstract_clean = strip_noise(abstract)

    words = len(re.findall(r"\S+", abstract_clean))
    over = words > args.limit

    abs_numbers = numbers_in(abstract_clean)
    untraceable = []
    if args.body:
        body_numbers = set()
        for b in args.body:
            raw = open(b).read()
            # LaTeX body: use the prose view so citation years / ref numbers
            # (\citep{smith2020}, \ref{fig:3}) don't seed phantom numbers.
            body_text = detex.detex(raw)[0] if b.endswith(".tex") else raw
            body_numbers |= numbers_in(strip_noise(body_text))
        untraceable = sorted(n for n in abs_numbers if n not in body_numbers)

    containedness = self_containedness(abstract_clean)

    result = {
        "located_via": how,
        "word_count": words,
        "limit": args.limit,
        "over_limit": over,
        "numbers": sorted(abs_numbers),
        "untraceable_numbers": untraceable,
        "self_containedness_findings": containedness,
        "abstract": abstract_clean,
    }
    failed = over or bool(untraceable) or bool(containedness)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Abstract located via: {how}")
        print(f"Word count: {words} / {args.limit}"
              + ("  OVER LIMIT" if over else ""))
        if args.body:
            if untraceable:
                print(f"UNTRACEABLE numbers (absent from body): {untraceable}")
            else:
                print("All abstract numbers trace to the body.")
        for f in containedness:
            print(f"Self-containedness: {f['kind']} in abstract: {f['text']}")
        if not failed:
            print("Mechanical checks pass.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
