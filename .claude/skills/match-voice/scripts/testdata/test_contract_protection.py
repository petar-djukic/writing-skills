#!/usr/bin/env python3
"""Tests for contract-field protection (GH-362).

Covers:
  - Paragraph.key_path property and to_dict() exposure
  - _match_key_glob pattern matching
  - excluded_indices filtering
  - verify.py must-preserve phrases
  - verify.py ASCII normalization (normalize_ascii)

No network, no model.
Run: python3 <skill>/scripts/testdata/test_contract_protection.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SHARED = os.path.normpath(os.path.join(SCRIPTS, "..", "..", "..", "scripts"))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, SHARED)

import prose_document as pd
import verify


# --- Paragraph.key_path and to_dict() ----------------------------------------

def test_key_path_property_returns_copy():
    p = pd.Paragraph(0, "hello world foo bar baz", 1, 1, "a.b",
                      key_path=["a", "b"])
    kp = p.key_path
    assert kp == ["a", "b"]
    kp.append("c")
    assert p.key_path == ["a", "b"], "mutation leaked into the paragraph"


def test_key_path_none_for_markdown():
    p = pd.Paragraph(0, "hello world foo bar baz", 1, 1, "heading")
    assert p.key_path is None


def test_to_dict_includes_key_path_for_yaml():
    p = pd.Paragraph(0, "some prose text here enough", 1, 1, "sections.0.body",
                      key_path=["sections", "0", "body"])
    d = p.to_dict()
    assert "key_path" in d
    assert d["key_path"] == ["sections", "0", "body"]


def test_to_dict_omits_key_path_when_none():
    p = pd.Paragraph(0, "some prose text here enough", 1, 1, "heading")
    d = p.to_dict()
    assert "key_path" not in d


# --- _match_key_glob ---------------------------------------------------------

def test_exact_match():
    assert pd._match_key_glob(["section_goal"], "section_goal")
    assert not pd._match_key_glob(["section_goal"], "body")


def test_wildcard_segment():
    assert pd._match_key_glob(["goals", "0", "goal"], "goals.*.goal")
    assert pd._match_key_glob(["goals", "5", "goal"], "goals.*.goal")
    assert not pd._match_key_glob(["goals", "0", "text"], "goals.*.goal")


def test_trailing_wildcard():
    assert pd._match_key_glob(["acceptance", "criteria"], "acceptance.*")
    assert pd._match_key_glob(["acceptance", "0"], "acceptance.*")
    assert pd._match_key_glob(["acceptance", "x", "y"], "acceptance.*")
    assert not pd._match_key_glob(["meta"], "acceptance.*")


def test_meta_wildcard():
    assert pd._match_key_glob(["meta", "version"], "meta.*")
    assert pd._match_key_glob(["meta", "a", "b"], "meta.*")


def test_none_key_path_never_matches():
    assert not pd._match_key_glob(None, "section_goal")


def test_string_key_path():
    assert pd._match_key_glob("goals.0.goal", "goals.*.goal")


# --- excluded_indices ---------------------------------------------------------

def _para(index, key_path):
    return pd.Paragraph(index, "word " * 10, 1, 1, ".".join(key_path),
                         key_path=key_path)


def test_excluded_indices_default_patterns():
    paras = [
        _para(0, ["intro", "body"]),
        _para(1, ["section_goal"]),
        _para(2, ["goals", "0", "goal"]),
        _para(3, ["acceptance", "criteria"]),
        _para(4, ["meta", "version"]),
        _para(5, ["sections", "0", "body"]),
    ]
    excl = pd.excluded_indices(paras, pd.YAML_EXCLUDE_KEYS_DEFAULT)
    assert excl == {2, 3, 4, 5}, f"got {excl}"


def test_excluded_indices_empty_patterns():
    paras = [_para(0, ["section_goal"])]
    assert pd.excluded_indices(paras, []) == set()


def test_excluded_indices_no_key_path():
    p = pd.Paragraph(0, "word " * 10, 1, 1, "heading")
    assert pd.excluded_indices([p], pd.YAML_EXCLUDE_KEYS_DEFAULT) == set()


# --- verify.py: normalize_ascii ----------------------------------------------

def test_normalize_curly_quotes():
    assert verify.normalize_ascii("‘hello’") == "'hello'"
    assert verify.normalize_ascii("“hello”") == '"hello"'


def test_normalize_nonbreaking_hyphen():
    assert verify.normalize_ascii("non‑breaking") == "non-breaking"


def test_normalize_nonbreaking_space():
    assert verify.normalize_ascii("hello world") == "hello world"


def test_normalize_thin_space():
    assert verify.normalize_ascii("hello world") == "hello world"


def test_normalize_soft_hyphen_removed():
    assert verify.normalize_ascii("soft­hyphen") == "softhyphen"


def test_normalize_en_dash():
    assert verify.normalize_ascii("2020–2025") == "2020-2025"


def test_normalize_idempotent_on_ascii():
    s = "plain ascii text - no change"
    assert verify.normalize_ascii(s) == s


# --- verify.py: must-preserve phrases ----------------------------------------

def test_must_preserve_passes_when_phrase_present():
    orig = "The system recorded as planned the observations."
    rewrite = "The system recorded as planned each observation."
    result = verify.verify(orig, rewrite, must_preserve=["recorded as planned"])
    assert result["clean"]


def test_must_preserve_fails_when_phrase_lost():
    orig = "The system recorded as planned the observations."
    rewrite = "The system logged as intended each observation."
    result = verify.verify(orig, rewrite, must_preserve=["recorded as planned"])
    assert not result["clean"]
    fatal = [f for f in result["findings"] if f["check"] == "must-preserve"]
    assert len(fatal) == 1
    assert "recorded as planned" in fatal[0]["detail"]


def test_must_preserve_multiple_phrases():
    orig = "No number is cited. Submission-status care applies."
    rewrite = "No number is cited. The status requires attention."
    result = verify.verify(orig, rewrite,
                           must_preserve=["No number is cited",
                                          "Submission-status care"])
    fatal = [f for f in result["findings"] if f["check"] == "must-preserve"]
    assert len(fatal) == 1
    assert "Submission-status care" in fatal[0]["detail"]


def test_must_preserve_none_is_noop():
    result = verify.verify("text here", "text here", must_preserve=None)
    assert result["clean"]


def test_must_preserve_skips_phrase_not_in_original():
    orig = "Something else entirely."
    rewrite = "Something different."
    result = verify.verify(orig, rewrite,
                           must_preserve=["recorded as planned"])
    mp = [f for f in result["findings"] if f["check"] == "must-preserve"]
    assert len(mp) == 0


# --- verify.py: ASCII normalization runs before checks ------------------------

def test_ascii_normalization_catches_reintroduced_curly_quotes():
    orig = 'The "standard" approach works well.'
    rewrite = 'The “standard” approach works well.'
    result = verify.verify(orig, rewrite)
    assert result["clean"], "curly quotes should be normalized to ASCII before comparison"


def test_ascii_normalization_catches_nonbreaking_hyphen():
    orig = "non-breaking hyphen test"
    rewrite = "non‑breaking hyphen test"
    result = verify.verify(orig, rewrite)
    assert result["clean"], "non-breaking hyphen should normalize to ASCII hyphen"


# --- end ----------------------------------------------------------------------

def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_contract_protection: all assertions passed")


if __name__ == "__main__":
    main()
