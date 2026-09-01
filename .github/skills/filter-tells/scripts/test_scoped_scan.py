#!/usr/bin/env python3
"""Tests for scoped_scan.py (GH-209): scope parsing, manifest and sidecar
consumption, accent-log mapping, view building, and the end-to-end
guarantee that an out-of-scope tell is not scanned. Offline; the one
subprocess run is detect-lexical.sh, which makes no model calls."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import importlib
ss = importlib.import_module("scoped_scan")

ARTICLE = """# Heading

First paragraph is plain and carries no tell at all today.

Second paragraph wants to leverage the ecosystem at scale.

| a | b |
|---|---|
| 1 | 2 |

Third paragraph is also plain and says nothing remarkable.

Fourth paragraph is plain as well and closes the document.

Fifth paragraph would leverage a paradigm shift if scanned.
"""


def _write(tmp, name, content):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_parse_ranges():
    assert ss.parse_ranges("1,3,7-9") == {1, 3, 7, 8, 9}
    assert ss.parse_ranges(" 2 ") == {2}
    try:
        ss.parse_ranges("0")
        raise AssertionError("accepted 0")
    except ValueError:
        pass
    try:
        ss.parse_ranges("5-3")
        raise AssertionError("accepted inverted range")
    except ValueError:
        pass
    print("  parse_ranges: ok")


def test_from_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "x.generation.yaml",
                   "match_voice:\n  model: m\n"
                   "  result: {accepted: 2}\n"
                   "  changed_paragraphs: [3, 7, 12]\n")
        assert ss.from_manifest(p) == {3, 7, 12}
        p2 = _write(tmp, "empty.generation.yaml",
                    "match_voice:\n  changed_paragraphs: []\n")
        assert ss.from_manifest(p2) == set()
        p3 = _write(tmp, "old.generation.yaml", "match_voice:\n  model: m\n")
        try:
            ss.from_manifest(p3)
            raise AssertionError("accepted pre-GH-209 manifest silently")
        except SystemExit:
            pass
    print("  from_manifest: ok")


def test_from_tighten():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "x.tighten.json",
                   json.dumps({"changed_paragraphs": [2, 4]}))
        assert ss.from_tighten(p) == {2, 4}
    print("  from_tighten: ok")


def test_accent_log_mapping():
    import md_paragraphs
    prose = md_paragraphs.parse(ARTICLE).paragraphs
    # Blank-line blocks of ARTICLE: 0 heading, 1 first para, 2 second para,
    # 3 table, 4 third para, 5 fourth para, 6 fifth para. Applying block 2
    # must map to prose paragraph 2; applying the table block maps nowhere
    # new; block 6 maps to prose paragraph 5.
    with tempfile.TemporaryDirectory() as tmp:
        log = _write(tmp, "x.log.json", json.dumps([
            {"para": 2, "applied": True},
            {"para": 3, "applied": True},
            {"para": 6, "applied": True},
            {"para": 4, "applied": False},
        ]))
        got = ss.from_accent_log(log, ARTICLE, prose)
    assert got == {2, 5}, got
    print("  accent_log_mapping: ok")


def test_build_view_and_mapping():
    import md_paragraphs
    prose = md_paragraphs.parse(ARTICLE).paragraphs
    view, mapping = ss.build_view(prose, {2})
    assert "leverage the ecosystem" in view
    assert "paradigm shift" not in view
    assert mapping[0][0] == 2
    try:
        ss.build_view(prose, {99})
        raise AssertionError("accepted out-of-range paragraph")
    except SystemExit:
        pass
    print("  build_view: ok")


def test_end_to_end_scoping():
    """The banned word in paragraph 5 must not appear in a scan scoped to
    paragraph 2, and the paragraph-2 tell must."""
    with tempfile.TemporaryDirectory() as tmp:
        art = _write(tmp, "a.md", ARTICLE)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "scoped_scan.py"),
             art, "--changed", "2"],
            capture_output=True, text=True)
        out = r.stdout
        assert "scope: 1 of 5 prose paragraphs" in out, out
        assert "ecosystem" in out, out
        assert "paradigm" not in out, out
        # Empty scope is a stated no-op, exit 2.
        r2 = subprocess.run(
            [sys.executable, os.path.join(HERE, "scoped_scan.py"), art],
            capture_output=True, text=True)
        assert r2.returncode == 2, (r2.returncode, r2.stderr)
        assert "empty scope" in r2.stderr
    print("  end_to_end_scoping: ok")


if __name__ == "__main__":
    test_parse_ranges()
    test_from_manifest()
    test_from_tighten()
    test_accent_log_mapping()
    test_build_view_and_mapping()
    test_end_to_end_scoping()
    print("all scoped_scan tests passed")
