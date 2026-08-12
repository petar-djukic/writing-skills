#!/usr/bin/env python3
"""Load the instead->do pairs the tightening model is shown.

The pairs are the delivery mechanism for the rule catalog: GH-220/GH-222
measured that rules read as prose by an instruction-tuned model pull any text
toward that model's own register, so no model reads the rules — it sees pairs
and imitates the transformation.

Library:
  load()                 -> {rule_id: [ {instead, do, why, source}, ... ]}
  for_rules(rule_ids)    -> flat pair list for those rules, TS-01 always
                            included (needless words are universal)
  as_prompt(pairs)       -> the pairs formatted for a rewrite prompt

CLI: pairs.py [--rule TS-02] — print pairs, or all of them.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS_FILE = os.path.join(HERE, "..", "references", "tightening-pairs.yaml")


def load(path=None):
    import yaml
    with open(path or PAIRS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {k: v for k, v in data.items() if k.startswith("TS-")}


def for_rules(rule_ids, path=None):
    """Pairs for the given rules, deduplicated, TS-01 always present."""
    data = load(path)
    want = ["TS-01"] + [r for r in rule_ids if r != "TS-01"]
    out, seen = [], set()
    for r in want:
        for p in data.get(r, []):
            key = p["instead"]
            if key not in seen:
                seen.add(key)
                out.append({**p, "rule": r})
    return out


def as_prompt(pairs):
    """Format for the rewrite prompt: transformation only, no rule prose."""
    lines = []
    for i, p in enumerate(pairs, 1):
        lines.append(f"INSTEAD OF: {p['instead']}")
        lines.append(f"WRITE:      {p['do']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main():
    ap = argparse.ArgumentParser(description="show the tightening pairs")
    ap.add_argument("--rule", help="one rule id, e.g. TS-02")
    a = ap.parse_args()
    data = load()
    for rule in ([a.rule] if a.rule else sorted(data)):
        for p in data.get(rule, []):
            print(f"[{rule}] ({p['source']})")
            print(f"  instead: {p['instead']}")
            print(f"  do:      {p['do']}")
            print(f"  why:     {p['why']}")


if __name__ == "__main__":
    main()
