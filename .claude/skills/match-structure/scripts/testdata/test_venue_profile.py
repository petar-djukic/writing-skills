#!/usr/bin/env python3
"""Offline tests for venue_profile. Run: python3 testdata/test_venue_profile.py

Builds a synthetic writing-voice corpus with a venues/ directory in a temp
directory, so the assertions are about the schema contract and discovery rule
rather than about any particular corpus.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import venue_profile as vp  # noqa: E402

GOOD = """\
name: newsletter
level: 1
description: test venue
anchor_query:
  role: venue-voice
  tags: [punchy]
blueprint: howto.md
structural_step: tighten-style
pov: first-person
citations: numbered
tell_lexicon: newsletter
hedge_policy: minimal
targets:
  sentence_length_mean: 17.4
  hedges_per_1000_words: 1.2
gates:
  - name: pangram
    max_ai_fraction: 0.5
  - pace
"""

MANIFEST = """\
purpose: test corpus
exemplars:
  - id: a
    file: A-2010-a.md
    role: venue-voice
    year: 2010
    tags: [punchy]
"""


def build_corpus(root):
    voice = os.path.join(root, "writing-voice")
    os.makedirs(os.path.join(voice, "venues"))
    os.makedirs(os.path.join(voice, "blueprints"))
    with open(os.path.join(voice, "manifest.yaml"), "w") as f:
        f.write(MANIFEST)
    with open(os.path.join(voice, "A-2010-a.md"), "w") as f:
        f.write("Sample text.\n")
    with open(os.path.join(voice, "blueprints", "howto.md"), "w") as f:
        f.write("# blueprint\n")
    with open(os.path.join(voice, "venues", "newsletter.yaml"), "w") as f:
        f.write(GOOD)
    # a nested article dir so walk-up discovery has something to climb from
    art = os.path.join(root, "articles", "2026")
    os.makedirs(art)
    apath = os.path.join(art, "draft.md")
    with open(apath, "w") as f:
        f.write("Draft.\n")
    return voice, apath


def main():
    tmp = tempfile.mkdtemp(prefix="venue-profile-test-")
    try:
        voice, article = build_corpus(tmp)

        # discovery walks up from the article to venues/
        found = vp.find_profile(article, "newsletter")
        assert found and found.endswith("venues/newsletter.yaml"), found
        assert vp.find_profile(article, "missing") is None
        assert vp.list_venues(voice) == ["newsletter"]

        # resolve loads, validates, normalizes gates
        prof = vp.resolve(start_path=article, venue="newsletter")
        assert prof["name"] == "newsletter"
        assert prof["gates"][0] == {"name": "pangram", "max_ai_fraction": 0.5}
        assert prof["gates"][1] == {"name": "pace"}  # bare string normalized
        assert prof["_warnings"] == [], prof["_warnings"]

        # unknown venue raises with the available list
        try:
            vp.resolve(voice_dir=voice, venue="nope")
            raise AssertionError("expected FileNotFoundError")
        except FileNotFoundError as e:
            assert "newsletter" in str(e)

        # validation: bad enums and non-numeric targets are errors
        bad = dict(vp.load_profile(found))
        bad["structural_step"] = "rewrite-everything"
        bad["citations"] = "footnotes"
        bad["targets"] = {"sentence_length_mean": "long"}
        bad["gates"] = ["pangram", "vibes"]
        errors, warnings = vp.validate_profile(bad)
        joined = " | ".join(errors)
        assert "structural_step" in joined, joined
        assert "citations" in joined
        assert "sentence_length_mean" in joined
        assert "vibes" in joined

        # warnings: unknown tag, unknown target key, missing blueprint
        warn = dict(vp.load_profile(found))
        warn["anchor_query"] = {"tags": ["no-such-tag"]}
        warn["targets"] = {"sentence_length_mean": 17.0, "swagger": 9.9}
        warn["blueprint"] = "absent.md"
        manifest = [{"tags": ["punchy"]}]
        errors, warnings = vp.validate_profile(warn, manifest=manifest)
        assert errors == [], errors
        joined = " | ".join(warnings)
        assert "no-such-tag" in joined, joined
        assert "swagger" in joined
        assert "absent.md" in joined

        # missing required fields are errors
        errors, _ = vp.validate_profile({"name": "x"})
        assert any("level" in e for e in errors)
        assert any("gates" in e for e in errors)

        print("ok: all venue_profile assertions passed")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
