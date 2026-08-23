#!/usr/bin/env python3
"""Build the critics' reading copy of an article (GH-75).

Strips front matter and the REFERENCES tail, collapses figures to [figure],
marks locked spans as [[LOCKED: ... :LOCKED]] so critics can see what is
off-limits, and drops other HTML comments. Writes <stem>.critic-copy.md.
"""
import argparse
import os
import re


def _balanced(text, i, open_ch, close_ch):
    """Index just past the delimiter opened at `text[i]`, or None if unclosed.

    `i` must be the opening character. Counts depth, so a nested pair inside
    does not end the span early.
    """
    depth = 0
    while i < len(text):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def collapse_figures(text):
    """Replace every `![label](destination)` with `[figure]`.

    A scan rather than a regex, because both halves nest and a character class
    cannot count (GH-102). `![^\\]]*` stopped at the first `]`, so alt text
    carrying a citation — `![see [1] for detail](fig.png)` — matched nothing
    and the whole construct reached the critics as prose, markdown and URL
    included. `[^)]*` stopped at the first `)`, so a parenthesised filename
    left `.png)` behind. CommonMark resolves both by counting balance, which
    is what this does.

    An unterminated construct is left exactly as it stands. Consuming to the
    end of the document would delete the article to tidy a caption — the same
    reasoning that kept the comment strip non-greedy in GH-96, where a fix
    that could eat everything between two markers was worse than the bug.

    Not handled, deliberately: CommonMark's `<...>` destination form. It
    appears nowhere in the corpora this runs on, and adding it without a case
    to test against is speculation.
    """
    out, i = [], 0
    while True:
        j = text.find("![", i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        label_end = _balanced(text, j + 1, "[", "]")
        if label_end is None or label_end >= len(text) or text[label_end] != "(":
            # Not a figure, or unterminated: emit `![` and keep scanning after
            # it, so a stray bracket costs two characters rather than the rest
            # of the document.
            out.append(text[i:j + 2])
            i = j + 2
            continue
        dest_end = _balanced(text, label_end, "(", ")")
        if dest_end is None:
            out.append(text[i:j + 2])
            i = j + 2
            continue
        out.append(text[i:j])
        out.append("[figure]")
        i = dest_end


def prepare(text):
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            text = parts[1]
    text = text.split("\n## REFERENCES")[0]
    # Locks first: once converted they carry no `<!--`, so the general strip
    # below cannot reach them. Reordering these three lines deletes the locks.
    text = re.sub(r"<!--\s*lock\s*-->", "[[LOCKED: ", text)
    text = re.sub(r"<!--\s*/lock\s*-->", " :LOCKED]]", text)
    # Non-greedy and dot-all, not `[^>]*` (GH-96). A negated class stops at the
    # first `>`, so a reverse-outline marker carrying `-> n` never matched at
    # all and reached the critics whole — 19 of them on one 5,500-word article,
    # read as if they were prose. Greedy `.*` would be worse than the bug: it
    # would swallow every line between the first comment and the last.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = collapse_figures(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article")
    ap.add_argument("--out")
    a = ap.parse_args()
    with open(a.article, encoding="utf-8") as f:
        out = prepare(f.read())
    path = a.out or os.path.splitext(a.article)[0] + ".critic-copy.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"{path}  ({len(out.split())} words, "
          f"{out.count('[[LOCKED:')} locked spans)")


if __name__ == "__main__":
    main()
