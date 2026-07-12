#!/usr/bin/env python3
"""LaTeX -> prose preprocessing for the prose skills (de-ai, match-voice,
audit-references).

The prose skills tokenize sentences, count burstiness, grep for banned words,
and extract citations. Fed raw .tex they misread command names, comments, math,
and float environments as prose. `detex` produces the prose view: the text a
reader sees, with markup removed, so the existing analysis runs unchanged.

It is line-oriented to preserve a line map: prose line k came from source line
`line_map[k]`, so a finding still points at the .tex source. Multi-line drop
environments (math, figure, table, algorithm) are removed but their `\\caption`
text is kept as prose.

Citations are replaced with a stable token so sentence shape survives:
  keep_cites=False (default): \\citep{a,b} / \\citet{a} -> "[CITE]"
  keep_cites=True:            -> "[CITE:p:a,b]" / "[CITE:t:a]"  (audit-references
                                 parses these back to keys + sentence context)

This module is canonical in de-ai/scripts and copied verbatim into the other
skills (skills are mirrored independently, so they cannot share an import).
Stdlib only.
"""

import re

# Environments dropped whole (contents are not prose). Captions are kept.
_DROP_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "math", "displaymath",
    "figure", "figure*", "table", "table*", "tabular", "tabular*", "array",
    "algorithm", "algorithm*", "algorithmic", "tikzpicture", "lstlisting",
    "verbatim", "minted", "thebibliography",
}
# Environments whose \begin/\end markers are dropped but whose text is prose.
# (itemize, enumerate, description, abstract, quote, ... — anything not above.)

_CAPTION_RE = re.compile(r"\\caption\{")
_BEGIN_RE = re.compile(r"\\begin\{([a-zA-Z*]+)\}")
_END_RE = re.compile(r"\\end\{([a-zA-Z*]+)\}")
_CITE_RE = re.compile(r"\\(citep|citet|citealp|citealt|cite)\s*(?:\[[^\]]*\])*\s*\{([^}]*)\}")
_REF_RE = re.compile(r"\\(ref|eqref|autoref|cref|pageref)\s*\{[^}]*\}")
# Inline commands whose single braced argument is kept as text.
_TEXT_CMD_RE = re.compile(
    r"\\(textbf|textit|texttt|textsc|textrm|textsf|emph|text|"
    r"section|subsection|subsubsection|paragraph|title|caption|footnote|"
    r"mbox|underline|uline)\*?\s*\{"
)
# Commands (with any braced/optional args) dropped entirely, argument and all.
_DROP_CMD_RE = re.compile(
    r"\\(label|includegraphics|input|include|usepackage|documentclass|"
    r"bibliography|bibliographystyle|newcommand|renewcommand|def|"
    r"vspace|hspace|centering|noindent|maketitle|tableofcontents|"
    r"item|hline|toprule|midrule|bottomrule|cline)\b(\s*\[[^\]]*\])?(\s*\{[^{}]*\})*"
)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$]*\$|\\\([^)]*\\\)")


def _strip_comment(line: str) -> str:
    """Drop a % comment (a % not escaped as \\%)."""
    out = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if c == "%":
            break
        out.append(c)
        i += 1
    return "".join(out)


def _expand_braced(text: str, match: re.Match) -> str:
    """Replace \\cmd{arg} (match ends at the opening brace) with its arg,
    handling one level of nested braces. Returns the rewritten full string."""
    start = match.start()
    brace = match.end() - 1  # position of '{'
    depth = 0
    i = brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    arg = text[brace + 1:i]
    return text[:start] + arg + text[i + 1:]


def _cite_token(m: re.Match, keep_cites: bool) -> str:
    if not keep_cites:
        return "[CITE]"
    cmd = m.group(1)
    typ = "t" if cmd == "citet" else "p"
    keys = ",".join(k.strip() for k in m.group(2).split(",") if k.strip())
    return f"[CITE:{typ}:{keys}]"


def _transform_inline(line: str, keep_cites: bool) -> str:
    line = _CITE_RE.sub(lambda m: _cite_token(m, keep_cites), line)
    line = _REF_RE.sub("[REF]", line)
    line = _INLINE_MATH_RE.sub("[MATH]", line)
    # expand text commands innermost-first until none remain
    for _ in range(12):
        m = _TEXT_CMD_RE.search(line)
        if not m:
            break
        line = _expand_braced(line, m)
    line = _DROP_CMD_RE.sub("", line)
    # any remaining bare command without args: drop the command token
    line = re.sub(r"\\[a-zA-Z]+\*?", "", line)
    # unescape TeX literals (50\% -> 50%, A\&B -> A&B, \_ -> _, \# -> #, \$ -> $)
    line = re.sub(r"\\([%&_#$~])", r"\1", line)
    line = line.replace("{", "").replace("}", "")
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def detex(tex: str, keep_cites: bool = False):
    """Return (prose, line_map).

    prose is the markup-stripped text, one entry per surviving source line.
    line_map[k] is the 1-based source line number of prose line k.
    """
    lines = tex.split("\n")
    out_text = []
    line_map = []
    drop_depth = 0  # nesting depth inside a _DROP_ENVS environment

    for lineno, raw in enumerate(lines, 1):
        line = _strip_comment(raw)

        if drop_depth > 0:
            # inside a dropped environment: keep only caption text
            if _CAPTION_RE.search(line):
                cap = _transform_inline(line, keep_cites)
                if cap:
                    out_text.append(cap)
                    line_map.append(lineno)
            for m in _END_RE.finditer(line):
                if m.group(1) in _DROP_ENVS:
                    drop_depth -= 1
            for m in _BEGIN_RE.finditer(line):
                if m.group(1) in _DROP_ENVS:
                    drop_depth += 1
            continue

        # not currently dropping: does this line open a drop env?
        begins = _BEGIN_RE.findall(line)
        if any(b in _DROP_ENVS for b in begins):
            # keep any caption on the same line, then enter drop mode
            if _CAPTION_RE.search(line):
                cap = _transform_inline(line, keep_cites)
                if cap:
                    out_text.append(cap)
                    line_map.append(lineno)
            for b in begins:
                if b in _DROP_ENVS:
                    drop_depth += 1
            continue

        # keep-env markers (itemize/abstract/...) — drop just the marker
        line = _BEGIN_RE.sub("", line)
        line = _END_RE.sub("", line)

        prose = _transform_inline(line, keep_cites)
        if prose:
            out_text.append(prose)
            line_map.append(lineno)

    return "\n".join(out_text), line_map


def extract_abstract(tex: str):
    """The text inside \\begin{abstract}...\\end{abstract}, as prose, or None."""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL)
    if not m:
        return None
    prose, _ = detex(m.group(1))
    return prose.strip() or None


if __name__ == "__main__":
    import sys
    keep = "--keep-cites" in sys.argv[1:]
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    for p in paths:
        with open(p) as f:
            prose, _ = detex(f.read(), keep_cites=keep)
        sys.stdout.write(prose + "\n")
