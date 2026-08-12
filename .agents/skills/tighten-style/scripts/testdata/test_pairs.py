#!/usr/bin/env python3
"""Self-test for the tightening pairs. Run: python3 testdata/test_pairs.py

Enforces the two directions GH-224 demands, where the checker can see:
every `do:` side is clean, and every `instead:` side for a script-visible rule
fires the rule it illustrates. A pair whose wordy side does not exhibit its own
rule teaches the model nothing; a pair whose tight side trips the checker
teaches it the wrong thing.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check_style as cs  # noqa: E402
import pairs as pr        # noqa: E402

# Rules whose `instead:` side the script can verify fires. The judgment rules
# (TS-09, TS-16 spans, ...) still get the clean-do check. TS-03 is excluded:
# its checker is a fixed phrase list, and the best TS-03 pair — Strunk's own
# "was not very often on time" — is a shape the list cannot see. Dropping the
# best example to satisfy the test would be the tail wagging the dog.
SCRIPT_VISIBLE = {"TS-01", "TS-02", "TS-05", "TS-08", "TS-15"}


def findings(tmp, text):
    p = os.path.join(tmp, "t.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("# H\n\n" + text + "\n")
    return {x["rule"] for x in cs.check(p)}


def main():
    tmp = tempfile.mkdtemp(prefix="test-pairs-")
    try:
        data = pr.load()
        assert len(data) >= 8, f"expected pairs for 8+ rules, got {sorted(data)}"

        checked = fired = 0
        for rule, plist in data.items():
            assert plist, f"{rule} has no pairs"
            for p in plist:
                for k in ("instead", "do", "why", "source"):
                    assert p.get(k), f"{rule} pair missing {k}: {p}"
                assert p["source"] in ("strunk-1918", "plain-language", "generated"), p

                # Direction 1: the tight side is clean. TS-14 excepted — a
                # short fragment may use an abbreviation its document defines.
                got = findings(tmp, p["do"]) - {"TS-14"}
                assert not got, f"{rule} do-side trips {got}: {p['do']!r}"
                checked += 1

                # Direction 2: the wordy side fires its own rule, where the
                # script can see that rule.
                if rule in SCRIPT_VISIBLE:
                    got = findings(tmp, p["instead"])
                    assert rule in got, \
                        f"{rule} instead-side does not fire it (got {got}): " \
                        f"{p['instead']!r}"
                    fired += 1

        # TS-04's pairs carry genitive chains; the checker needs 3 distinct
        # nominalizations + a chain, which pair-length examples satisfy.
        got = findings(tmp, data["TS-04"][0]["instead"])
        assert "TS-04" in got, got

        # The prompt format shows transformations only — no rule ids, no rule
        # prose, nothing for a model to interpret as an instruction register.
        text = pr.as_prompt(pr.for_rules(["TS-02"]))
        assert "INSTEAD OF:" in text and "WRITE:" in text
        assert "TS-" not in text, "rule ids must not reach the prompt"
        assert "active voice" not in text.lower(), "rule prose must not reach the prompt"

        # for_rules always includes TS-01: needless words are universal.
        rules_present = {p["rule"] for p in pr.for_rules(["TS-05"])}
        assert "TS-01" in rules_present and "TS-05" in rules_present

        print(f"test_pairs: {checked} do-sides clean, {fired} instead-sides "
              f"fire their rule")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
