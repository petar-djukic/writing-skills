#!/usr/bin/env python3
"""Tests for GH-260: style.py must strip YAML front matter before profiling.

Run: python3 testdata/test_style_frontmatter.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import style  # noqa: E402

ARTICLE_WITH_FRONTMATTER = """\
---
title: How to Fence a Coding Agent
subtitle: A short guide to repository discipline
linkedin_post: >
  Ship it. The tool runs git, not the agents, and that is the whole rule
  here. Agents branch when they should not. Agents merge when nobody asked.
  Agents lose work in ways you find out about later. Let the orchestrator
  run git and the entire class of problem simply goes away for good.
illustration_prompt: A fence around a garden with robots inside
tags: [agents, git, workflow]
---

Let the orchestrator manage git operations because agents race on the index
and lose work in ways discovered later. One tool owns the repository state
and the agents do the implementation work they are good at.

Worktrees are cheap. Branches are cheap. Losing an afternoon of agent output
because two of them raced on the same index is not cheap at all.
"""

ARTICLE_NO_FRONTMATTER = """\
Let the orchestrator manage git operations because agents race on the index
and lose work in ways discovered later. One tool owns the repository state
and the agents do the implementation work they are good at.

Worktrees are cheap. Branches are cheap. Losing an afternoon of agent output
because two of them raced on the same index is not cheap at all.
"""


def test_strip_front_matter():
    """_strip_front_matter removes the --- block."""
    result = style._strip_front_matter(ARTICLE_WITH_FRONTMATTER)
    assert "title:" not in result, "front matter should be stripped"
    assert "linkedin_post:" not in result
    assert "orchestrator" in result, "body should remain"
    print("  strip_front_matter: passed")


def test_strip_no_front_matter():
    """_strip_front_matter is a no-op when no front matter present."""
    result = style._strip_front_matter(ARTICLE_NO_FRONTMATTER)
    assert result == ARTICLE_NO_FRONTMATTER
    print("  strip_no_front_matter: passed")


def test_profile_excludes_front_matter_words():
    """profile_file word count should not include front matter."""
    tmp = tempfile.mkdtemp(prefix="test-style-fm-")
    try:
        with_fm = os.path.join(tmp, "with.md")
        without_fm = os.path.join(tmp, "without.md")
        with open(with_fm, "w") as f:
            f.write(ARTICLE_WITH_FRONTMATTER)
        with open(without_fm, "w") as f:
            f.write(ARTICLE_NO_FRONTMATTER)

        p_with = style.profile_file(with_fm)
        p_without = style.profile_file(without_fm)

        assert p_with["overall"]["words"] == p_without["overall"]["words"], (
            f"with front matter: {p_with['overall']['words']} words, "
            f"without: {p_without['overall']['words']} — should match")
        print(f"  profile word count matches: {p_with['overall']['words']} words")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_raw_flag_includes_front_matter():
    """profile_file(raw=True) should include front matter in metrics."""
    tmp = tempfile.mkdtemp(prefix="test-style-raw-")
    try:
        path = os.path.join(tmp, "article.md")
        with open(path, "w") as f:
            f.write(ARTICLE_WITH_FRONTMATTER)

        p_default = style.profile_file(path)
        p_raw = style.profile_file(path, raw=True)

        assert p_raw["overall"]["words"] > p_default["overall"]["words"], (
            f"raw ({p_raw['overall']['words']}) should have more words "
            f"than default ({p_default['overall']['words']})")
        print(f"  raw flag: {p_raw['overall']['words']} > "
              f"{p_default['overall']['words']} words")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sentence_length_stdev_uncontaminated():
    """Front matter with varied sentence lengths should not inflate stdev."""
    tmp = tempfile.mkdtemp(prefix="test-style-stdev-")
    try:
        path = os.path.join(tmp, "article.md")
        with open(path, "w") as f:
            f.write(ARTICLE_WITH_FRONTMATTER)

        p_default = style.profile_file(path)
        p_raw = style.profile_file(path, raw=True)

        stdev_default = p_default["overall"]["sentence_length_stdev"]
        stdev_raw = p_raw["overall"]["sentence_length_stdev"]
        assert stdev_raw > stdev_default, (
            f"raw stdev ({stdev_raw}) should exceed stripped ({stdev_default}) "
            f"since front matter has varied sentence lengths")
        print(f"  stdev uncontaminated: {stdev_default} < {stdev_raw} (raw)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_strip_front_matter()
    test_strip_no_front_matter()
    test_profile_excludes_front_matter_words()
    test_raw_flag_includes_front_matter()
    test_sentence_length_stdev_uncontaminated()
    print("test_style_frontmatter: all assertions passed")


if __name__ == "__main__":
    main()
