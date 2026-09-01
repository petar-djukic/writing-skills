#!/usr/bin/env python3
"""Offline tests for the bake-off harness (GH-205): the module imports
from its new home, and the mechanical scorer holds its multiset
semantics. No model calls."""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import importlib
bo = importlib.import_module("bakeoff")


def test_imports_from_new_home():
    # The move relocated the script out of match-voice; rewrite and
    # md_paragraphs must still resolve (sibling-skill and shared paths).
    assert hasattr(bo, "score") and hasattr(bo, "sweep")
    assert "cohere:command-a-03-2025" in bo.MODELS
    print("  imports_from_new_home: ok")


def test_score_multisets():
    orig = "The run kept 42 of 50 items [3] and cited the spec twice [3]."
    same = "It kept 42 of 50 items [3], citing the spec twice [3]."
    r = bo.score(orig, same)
    assert r["cites_kept"] and r["nums_kept"], r
    # dropping ONE of two identical citations is a loss — multisets
    dropped = "The run kept 42 of 50 items [3] and cited the spec twice."
    r = bo.score(orig, dropped)
    assert not r["cites_kept"], r
    # a lost number is a loss
    r = bo.score(orig, "The run kept most items [3] twice [3].")
    assert not r["nums_kept"], r
    print("  score_multisets: ok")


def test_score_meta_hits():
    r = bo.score("Plain text.", "Here is the rewritten paragraph: Plain text.")
    assert r["meta_hits"], r
    r = bo.score("Plain text.", "Plain text.")
    assert not r["meta_hits"], r
    print("  score_meta_hits: ok")


if __name__ == "__main__":
    test_imports_from_new_home()
    test_score_multisets()
    test_score_meta_hits()
    print("all bake-off tests passed")
