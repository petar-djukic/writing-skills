#!/usr/bin/env python3
"""Tests for ornate-register occurrence counting (GH-242).

`grep -c` counts matching LINES. A markdown paragraph is one long line, so
three flourishes in a paragraph scored as one and the density undercounted the
documents it exists to catch — worse the longer the paragraphs. Bundling -o
with -c is not a dependable fix: the result varies by grep implementation.

These tests pin the arithmetic against a single line, which is where the two
readings differ, and pin the 4.0 threshold against the corpus sweep that
justified keeping it.

Run: python3 <skill>/scripts/testdata/test_ornate_density.py
"""
import os
import re
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.normpath(os.path.join(HERE, "..", "detect-lexical.sh"))

PAD = ("The node sends a frame to the peer and the peer returns a receipt. "
       "The scheduler assigns one slot per node in each frame. ")


def density(text):
    """The ornate density the scanner reports for `text`."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "sample.md")
        open(p, "w").write(text)
        r = subprocess.run(["bash", SCAN, p], capture_output=True, text=True)
    m = re.search(r"Ornate-register density: ([\d.]+)/500w", r.stdout)
    assert m, r.stdout
    return float(m.group(1)), r.returncode


def test_three_hits_on_one_line_count_three():
    """The defect, reduced to its smallest form.

    Under line counting this paragraph scores 1 and reads as clean prose with a
    single flourish. It has three.
    """
    line = ("# H\n\nThe design is brittle, the concern is orthogonal, and the "
            "assumption is load-bearing. " + PAD * 12 + "\n")
    d, _rc = density(line)
    words = len(line.split())
    assert abs(d - 3 / words * 500) < 0.15, (d, words, 3 / words * 500)


def test_hits_spread_over_lines_are_unchanged():
    """Where each hit sits on its own line the two readings agree, which is why
    the corpus sweep found a median factor of 1.00x."""
    spread = ("# H\n\nThe design is brittle.\n\nThe concern is orthogonal.\n\n"
              "The assumption is load-bearing.\n\n" + PAD * 12 + "\n")
    d, _rc = density(spread)
    words = len(spread.split())
    assert abs(d - 3 / words * 500) < 0.15, (d, words)


def test_clean_prose_scores_zero():
    d, rc = density("# H\n\n" + PAD * 12 + "\n")
    assert d == 0.0
    assert rc == 0


def test_threshold_still_fires_above_four():
    """4.0 is kept, not re-tuned: across 193 files in three corpora only one
    exceeds it after the fix, and that one is filter-tells' own pattern list."""
    dense = "# H\n\n" + ("It is brittle and orthogonal and load-bearing. " * 6) \
            + PAD * 3 + "\n"
    d, rc = density(dense)
    assert d > 4.0, d
    assert rc == 1, "over-threshold ornate density must fail the scan"


def test_counting_does_not_use_bare_c():
    """Pins the implementation, because the bug is invisible in output: a
    reviewer cannot tell 1-of-3 from 1-of-1 by reading a density."""
    src = open(SCAN).read()
    block = src[src.index("Ornate-register density per 500 words"):]
    block = block[:block.index("local file_words")]
    assert "grep -ioc" not in block, "bare -c counts lines, not occurrences"
    assert "wc -l" in block, "occurrences must be counted with -o piped to wc"


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_ornate_density: all assertions passed")


if __name__ == "__main__":
    main()
