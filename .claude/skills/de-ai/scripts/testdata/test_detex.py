#!/usr/bin/env python3
"""Fixture test for detex.py. Run: python3 testdata/test_detex.py

Asserts the .tex path and the .md path agree on a paragraph present in both
forms, and that the sample's known LaTeX findings are handled.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import detex as dx  # noqa: E402


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    tex = open(os.path.join(HERE, "sample.tex")).read()
    md = open(os.path.join(HERE, "sample.md")).read()

    prose, line_map = dx.detex(tex)
    assert len(prose.split("\n")) == len(line_map), "line map length mismatch"

    # 1. md/tex agreement: the shared paragraph reads identically after detex.
    shared = "Reliability comes from the workflow. On Ollama you keep both. The bill stays predictable whatever you run."
    assert _norm(shared) in _norm(prose), "shared paragraph not found in tex prose"
    md_para = md.split("\n")[1]  # the paragraph line, minus the ## heading
    assert _norm(md_para) in _norm(prose), "tex prose disagrees with md paragraph"

    # 2. markup is gone; caption text is kept as prose.
    for tok in ("\\textbf", "\\citep", "\\includegraphics", "\\begin{figure}", "\\section"):
        assert tok not in prose, f"leftover markup: {tok}"
    assert "this comment must not appear" not in prose, "comment not stripped"
    assert "The end-to-end pipeline architecture." in prose, "caption not kept"
    assert "A first bulleted point." in prose, "list item text dropped"
    assert "50%" in prose, "escaped percent not unescaped"
    assert "[MATH]" in prose, "inline math not tokenized"

    # 3. citations: default tokenizes to [CITE]; keep_cites carries the keys.
    assert prose.count("[CITE]") == 2, "expected two citation tokens"
    keyed, _ = dx.detex(tex, keep_cites=True)
    keys = re.findall(r"\[CITE:[pt]:([^\]]+)\]", keyed)
    all_keys = [k for grp in keys for k in grp.split(",")]
    assert all_keys == ["smith2020", "jones2019", "doe2021"], all_keys

    # 4. abstract extraction (none in this sample) returns None cleanly.
    assert dx.extract_abstract(tex) is None

    print("test_detex: all assertions passed")


if __name__ == "__main__":
    main()
