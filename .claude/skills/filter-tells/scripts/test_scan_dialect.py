#!/usr/bin/env python3
"""detect-lexical.sh's gating scanner is ERE, and its anchors are sentence-aware.

    python3 test_scan_dialect.py

GH-43. `MECHANICAL_TRANSITIONS` held 19 patterns, every one anchored with `^`.
grep matches per line and a markdown paragraph is a single long line, so those
patterns fired only when the transition opened a paragraph — never on the
second or third sentence, which is where a transition usually sits. Nineteen
gating tells, mostly unable to fire.

Dropping the `^` is the wrong fix: bare "first," matches "the first, and
largest, deployment". The right form is `(^|[.!?] )` — line start or sentence
boundary — which `NARRATIVE_PIVOT_CANDIDATES` already used. That needs
alternation, so the gating scanner had to move from BRE to ERE.

Two properties are asserted, and the second is the one nobody would think to
check. The dialect switch is safe only because the gating arrays are literal
strings: 344 of 345 patterns hold no ERE metacharacter and read identically
either way. A future pattern with a bare `?`, `+` or `(` would silently change
meaning — quietly, since the scan would still run and still report something.
So the metacharacter census is a test, not a one-time audit.

The 345th pattern is why the switch was an improvement rather than a wash:
AI_PHRASES' `there are [0-9]+ main` was written as ERE and had been running as
BRE, where `+` is literal. It matched "there are 5+ main" and never "there are
3 main". Both halves are pinned below.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPT = os.path.join(HERE, "detect-lexical.sh")

# Arrays scanned by scan_patterns (gating). scan_candidates was already ERE.
GATING_ARRAYS = [
    "CHAT_RESIDUE", "BANNED_WORDS", "ACADEMIC_TELLS", "AI_PHRASES",
    "FALSE_EMPHASIS", "MECHANICAL_TRANSITIONS", "COT_STRUCTURAL",
    "NARRATIVE_PIVOTS", "MARKETING_JARGON",
]

# Metacharacters that mean something different in ERE than in BRE. A gating
# pattern containing one is either deliberate (and belongs in ALLOWED) or a
# silent change of meaning.
ERE_META = re.compile(r"[(){}|+?]")
ALLOWED = {
    "there are [0-9]+ main",          # ERE all along; BRE was the bug (GH-43)
}

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def scan(text, json_mode=False):
    """Run the scan over a document and return its stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        cmd = ["bash", SCRIPT, path] + (["--json"] if json_mode else [])
        return subprocess.run(cmd, capture_output=True, text=True).stdout


def categories(text):
    """The set of categories that fired, from --json.

    Asserted on rather than the printed pattern, because the printed pattern is
    the pattern's own spelling: a test that greps for "(^|[.!?] )first," passes
    the moment someone rewrites the pattern to bare "first,", which is exactly
    the wrong fix this file exists to reject.
    """
    out = scan(text, json_mode=True)
    return {m for m in re.findall(r'"category":\s*"([^"]+)"', out)}


def arrays():
    """{name: [pattern, ...]} for the gating arrays."""
    src = open(SCRIPT, encoding="utf-8").read()
    out = {}
    for name in GATING_ARRAYS:
        m = re.search(r"^%s=\(\n(.*?)^\)" % name, src, re.S | re.M)
        if m:
            out[name] = re.findall(r"""^\s*['"](.+?)['"]\s*$""", m.group(1), re.M)
    return out


def main():
    # --- a transition mid-paragraph is caught ----------------------------- #
    # The single-line shape real markdown takes. This is the bug.
    second = ("The factory generates logic at runtime. That said, composition "
              "has a ceiling.\n")
    third = ("The factory generates logic at runtime. Composition has a "
             "ceiling. With that in mind, the loop closes.\n")
    check("a transition on a paragraph's second sentence is caught",
          "mechanical-transition" in categories(second), categories(second))
    check("a transition on its third sentence is caught",
          "mechanical-transition" in categories(third), categories(third))

    # And still caught where it always was.
    check("a transition opening a paragraph is still caught",
          "mechanical-transition" in
          categories("That said, composition has a ceiling.\n"))

    # --- the false positives the anchor was protecting against ------------ #
    # Bare "first," would match "the first, and largest" — the naive fix. This
    # asserts the category does not fire at all, so rewriting the pattern
    # cannot make it pass.
    ordinals = ("The first, and largest, deployment ran for six months. We "
                "shipped the second, smaller one in March. The third, "
                "unrelated, cluster failed.\n")
    got = categories(ordinals)
    check("mid-sentence ordinals are not transitions",
          "mechanical-transition" not in got, got)
    check("a real sentence-initial ordinal still is",
          "mechanical-transition" in
          categories("The run ends. Finally, the loop closes.\n"))

    # --- the dialect census ------------------------------------------------ #
    total = 0
    offenders = []
    for name, pats in arrays().items():
        total += len(pats)
        for p in pats:
            if p in ALLOWED or p.startswith("(^|[.!?] )"):
                continue
            if ERE_META.search(p):
                offenders.append("%s: %r" % (name, p))
    check("the gating arrays were found", total > 300, total)
    check("no gating pattern silently changes meaning under ERE",
          not offenders,
          "%d unexpected: %s — an ERE metacharacter in a literal pattern means "
          "something different now; escape it or add it to ALLOWED with a "
          "reason" % (len(offenders), offenders[:3]))

    # --- the pattern the switch fixed -------------------------------------- #
    check("'there are N main' matches a digit, as written",
          "there are [0-9]+ main" in scan("There are 3 main reasons.\n"))
    check("it no longer matches only a literal plus sign",
          "there are [0-9]+ main" in scan("There are 12 main reasons.\n"))

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all scan dialect tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
