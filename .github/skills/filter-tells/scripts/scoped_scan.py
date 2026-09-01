#!/usr/bin/env python3
"""scoped_scan.py — filter-tells scans over only the paragraphs the
pipeline changed (GH-209).

Every sampling stage after the chain's first filter-tells pass can inject
model phrasing (match-voice injected bold lead-ins, tighten-style raised
nominalization, applied critic picks moved Pangram 0.332 -> 0.421). A
full-document re-scan re-litigates author text and invites the
over-correction loop filter-tells warns about, so this scan is scoped: it
extracts exactly the paragraphs the drivers report as changed, builds a
scoped view, and runs detect-lexical.sh and detect-structural.py on that
view alone. Repairs stay editorial and route through the rewrite
transport per the skill procedure; this script only defines the worklist.

Scope sources (union of all given):
  --changed "1,3,7-9"          1-based md_paragraphs prose numbers
  --from-manifest X.yaml       drive.py generation.yaml (changed_paragraphs)
  --from-tighten X.tighten.json  tighten.py sidecar (changed_paragraphs)
  --from-accent-log X.log.json accent_dial edit log (applied units; its
                               blank-line paragraph indices are mapped onto
                               md_paragraphs prose numbers of the article)

The scoped view is a temp markdown file; the report header maps each view
paragraph back to its source paragraph number and line range. Exit code is
the max of the two detectors' exit codes; an empty scope exits 2 with a
message (nothing changed means nothing to scan — say so, don't scan the
world).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
sys.path.insert(0, SHARED)
import md_paragraphs  # noqa: E402


def parse_ranges(spec):
    """'1,3,7-9' -> {1, 3, 7, 8, 9}. Rejects zero and negatives."""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a < 1 or b < a:
                raise ValueError(f"bad range {part!r}")
            out.update(range(a, b + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"bad paragraph number {part!r}")
            out.add(n)
    return out


def from_manifest(path):
    """changed_paragraphs from a drive.py generation.yaml, by regex —
    the manifest is hand-shaped YAML and the one list is one line."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^\s*changed_paragraphs:\s*\[([^\]]*)\]", text, re.M)
    if not m:
        raise SystemExit(
            f"{path}: no changed_paragraphs line — manifest predates GH-209; "
            f"re-run the driver or pass --changed explicitly")
    inner = m.group(1).strip()
    return {int(x) for x in inner.split(",")} if inner else set()


def from_tighten(path):
    data = json.load(open(path, encoding="utf-8"))
    return set(data.get("changed_paragraphs", []))


def _blankline_blocks(text):
    """Blank-line-separated blocks with 1-based line ranges, matching
    accent_dial.split_paras() order (its indices are positions in that
    list). Returns [(start_line, end_line)] for nonempty blocks."""
    blocks, buf_start, last_nonblank = [], None, None
    lines = text.split("\n")
    for i, ln in enumerate(lines, 1):
        if ln.strip():
            if buf_start is None:
                buf_start = i
            last_nonblank = i
        else:
            if buf_start is not None:
                blocks.append((buf_start, last_nonblank))
                buf_start = None
    if buf_start is not None:
        blocks.append((buf_start, last_nonblank))
    return blocks


def from_accent_log(path, article_text, prose_paras):
    """Map accent_dial's applied units onto prose paragraph numbers.

    The log's "para" field indexes split_paras() blocks (0-based, every
    blank-line block including headings and tables); a prose paragraph is
    in scope when its line range overlaps an applied block's range.
    """
    data = json.load(open(path, encoding="utf-8"))
    cands = data if isinstance(data, list) else data.get("candidates", data)
    if isinstance(cands, dict):
        raise SystemExit(f"{path}: unrecognized accent log shape")
    applied = {c["para"] for c in cands if c.get("applied")}
    blocks = _blankline_blocks(article_text)
    out = set()
    for bi in applied:
        if bi < 0 or bi >= len(blocks):
            continue
        bs, be = blocks[bi]
        for n, (ps, pe, _txt) in enumerate(prose_paras, 1):
            if ps <= be and bs <= pe:
                out.add(n)
    return out


def build_view(prose_paras, ns):
    """Scoped view text plus a mapping table [(n, src_start, src_end)]."""
    chunks, mapping = [], []
    for n in sorted(ns):
        if n < 1 or n > len(prose_paras):
            raise SystemExit(
                f"paragraph {n} out of range (document has "
                f"{len(prose_paras)} prose paragraphs)")
        s, e, txt = prose_paras[n - 1]
        chunks.append(txt)
        mapping.append((n, s, e))
    return "\n\n".join(chunks) + "\n", mapping


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("article")
    ap.add_argument("--changed", help="explicit 1-based numbers, e.g. '1,3,7-9'")
    ap.add_argument("--from-manifest", action="append", default=[],
                    help="drive.py generation.yaml; repeatable")
    ap.add_argument("--from-tighten", action="append", default=[],
                    help="tighten.py <out>.tighten.json sidecar; repeatable")
    ap.add_argument("--from-accent-log", action="append", default=[],
                    help="accent_dial <out>.log.json; repeatable")
    ap.add_argument("--lexicon", help="venue lexicon for detect-lexical.sh")
    ap.add_argument("--voice-dir",
                    help="writing-voice dir for detect-structural.py "
                         "calibration (default: discovered from the article)")
    ap.add_argument("--keep-view", action="store_true",
                    help="keep the scoped view file and print its path")
    a = ap.parse_args()

    text = open(a.article, encoding="utf-8").read()
    prose = md_paragraphs.parse(text).paragraphs

    ns = set()
    if a.changed:
        ns |= parse_ranges(a.changed)
    for p in a.from_manifest:
        ns |= from_manifest(p)
    for p in a.from_tighten:
        ns |= from_tighten(p)
    for p in a.from_accent_log:
        ns |= from_accent_log(p, text, prose)

    if not ns:
        print("scoped_scan: empty scope — no changed paragraphs reported. "
              "Nothing to scan.", file=sys.stderr)
        return 2

    view_text, mapping = build_view(prose, ns)

    stem = os.path.splitext(os.path.basename(a.article))[0]
    tmpdir = tempfile.mkdtemp(prefix="scoped-scan-")
    view = os.path.join(tmpdir, f"{stem}.scoped.md")
    open(view, "w", encoding="utf-8").write(view_text)

    print(f"=== Scoped filter-tells scan: {a.article} ===")
    print(f"    scope: {len(mapping)} of {len(prose)} prose paragraphs")
    for n, s, e in mapping:
        print(f"    p{n:02d}  source lines {s}-{e}")
    if a.keep_view:
        print(f"    view: {view}")
    print()

    rc = 0

    lex_cmd = ["bash", os.path.join(HERE, "detect-lexical.sh"), view]
    if a.lexicon:
        lex_cmd.append(f"--lexicon={a.lexicon}")
    print(f"--- detect-lexical.sh ({'--lexicon=' + a.lexicon if a.lexicon else 'default lexicon'}) ---")
    r = subprocess.run(lex_cmd)
    rc = max(rc, r.returncode)
    print()

    struct_cmd = [sys.executable, os.path.join(HERE, "detect-structural.py"), view]
    voice_dir = a.voice_dir
    if not voice_dir:
        # Discover from the ARTICLE path, not the temp view — the walk-up
        # from a mkdtemp finds nothing and silently drops calibration.
        d = os.path.dirname(os.path.abspath(a.article))
        while d != os.path.dirname(d):
            cand = os.path.join(d, "writing-voice")
            if os.path.isdir(cand):
                voice_dir = cand
                break
            d = os.path.dirname(d)
    if voice_dir:
        struct_cmd.append(f"--voice-dir={voice_dir}")
    print("--- detect-structural.py ---")
    r = subprocess.run(struct_cmd)
    rc = max(rc, r.returncode)

    if not a.keep_view:
        try:
            os.unlink(view)
            os.rmdir(tmpdir)
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
