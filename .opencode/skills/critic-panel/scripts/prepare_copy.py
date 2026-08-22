#!/usr/bin/env python3
"""Build the critics' reading copy of an article (GH-75).

Strips front matter and the REFERENCES tail, collapses figures to [figure],
marks locked spans as [[LOCKED: ... :LOCKED]] so critics can see what is
off-limits, and drops other HTML comments. Writes <stem>.critic-copy.md.
"""
import argparse
import os
import re


def prepare(text):
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            text = parts[1]
    text = text.split("\n## REFERENCES")[0]
    text = re.sub(r"<!--\s*lock\s*-->", "[[LOCKED: ", text)
    text = re.sub(r"<!--\s*/lock\s*-->", " :LOCKED]]", text)
    text = re.sub(r"<!--[^>]*-->", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[figure]", text)
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
