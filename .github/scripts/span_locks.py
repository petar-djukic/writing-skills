#!/usr/bin/env python3
"""Span locks — mechanical protection for text no model may rewrite.

A lock is a marker pair in the source document:

    <!-- lock -->hand-written sentence that must survive<!-- /lock -->

Everything between the markers, markers included, is excised before any
model sees the text and spliced back byte-identical afterwards (GH-57).
Protection is enforced here, in the shared drivers, never by prompts: the
Strategy Theatre provenance logs showed every generative stage rewriting
text it was instructed to leave alone, so the invariant is mechanical.

Two placement forms:

- **Block**: each marker alone on its own line. The whole region between
  the marker lines is classified ``locked`` by md_paragraphs.parse and
  never becomes prose — opaque to paragraph extraction and replacement.
  Code fences inside a block lock are not interpreted; lock markers inside
  a code fence are inert (example text, not a lock).
- **Inline**: markers inside a prose paragraph (or a YAML prose scalar).
  The paragraph text handed to callers carries an opaque anchor token
  ``[[LOCK-n]]`` where the span was; the locked bytes stay in a manifest
  and never leave the driver. Replacement text must carry each token
  exactly once — splice() re-expands them and refuses loudly otherwise,
  which is the keep/drop gate for rewrites that ate the anchor.

Nested locks, a close without an open, and an unclosed open are structural
errors, rejected with line numbers (LockError), never ignored. An inline
lock must open and close within one paragraph; spanning a blank line is
the block form's job and fails paragraph-level validation loudly.

Library:
  excise(text, start=1, base_line=1) -> (clean_text, manifest)
  splice(text, manifest)             -> text with tokens re-expanded
  tokens_in(text)                    -> the anchor tokens a text carries
  check_tokens(original, candidate)  -> None, or the token fault to retry on
  verify_preserved(spans, output)    -> locked spans the output lost
  is_open_marker(line) / is_close_marker(line)   whole-line predicates

The last three exist because of GH-82: excise and splice both worked, and
match-voice's markdown path called neither — it read the raw parse and
spliced raw lines, so two inline locks reached the model and came back
edited. check_tokens lets a driver retry before the splice; verify_preserved
checks the bytes actually written, whichever path wrote them.

CLI (audit):
  span_locks.py <file.md|file.yaml> [--json]
  Reports block-locked line ranges and inline lock counts per paragraph;
  exit 1 on malformed markers.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Both comment spellings: some files carry the bang escaped ("<\!--"),
# matching the tolerance already in md_paragraphs' comment category.
_MARKER_RE = re.compile(r"<\\?!--\s*(/?)lock\s*-->")
_TOKEN_RE = re.compile(r"\[\[LOCK-(\d+)\]\]")

TOKEN_FMT = "[[LOCK-{n}]]"


class LockError(ValueError):
    """Malformed lock structure: nested, unbalanced, or a broken token."""


def _whole_line_marker(line):
    m = _MARKER_RE.fullmatch(line.strip())
    return m if m else None


def is_open_marker(line):
    """True when the stripped line is exactly an opening lock marker."""
    m = _whole_line_marker(line)
    return bool(m and not m.group(1))


def is_close_marker(line):
    """True when the stripped line is exactly a closing lock marker."""
    m = _whole_line_marker(line)
    return bool(m and m.group(1))


def _line_of(text, offset, base_line):
    return base_line + text.count("\n", 0, offset)


def excise(text, start=1, base_line=1):
    """Replace each inline lock span with an anchor token.

    Returns (clean_text, manifest) where manifest maps token -> raw span
    bytes, markers included. Tokens number from ``start`` in document
    order so a re-parse of the same text yields the same tokens.
    ``base_line`` shifts reported line numbers to file coordinates.
    """
    out, manifest = [], {}
    pos, open_m, n = 0, None, start
    for m in _MARKER_RE.finditer(text):
        if not m.group(1):
            if open_m is not None:
                raise LockError(
                    f"nested lock: open at line {_line_of(text, m.start(), base_line)} "
                    f"inside the lock opened at line {_line_of(text, open_m.start(), base_line)}")
            open_m = m
        else:
            if open_m is None:
                raise LockError(
                    f"lock close without open at line {_line_of(text, m.start(), base_line)}")
            token = TOKEN_FMT.format(n=n)
            manifest[token] = text[open_m.start():m.end()]
            out.append(text[pos:open_m.start()])
            out.append(token)
            pos, open_m, n = m.end(), None, n + 1
    if open_m is not None:
        raise LockError(
            f"unclosed lock opened at line {_line_of(text, open_m.start(), base_line)}")
    out.append(text[pos:])
    return "".join(out), manifest


def splice(text, manifest):
    """Re-expand anchor tokens into their locked bytes.

    Every manifest token must appear exactly once, and no token outside
    the manifest may appear at all — a rewrite that dropped, duplicated,
    or invented an anchor is refused, not repaired.
    """
    for m in _TOKEN_RE.finditer(text):
        if m.group(0) not in manifest:
            raise LockError(f"unknown lock token {m.group(0)} in replacement text")
    for token in manifest:
        count = text.count(token)
        if count != 1:
            raise LockError(
                f"lock token {token} appears {count} times in replacement text "
                f"(expected exactly 1)")
    for token, raw in manifest.items():
        text = text.replace(token, raw)
    return text


def tokens_in(text):
    """Anchor tokens in ``text``, in order of appearance."""
    return [m.group(0) for m in _TOKEN_RE.finditer(text)]


def check_tokens(original, candidate):
    """None when ``candidate`` carries every token of ``original`` exactly
    once and no other; otherwise one message naming each fault.

    The rule splice() enforces, available before the splice: a driver can
    send the fault back to the model as a retry note instead of discovering
    at assembly time that the paragraph cannot be written.
    """
    want = tokens_in(original)
    have = Counter(tokens_in(candidate))
    faults = [f"{t} appears {have.get(t, 0)} times (expected exactly 1)"
              for t in want if have.get(t, 0) != 1]
    faults += [f"unknown token {t}" for t in have if t not in want]
    return "; ".join(faults) or None


def verify_preserved(spans, output):
    """The locked spans missing from ``output``: each must appear verbatim,
    markers included, as many times as it was locked. Empty when the
    invariant holds.

    A check on the bytes written, not on the path that wrote them. Every
    test of excise and splice passed while the GH-82 path shipped, because
    that path called neither.
    """
    missing, rest = [], output
    for span in spans:
        at = rest.find(span)
        if at < 0:
            missing.append(span)
        else:
            rest = rest[:at] + rest[at + len(span):]
    return missing


def main():
    ap = argparse.ArgumentParser(
        description="audit the span locks in a markdown or YAML document")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import prose_document
    try:
        doc = prose_document.ProseDocument.open(args.file)
    # ValueError, not LockError: run as a script this module is __main__,
    # so the imported drivers raise the *imported* span_locks.LockError —
    # a different class object. The common base is the reliable catch.
    except ValueError as e:
        print(f"{args.file}: MALFORMED — {e}", file=sys.stderr)
        sys.exit(1)

    report = doc.lock_report()
    if args.json:
        print(json.dumps({"file": args.file, **report}, indent=2))
    else:
        blocks = report.get("block_ranges", [])
        inline = report.get("inline", [])
        total = len(blocks) + sum(p["tokens"] for p in inline)
        print(f"{args.file}: {total} locked span(s)")
        for s, e in blocks:
            print(f"  block  L{s}-{e}")
        for p in inline:
            print(f"  inline paragraph {p['paragraph']}  L{p['start_line']}-"
                  f"{p['end_line']}  {p['tokens']} span(s)")
    sys.exit(0)


if __name__ == "__main__":
    main()
