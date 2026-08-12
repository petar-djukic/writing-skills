#!/usr/bin/env python3
"""Tests for writing-voice corpus support in style.py and match_structure.py.

Run: python3 .agents/skills/match-structure/scripts/testdata/test_voice_corpus.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import style
import match_structure as ms


def setup_voice_dir(tmp):
    """Create a minimal writing-voice directory with manifest and exemplars."""
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd)
    with open(os.path.join(vd, "manifest.yaml"), "w") as f:
        f.write("""purpose: test corpus
updated: '2026-07-27'
target_document: test
roles:
  author-voice: author samples
  venue-voice: venue samples
exemplars:
  - id: author-2010-sample
    file: author-2010.md
    role: author-voice
    year: 2010
    tags: [diction, academic]
  - id: venue-2015-sample
    file: venue-2015.md
    role: venue-voice
    year: 2015
    tags: [medium, workflow]
  - id: venue-2023-post
    file: venue-2023.md
    role: venue-voice
    year: 2023
    pre_ai: false
    tags: [structure-only]
""")
    for name, content in [
        ("author-2010.md",
         "# Intro\n\nThe distributed algorithm coordinates nodes.\n\n"
         "# Results\n\nWe observe a 30% improvement.\n"),
        ("venue-2015.md",
         "# Overview\n\nThis essay argues for simplicity.\n\n"
         "# Conclusion\n\nSimplicity wins in practice.\n"),
        ("venue-2023.md",
         "# Structure\n\nA worked example of section layout.\n"),
    ]:
        with open(os.path.join(vd, name), "w") as f:
            f.write(content)
    return vd


def main():
    tmp = tempfile.mkdtemp()
    try:
        vd = setup_voice_dir(tmp)

        # 1. select_voice_corpus returns all exemplars with no filter.
        all_ex = style.select_voice_corpus(vd)
        assert len(all_ex) == 3, f"expected 3, got {len(all_ex)}"

        # 2. Role filter.
        authors = style.select_voice_corpus(vd, role="author-voice")
        assert len(authors) == 1 and authors[0][0]["id"] == "author-2010-sample"

        venues = style.select_voice_corpus(vd, role="venue-voice")
        assert len(venues) == 2

        # 3. Pre-AI filter.
        pre = style.select_voice_corpus(vd, pre_ai=True)
        assert len(pre) == 2, f"expected 2 pre-ai, got {len(pre)}"
        ids = {e[0]["id"] for e in pre}
        assert "venue-2023-post" not in ids

        ai_era = style.select_voice_corpus(vd, pre_ai=False)
        assert len(ai_era) == 1 and ai_era[0][0]["id"] == "venue-2023-post"

        # 4. Tag filter.
        academic = style.select_voice_corpus(vd, tags=["academic"])
        assert len(academic) == 1 and academic[0][0]["id"] == "author-2010-sample"

        workflow = style.select_voice_corpus(vd, tags=["workflow"])
        assert len(workflow) == 1 and workflow[0][0]["id"] == "venue-2015-sample"

        # 5. Combined filters.
        combo = style.select_voice_corpus(vd, role="venue-voice", pre_ai=True)
        assert len(combo) == 1 and combo[0][0]["id"] == "venue-2015-sample"

        # 6. Return shape matches select_corpus: (entry_dict, abs_path).
        entry, path = all_ex[0]
        assert isinstance(entry, dict) and "id" in entry
        assert os.path.isabs(path) and os.path.exists(path)

        # 7. load_corpus with voice_dir.
        corpus_text, n = ms.load_corpus("nonexistent.yaml", voice_dir=vd)
        assert n == 3, f"expected 3 papers, got {n}"
        assert "author-2010-sample" in corpus_text

        # 8. _strip_added_bold: removes bold the model added.
        orig = "The algorithm works."
        rewritten = "**The algorithm** works well."
        assert "**" not in ms._strip_added_bold(orig, rewritten)

        # 9. _strip_added_bold: keeps bold that was in the original.
        orig2 = "**The algorithm** works."
        rewritten2 = "**The algorithm** works well."
        assert "**" in ms._strip_added_bold(orig2, rewritten2)

        # 10. "references" section pattern added to style.
        from style import SECTION_PATTERNS
        ref_names = [name for name, _ in SECTION_PATTERNS]
        assert "references" in ref_names

        # 11. _FM regex extracts front matter for preservation (GH-298).
        draft_with_fm = "---\ntitle: Test\ndate: 2026-07-28\n---\n\n# Intro\n\nBody text.\n"
        fm_match = ms._FM.match(draft_with_fm)
        assert fm_match is not None, "_FM must match YAML front matter"
        assert fm_match.group(0).startswith("---\ntitle: Test")
        assert ms._FM.match("# No front matter\n\nJust text.") is None

        print("test_voice_corpus: all assertions passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
