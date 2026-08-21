#!/usr/bin/env python3
"""Canonical markdown paragraph extractor for the prose skills.

One parser, imported by every consumer that needs "which lines are prose".
Divergent splitters mean divergent bugs: a block one parser calls prose and
another silently skips shifts metrics, anchors, and rewrites in ways nobody
audits. Lifted out of match-voice's drive.py (GH-167) and kept here because
filter-tells is the skill every other prose skill already imports from.

Every body line is classified — prose, heading, figure, figure-caption, table,
code, reference, blockquote, list, rule, blank, locked. The classification
tally is the audit consumers actually read: it answers "what did the parser
decide to skip, and does that match the document" without reading the document.

Locked regions (GH-57): a `<!-- lock -->` marker alone on a line opens a
block lock, `<!-- /lock -->` closes it, and every line between, markers
included, is classified ``locked`` — opaque to paragraph extraction, so no
model-facing consumer ever sees the text. The region is not interpreted:
code fences inside a lock do not toggle code state. Markers inside a code
fence are inert (example text). Nested opens, a close without an open, and
an unclosed open raise span_locks.LockError with line numbers — a document
whose protection markers are broken must not parse quietly.

`unaccounted` is an invariant check, not a live detector. Unrecognised lines
fall through to prose by design (raw HTML, definition lists), so on today's
grammar the list is always empty. It fires only if a future branch `continue`s
without recording coverage — which is exactly the bug that would silently drop
paragraphs, so the check earns its keep as a tripwire.

Front matter (a leading `---` fence) is excluded from the body.

Library:
  parse(text)              -> Result(lines, fm_close, paragraphs, coverage, unaccounted)
  paragraphs(text, n)      -> prose blocks of at least n words
  parse_file(path)         -> parse() over a file's contents

CLI (coverage audit):
  md_paragraphs.py <file.md> [--min-words 12] [--json] [--coverage-only]
  exit 1 when any body line is unaccounted for.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, namedtuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import span_locks

Result = namedtuple("Result",
                    "lines fm_close paragraphs coverage unaccounted")

# Line categories, checked in this order. Order matters: a line starting with
# "**Figure" is a caption, not prose, but only after the code-fence and blank
# checks have run.
_CATEGORY_TESTS = (
    # Both spellings: some files carry the bang escaped ("<\!--").
    ("comment", lambda s: s.startswith(("<!--", "<\\!--"))),
    ("heading", lambda s: s.startswith("#")),
    ("figure", lambda s: s.startswith("![")),
    ("table", lambda s: s.startswith("|")),
    ("figure-caption", lambda s: s.startswith("**Figure")),
    ("reference", lambda s: bool(re.match(r"^\[\d+\]", s))),
    ("rule", lambda s: s == "---"),
    ("blockquote", lambda s: s.startswith(">")),
    ("list", lambda s: bool(re.match(r"^([-*+]\s|\d+\.\s)", s))),
)


def _front_matter_close(lines):
    """Index of the closing `---` of front matter, else -1.

    -1, not 0: the body loop starts at fm_close + 1, and returning 0 for "no
    front matter" silently skipped the FIRST LINE of every document that did
    not open with ---. Unnoticed for the extractor's whole life because
    documents usually open with a heading, which is skipped anyway; found by a
    one-line GH-223 control file that parsed to zero paragraphs.
    """
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i
    return -1


def parse(text: str) -> Result:
    """Classify every body line; return prose blocks with 1-indexed line ranges.

    paragraphs entries are [start_line, end_line, text]; coverage maps every
    body line number to its category; unaccounted lists any body line the
    classifier failed to categorise (should always be empty — a nonempty list
    is a parser bug, not a document problem).
    """
    lines = text.split("\n")
    fm_close = _front_matter_close(lines)
    paras, coverage = [], {}
    in_code = False
    lock_open_ln = None
    buf, buf_start = [], None

    def flush():
        nonlocal buf, buf_start
        if buf:
            txt = "\n".join(buf).strip()
            if txt:
                paras.append([buf_start + 1, buf_start + len(buf), txt])
        buf, buf_start = [], None

    for idx in range(fm_close + 1, len(lines)):
        ln, s = idx + 1, lines[idx].strip()
        # A locked region is opaque: nothing inside it is interpreted,
        # including code fences, until the closing marker.
        if lock_open_ln is not None:
            coverage[ln] = "locked"
            if span_locks.is_open_marker(s):
                raise span_locks.LockError(
                    f"nested lock: open at line {ln} inside the lock "
                    f"opened at line {lock_open_ln}")
            if span_locks.is_close_marker(s):
                lock_open_ln = None
            continue
        if s.startswith("```"):
            flush()
            in_code = not in_code
            coverage[ln] = "code"
            continue
        if in_code:
            coverage[ln] = "code"
            continue
        # Lock markers checked before the category tests — the comment
        # category would otherwise swallow them.
        if span_locks.is_open_marker(s):
            flush()
            coverage[ln] = "locked"
            lock_open_ln = ln
            continue
        if span_locks.is_close_marker(s):
            raise span_locks.LockError(
                f"lock close without open at line {ln}")
        if s == "":
            flush()
            coverage[ln] = "blank"
            continue
        cat = next((name for name, test in _CATEGORY_TESTS if test(s)), None)
        if cat:
            flush()
            coverage[ln] = cat
            continue
        if buf_start is None:
            buf_start = idx
        buf.append(lines[idx])
        coverage[ln] = "prose"
    flush()
    if lock_open_ln is not None:
        raise span_locks.LockError(
            f"unclosed lock opened at line {lock_open_ln}")

    unaccounted = [i + 1 for i in range(fm_close + 1, len(lines))
                   if (i + 1) not in coverage]
    return Result(lines, fm_close, paras, coverage, unaccounted)


def parse_file(path: str) -> Result:
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse(f.read())


def paragraphs(text: str, min_words: int = 0):
    """Prose blocks of at least min_words words: [[start, end, text], ...]."""
    return [p for p in parse(text).paragraphs
            if len(p[2].split()) >= min_words]


def main():
    ap = argparse.ArgumentParser(description="markdown paragraph extraction and coverage audit")
    ap.add_argument("file")
    ap.add_argument("--min-words", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--coverage-only", action="store_true",
                    help="report the classification tally and exit nonzero on gaps")
    args = ap.parse_args()

    r = parse_file(args.file)
    kept = [p for p in r.paragraphs if len(p[2].split()) >= args.min_words]
    tally = Counter(r.coverage.values())

    if args.json:
        print(json.dumps({
            "file": args.file,
            "body_lines": len(r.lines) - (r.fm_close + 1),
            "coverage": dict(tally),
            "paragraphs": len(r.paragraphs),
            "paragraphs_at_min_words": len(kept),
            "unaccounted": r.unaccounted,
        }, indent=2))
    else:
        print(f"{args.file}: {len(r.paragraphs)} prose blocks "
              f"({len(kept)} at >= {args.min_words} words)")
        for cat, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"  {cat:16} {n}")
        if r.unaccounted:
            print(f"  UNACCOUNTED body lines: {r.unaccounted[:20]}"
                  f"{' ...' if len(r.unaccounted) > 20 else ''}")
        elif args.coverage_only:
            print("  every body line classified")

    sys.exit(1 if r.unaccounted else 0)


if __name__ == "__main__":
    main()
