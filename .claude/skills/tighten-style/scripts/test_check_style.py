#!/usr/bin/env python3
"""Tests for tighten_style_check paragraph-level API."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)
import check_style as cs


def test_returns_list():
    result = cs.tighten_style_check("A simple sentence with no issues at all.")
    assert isinstance(result, list)
    print("  returns_list: ok")


def test_ts01_needless_words():
    text = "In order to understand the system we must read the documentation."
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-01" in rules, f"expected TS-01, got {rules}"
    print("  ts01_needless_words: ok")


def test_ts03_negative_form():
    text = "The system did not remember the previous state of the connection."
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-03" in rules, f"expected TS-03, got {rules}"
    print("  ts03_negative_form: ok")


def test_ts05_intensifier():
    text = "The system is very fast and extremely reliable under all conditions."
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-05" in rules, f"expected TS-05, got {rules}"
    print("  ts05_intensifier: ok")


def test_ts08_hedge_stack():
    text = ("The system may perhaps possibly suggest that the implementation "
            "could arguably be somewhat improved in certain conditions.")
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-08" in rules, f"expected TS-08, got {rules}"
    print("  ts08_hedge_stack: ok")


def test_ts15_importance():
    text = "This is a fundamental breakthrough in the field of computing."
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-15" in rules, f"expected TS-15, got {rules}"
    print("  ts15_importance: ok")


def test_ts15_term_of_art_excluded():
    text = "The critical section protects shared state from data races."
    result = cs.tighten_style_check(text)
    rules = [f["rule"] for f in result]
    assert "TS-15" not in rules, f"term of art should be excluded, got {rules}"
    print("  ts15_term_of_art_excluded: ok")


def test_rule_filter():
    text = "In order to understand the very fundamental system we proceed."
    all_findings = cs.tighten_style_check(text)
    ts01_only = cs.tighten_style_check(text, rules={"TS-01"})
    assert all(f["rule"] == "TS-01" for f in ts01_only)
    assert len(ts01_only) <= len(all_findings)
    print("  rule_filter: ok")


def test_check_paragraph_alias():
    assert cs.check_paragraph is cs.tighten_style_check
    print("  check_paragraph_alias: ok")


def test_base_line_offset():
    text = "In order to understand the system we must first read everything."
    result = cs.tighten_style_check(text, base_line=42)
    assert all(f["line"] >= 42 for f in result), \
        f"expected lines >= 42, got {[f['line'] for f in result]}"
    print("  base_line_offset: ok")


def test_clean_text():
    text = "The router forwards packets to the next hop in the network."
    result = cs.tighten_style_check(text)
    assert result == [], f"expected clean, got {result}"
    print("  clean_text: ok")


def main():
    test_returns_list()
    test_ts01_needless_words()
    test_ts03_negative_form()
    test_ts05_intensifier()
    test_ts08_hedge_stack()
    test_ts15_importance()
    test_ts15_term_of_art_excluded()
    test_rule_filter()
    test_check_paragraph_alias()
    test_base_line_offset()
    test_clean_text()
    print("test_check_style: all assertions passed")


if __name__ == "__main__":
    main()
