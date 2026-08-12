#!/usr/bin/env python3
"""Offline tests for extension-aware output naming (GH-349).

The old .md-only substitutions had two silent-overwrite failure modes for
non-.md articles: the default draft path equalled the article path, and the
manifest path equalled the draft path. These pin the derivations.

No network, no model. Run: python3 <skill>/scripts/testdata/test_out_naming.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402


def test_default_out():
    assert drive.default_out("/w/a.md") == "/w/a.vr-draft.md"
    assert drive.default_out("/w/a.yaml") == "/w/a.vr-draft.yaml"
    assert drive.default_out("/w/a.yml") == "/w/a.vr-draft.yml"
    for art in ("/w/a.md", "/w/a.yaml"):
        assert drive.default_out(art) != art, "draft path equals article path"
    print("  default_out: ok")


def test_manifest_path():
    assert drive.manifest_path("/w/a.vr-draft.md") == \
        "/w/a.vr-draft.generation.yaml"
    assert drive.manifest_path("/w/a.vr-draft.yaml") == \
        "/w/a.vr-draft.generation.yaml"
    # A draft that already ends in .generation.yaml still gets a distinct
    # manifest rather than overwriting itself.
    weird = "/w/a.generation.yaml"
    assert drive.manifest_path(weird) != weird
    print("  manifest_path: ok")


def main():
    test_default_out()
    test_manifest_path()
    print("test_out_naming: all assertions passed")


if __name__ == "__main__":
    main()
