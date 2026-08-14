#!/usr/bin/env python3
"""Every CoT catalog category has a decided detection owner. Run:

    python3 test_cot_coverage.py

GH-40: the catalog grew to 14 categories while Prompt 4 kept enumerating the
original 7. Nothing was wrong with either file on its own, so nothing failed —
seven categories were simply never scanned semantically, and it took a reader
comparing the two documents to notice.

The reconciliation is not "put all of them in Prompt 4". Some are owned by a
regex (a closed set of imperatives does not need a language model), and one is
owned by a different prompt. What must not happen again is a category with no
decision recorded anywhere. That is what this file asserts:

    every `## Category N` in cot-leakage-patterns.md is either
      (a) enumerated in Prompt 4's type list, or
      (b) carries a `**Detection ownership` note saying who owns it instead.

Add a category and forget to place it, and this fails.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "references")
CATALOG = os.path.join(REFS, "cot-leakage-patterns.md")
PROMPTS = os.path.join(REFS, "perplexity-prompts.md")
LEXICAL = os.path.join(HERE, "detect-lexical.sh")

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def catalog_sections():
    """{number: section text} for every '## Category N: ...' in the catalog."""
    text = open(CATALOG, encoding="utf-8").read()
    parts = re.split(r"^## Category (\d+):", text, flags=re.M)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def prompt4_types():
    """The category numbers Prompt 4 enumerates."""
    text = open(PROMPTS, encoding="utf-8").read()
    start = text.index("## Prompt 4:")
    body = text[start:text.index("## Prompt 5:", start)]
    return {int(m) for m in re.findall(r"^(\d+)\. [A-Z][A-Z -]+:", body, re.M)}


def lexical_hits(sample):
    """Run detect-lexical.sh over a sample and return its stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sample.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample)
        return subprocess.run(["bash", LEXICAL, path], capture_output=True,
                              text=True).stdout


def main():
    sections = catalog_sections()
    in_prompt = prompt4_types()

    check("the catalog parses into categories", len(sections) >= 14, len(sections))
    check("Prompt 4 enumerates categories by their catalog number",
          in_prompt and max(in_prompt) <= max(sections),
          "prompt=%s catalog max=%s" % (sorted(in_prompt), max(sections)))

    # --- the invariant ---------------------------------------------------- #
    unplaced = []
    for num, body in sorted(sections.items()):
        if num in in_prompt:
            continue
        if "**Detection ownership" in body:
            continue
        unplaced.append(num)
    check("every category is either in Prompt 4 or says who owns it instead",
          not unplaced,
          "unplaced: %s — add it to Prompt 4's type list, or give the catalog "
          "entry a '**Detection ownership (GH-N):**' note" % unplaced)

    # A category cannot be in both places, or two passes rule one sentence.
    both = [n for n in sorted(in_prompt & set(sections))
            if "**Detection ownership" in sections[n]]
    check("no category is both in Prompt 4 and delegated elsewhere", not both, both)

    # --- the lexical claims those notes make ------------------------------ #
    # Each delegated category asserts a regex covers it. If the regex does not,
    # the note is a promise the scan does not keep.
    for num, sample, label in [
        (10, "Runtime generation is what separates a factory from a library.\n",
         "inverted wh-cleft"),
        (11, "Imagine a network that loses its uplink.\n", "imperative 'Imagine'"),
        (11, "Suppose the telemetry stops arriving.\n", "imperative 'Suppose'"),
        (11, "Take the case of a partial rollback.\n", "'Take the case of'"),
        (12, "The agent is not just a program but an orchestrator.\n",
         "correlative 'not just ... but'"),
    ]:
        out = lexical_hits(sample)
        check("Category %d: the scan catches %s" % (num, label),
              sample.strip()[:40] in out, out[-200:])

    # Category 13 is deliberately NOT lexical: the tell is whether the count
    # matches the list that follows, which no regex can see. If this ever
    # starts firing, the division of labour has drifted.
    out = lexical_hits("Three failure modes recur across deployments.\n")
    check("Category 13 is left to the semantic pass, not the regex",
          "Three failure modes" not in out, out[-160:])

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all CoT coverage assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
