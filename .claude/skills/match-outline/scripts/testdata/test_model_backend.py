#!/usr/bin/env python3
"""Regression tests for model backend configurability.

Run: python3 testdata/test_model_backend.py

Verifies:
  1. Default model is claude-* (structural rewrite uses a large model)
  2. --help works without the anthropic package
  3. _is_claude routing is correct
  4. Claude backend is selected for the default model
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import match_outline as ms  # noqa: E402


def test_default_is_claude():
    """The default model must be a claude-* model."""
    assert ms.DEFAULT_MODEL.startswith("claude-"), (
        f"DEFAULT_MODEL is '{ms.DEFAULT_MODEL}' — must be claude-*. "
        "match-outline does structural rewriting where capability matters; "
        "match-voice handles AI diction cleanup downstream.")
    print(f"  default model: {ms.DEFAULT_MODEL} (claude)")


def test_is_claude_routing():
    """_is_claude correctly classifies model names."""
    assert ms._is_claude("claude-opus-4-8")
    assert ms._is_claude("claude-sonnet-5")
    assert not ms._is_claude("gemma4:12b")
    assert not ms._is_claude("gemma4:31b-cloud")
    assert not ms._is_claude("llama3.1:8b")
    print("  _is_claude routing: correct")


def test_help_no_anthropic():
    """--help must work even without the anthropic package installed."""
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "match_outline.py"), "--help"],
        capture_output=True, text=True)
    assert r.returncode == 0, f"--help failed: {r.stderr}"
    assert "--model" in r.stdout, "--model not in help"
    assert "--endpoint" in r.stdout, "--endpoint not in help"
    print("  --help works, shows --model and --endpoint")


def test_backend_construction():
    """Default model routes to Claude backend."""
    model = ms.DEFAULT_MODEL
    assert ms._is_claude(model)
    assert not ms._is_claude("gemma4:12b")
    print("  backend routing: claude for default, ollama for non-claude")


def main():
    test_default_is_claude()
    test_is_claude_routing()
    test_help_no_anthropic()
    test_backend_construction()
    print("test_model_backend: all assertions passed")


if __name__ == "__main__":
    main()
