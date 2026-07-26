#!/usr/bin/env python3
"""Offline tests for check_style.py. Run: python3 testdata/test_check_style.py

No network. Synthetic documents in a temp directory, so the assertions are
about the rules rather than about any particular corpus.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check_style as cs  # noqa: E402


def run(tmp, body, name="d.md"):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return cs.check(p)


def rules(findings):
    return [f["rule"] for f in findings]


def main():
    tmp = tempfile.mkdtemp(prefix="test-tighten-")
    try:
        # TS-01 needless words, TS-03 negative form, TS-05 intensifiers.
        f = run(tmp, "# H\n\nIt should be noted that in order to proceed we did "
                     "not remember the very simple rule that applies here.\n")
        assert "TS-01" in rules(f) and "TS-03" in rules(f) and "TS-05" in rules(f)

        # TS-08 fires on a STACK, not on a single honest hedge. One hedge is
        # calibration; flagging it would push writers toward false confidence.
        one = run(tmp, "# H\n\nThe result may depend on the sampling rate used "
                       "throughout this particular experimental configuration.\n")
        assert "TS-08" not in rules(one), "a single hedge must not fire"
        many = run(tmp, "# H\n\nThis may perhaps possibly suggest that the "
                        "effect seems to be somewhat relevant in general.\n")
        assert "TS-08" in rules(many), "a hedge stack must fire"

        # TS-15 term-of-art exception is load-bearing: the same word is a
        # finding in one context and correct in the other.
        f = run(tmp, "# H\n\nThe critical section was guarded by a mutex lock "
                     "held for the whole duration of the update operation.\n")
        assert "TS-15" not in rules(f), "'critical section' is a term of art"
        f = run(tmp, "# H\n\nThis is a critical improvement to the overall "
                     "quality of the generated output in every scenario.\n")
        assert "TS-15" in rules(f), "bare 'critical' should fire"

        # TS-14: an abbreviation is reported once per section, not per use, and
        # not when the document defines it.
        f = run(tmp, "# H\n\nThe RRM module allocates. The RRM module also "
                     "schedules. The RRM module reports on all of this.\n")
        assert rules(f).count("TS-14") == 1, "report an abbreviation once per section"
        f = run(tmp, "# H\n\nRadio Resource Management (RRM) allocates blocks. "
                     "The RRM module also schedules them across the frame.\n")
        assert "TS-14" not in rules(f), "defined abbreviation must not fire"
        f = run(tmp, "# H\n\nThe JSON payload arrived over HTTP from the API "
                     "endpoint that the CPU had been waiting on for a while.\n")
        assert "TS-14" not in rules(f), "common abbreviations are exempt"

        # Non-prose is out of scope: code fences and headings are not prose,
        # and flagging them would bury real findings in noise.
        f = run(tmp, "# A very critical heading\n\n```python\n"
                     "# it should be noted that this is code\nx = 1\n```\n\n"
                     "Ordinary prose here that says something plain and short.\n")
        assert not rules(f), f"code and headings must be out of scope: {f}"

        # Clean prose produces nothing — the skill must be usable without
        # crying wolf on writing that is already tight.
        f = run(tmp, "# H\n\nThe scheduler allocates one slot per link. "
                     "Latency fell from 40 ms to 12 ms across twenty runs.\n")
        assert not f, f"clean prose should be silent, got {rules(f)}"

        # Findings carry the rule ID, a line number, and a fix.
        f = run(tmp, "# H\n\nIt should be noted that this sentence exists here "
                     "for the purpose of carrying a single detectable finding.\n")
        assert f and all(x["rule"].startswith("TS-") and x["line"] > 0 for x in f)
        assert any(x["fix"] for x in f), "findings should suggest a fix"

        print("test_check_style: all assertions passed (no network)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
