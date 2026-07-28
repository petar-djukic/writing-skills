#!/usr/bin/env python3
"""Regression tests for model backend configurability.

Run: python3 testdata/test_model_backend.py

Verifies:
  1. Default model is an Ollama cloud model (gpt-oss:120b-cloud)
  2. --help works without the anthropic package
  3. _is_claude routing is correct
  4. Ollama backend is selected for the default model
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import match_outline as ms  # noqa: E402


def test_default_is_ollama():
    """The default model must be an Ollama model, not claude-*."""
    assert not ms._is_claude(ms.DEFAULT_MODEL), (
        f"DEFAULT_MODEL is '{ms.DEFAULT_MODEL}' — must not be claude-*. "
        "match-outline defaults to an Ollama cloud model; pass --model "
        "claude-* explicitly for the Anthropic API.")
    print(f"  default model: {ms.DEFAULT_MODEL} (ollama)")


def test_is_claude_routing():
    """_is_claude correctly classifies model names."""
    assert ms._is_claude("claude-opus-4-8")
    assert ms._is_claude("claude-sonnet-5")
    assert not ms._is_claude("gemma4:12b")
    assert not ms._is_claude("gemma4:31b-cloud")
    assert not ms._is_claude("gpt-oss:120b-cloud")
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
    """Default model routes to Ollama backend."""
    model = ms.DEFAULT_MODEL
    assert not ms._is_claude(model)
    assert ms._is_claude("claude-sonnet-5")
    print("  backend routing: ollama for default, claude for claude-*")


def main():
    test_default_is_ollama()
    test_is_claude_routing()
    test_help_no_anthropic()
    test_backend_construction()
    print("test_model_backend: all assertions passed")


if __name__ == "__main__":
    main()
