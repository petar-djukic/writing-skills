#!/usr/bin/env python3
"""Tests that the Ollama timeout reaches the generation call. Run:

    python3 test_timeout.py

No Ollama, no network — rewrite.generate is replaced by a stub that records the
timeout it was handed.

Covers GH-23: match_outline.py passed timeout=600 literally at the call site, so
rewrite.py's own configurable default could not be raised from outside and any
chapter needing more than 600s of generation was unreachable. The defect was a
value not arriving, so every case here asserts the value that arrives.
"""
import importlib
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILURES = []
SEEN = {}


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def install_stub():
    """Stand in for match-voice's rewrite module, recording what it receives."""
    stub = types.ModuleType("rewrite")

    def generate(prompt, endpoint=None, model=None, temperature=0.7, timeout=None):
        SEEN["timeout"] = timeout
        return "rewritten text"

    stub.generate = generate
    sys.modules["rewrite"] = stub


def load(env=None):
    """Import match_outline fresh, with MATCH_OUTLINE_TIMEOUT set or cleared."""
    os.environ.pop("MATCH_OUTLINE_TIMEOUT", None)
    if env is not None:
        os.environ["MATCH_OUTLINE_TIMEOUT"] = env
    sys.modules.pop("match_outline", None)
    return importlib.import_module("match_outline")


BLOCKS = [{"type": "text", "text": "draft"}]


def timeout_seen(mo, backend):
    """The timeout generate received, or None if the call did not get there.

    Tolerant on purpose: run against the pre-fix module this must report a
    readable failure rather than raising, or it cannot demonstrate the bug.
    """
    SEEN.clear()
    try:
        mo.call_model(backend, "sys", BLOCKS)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return "call raised %s" % type(exc).__name__
    return SEEN.get("timeout")


OLLAMA = {"type": "ollama", "model": "m", "endpoint": "e"}


def main():
    install_stub()

    # --- the default, unchanged by this fix ---------------------------------
    mo = load()
    check("default is 600", getattr(mo, "DEFAULT_TIMEOUT", None) == 600,
          getattr(mo, "DEFAULT_TIMEOUT", "no DEFAULT_TIMEOUT"))
    check("default reaches generate", timeout_seen(mo, dict(OLLAMA)) == 600,
          timeout_seen(mo, dict(OLLAMA)))

    # --- the environment override, which is the reported defect -------------
    mo = load("3600")
    check("MATCH_OUTLINE_TIMEOUT sets the default",
          getattr(mo, "DEFAULT_TIMEOUT", None) == 3600,
          getattr(mo, "DEFAULT_TIMEOUT", "no DEFAULT_TIMEOUT"))
    check("MATCH_OUTLINE_TIMEOUT reaches generate",
          timeout_seen(mo, dict(OLLAMA)) == 3600, timeout_seen(mo, dict(OLLAMA)))

    # --- an explicit per-call value beats both ------------------------------
    backend = dict(OLLAMA, timeout=1200)
    check("an explicit backend timeout reaches generate",
          timeout_seen(mo, backend) == 1200, timeout_seen(mo, backend))

    # A backend dict without the key must still work: call_model is called from
    # several places and only the CLI path builds the full dict.
    check("a backend without a timeout key falls back to the default",
          timeout_seen(mo, dict(OLLAMA)) == 3600, timeout_seen(mo, dict(OLLAMA)))

    # --- the CLI flag ------------------------------------------------------
    mo = load()
    parser_args = mo.build_parser().parse_args(["draft.md"]) \
        if hasattr(mo, "build_parser") else None
    if parser_args is not None:
        check("--timeout defaults to DEFAULT_TIMEOUT",
              parser_args.timeout == 600, parser_args.timeout)
    else:
        # The parser is built inside main(); assert the flag exists by running
        # --help, which is the same surface a user meets.
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(HERE, "match_outline.py"),
                              "--help"], capture_output=True, text=True).stdout
        check("--timeout appears in --help", "--timeout" in out)
        check("--help states the environment variable",
              "MATCH_OUTLINE_TIMEOUT" in out)

    # --- no literal timeout left at the call site ---------------------------
    src = open(os.path.join(HERE, "match_outline.py")).read()
    check("no hard-coded timeout remains in the generate call",
          "timeout=600" not in src,
          "found a literal timeout=600")

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all timeout tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
