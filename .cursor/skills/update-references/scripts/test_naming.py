#!/usr/bin/env python3
"""Tests for _naming, which decides every filename the skill writes. Run:

    python3 test_naming.py

_naming.py is imported by arxiv.py, scholar.py and semantic_scholar.py so the
convention is byte-identical across fetchers, and by the repair migration that
reproduces it. It had no tests, which is why GH-35 was found by reading rather
than by a failure.

GH-35: paper_stem assembled <Family>-<Year>-<slug>-<source>-<id> and truncated
the whole string at 150 characters. The source tag sits last, so the cap cut
the one component that makes a stem unique — two papers by one author in one
year sharing their opening title words collapsed onto a single stem, and the
GH-28/GH-32 guards then had a collision to catch that need not have existed.

The property that makes the fix safe to land on existing paper directories is
asserted here: for every stem at or under the cap, the result is unchanged, so
`repair` renames nothing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _naming  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def naive_stem(family, year, title, **kw):
    """The pre-GH-35 assembly, minus the truncation.

    Used to state the compatibility property exactly: wherever this fits in
    STEM_MAX_LEN, paper_stem must return it verbatim.
    """
    fam = _naming._family_token(family)
    yr = str(year) if year else "nd"
    slug = _naming.title_slug(title)
    src = _naming._source_tag(kw.get("arxiv_id"), kw.get("version"),
                              kw.get("doi"), kw.get("citation_id"))
    stem = "-".join(p for p in (fam, yr, slug, src) if p)
    return re.sub(r"-{2,}", "-", stem).strip("-")


TITLE = "Autonomic control loops for wide area transport networks under load"
LONG_TITLE = " ".join(["autonomic"] * 8)      # drives the slug to its cap
# The worst plausible junk metadata: a PDF /Author whose text before the first
# comma is an institution, which parse_author_name hands back as a family name.
INSTITUTION = "Institute of Electrical and Electronics Engineers Standards Association"


def main():
    # --- the compatibility property -----------------------------------------
    # Anything that fits today must come back byte-identical, or landing this
    # renames files in every existing database.
    cases = [
        ("Djukic", 2007, TITLE, {"arxiv_id": "0704.12345", "version": 2}),
        ("Lamport", 1978, "Time clocks and the ordering of events", {}),
        ("van der Berg", 2021, TITLE, {"doi": "10.1109/TNSM.2021.1234567"}),
        ("Doe", None, TITLE, {"citation_id": "doe-nd"}),
        ("", 2024, "", {}),
        (INSTITUTION, 2025, TITLE, {"arxiv_id": "2501.12345", "version": 1}),
    ]
    unchanged = 0
    for family, year, title, kw in cases:
        naive = naive_stem(family, year, title, **kw)
        got = _naming.paper_stem(family, year, title, **kw)
        if len(naive) <= _naming.STEM_MAX_LEN:
            unchanged += 1
            check("stem under the cap is unchanged (%s)" % (family[:20] or "empty"),
                  got == naive, "%r != %r" % (got, naive))
    check("the compatibility case actually covered the realistic inputs",
          unchanged == len(cases), "%d of %d" % (unchanged, len(cases)))

    # --- the source tag survives, whatever else has to go -------------------
    for fam_len in (10, 66, 67, 80, 140, 200):
        stem = _naming.paper_stem("V" * fam_len, 2025, LONG_TITLE,
                                  arxiv_id="2501.12345", version=1)
        check("tag survives a %d-char family token" % fam_len,
              stem.endswith("arxiv-2501.12345v1"), stem[-30:])
        check("stem stays within the cap at family %d" % fam_len,
              len(stem) <= _naming.STEM_MAX_LEN, len(stem))

    # 67 is where the tag was cut before the fix — the boundary GH-35 measured.
    boundary = _naming.paper_stem("V" * 67, 2025, LONG_TITLE,
                                  arxiv_id="2501.12345", version=1)
    check("the slug is what gives way at the boundary, not the tag",
          "autonomic" in boundary and boundary.endswith("arxiv-2501.12345v1"),
          boundary)

    # --- the collision the issue is about ------------------------------------
    for fam_len in (10, 67, 90, 200):
        fam = "V" * fam_len
        a = _naming.paper_stem(fam, 2025, LONG_TITLE, arxiv_id="2501.12345", version=1)
        b = _naming.paper_stem(fam, 2025, LONG_TITLE, arxiv_id="2501.99999", version=1)
        check("same-month ids stay distinct at family %d" % fam_len, a != b,
              "both %r" % a[-24:])
    a = _naming.paper_stem("Doe", 2025, LONG_TITLE, arxiv_id="2501.12345", version=1)
    b = _naming.paper_stem("Doe", 2025, LONG_TITLE, arxiv_id="2501.12345", version=2)
    check("versions of one paper stay distinct", a != b)

    # A source tag past the whole budget is degenerate; the cap still holds.
    huge = _naming.paper_stem("Doe", 2025, TITLE, doi="10.1109/" + "x" * 400)
    check("an absurd DOI still respects the cap",
          len(huge) <= _naming.STEM_MAX_LEN, len(huge))

    # --- title_slug ----------------------------------------------------------
    check("slug takes the first eight words",
          _naming.title_slug("one two three four five six seven eight nine ten")
          == "one-two-three-four-five-six-seven-eight")
    check("slug caps at 60 characters",
          len(_naming.title_slug(" ".join(["abcdefghij"] * 8))) <= 60)
    check("slug drops punctuation and case", _naming.title_slug("Hello, World!") == "hello-world")
    check("empty title gives an empty slug", _naming.title_slug("") == "")

    # --- _family_token -------------------------------------------------------
    check("multi-part surnames collapse to one token",
          _naming._family_token("van der Berg") == "vanderBerg")
    check("case is kept", _naming._family_token("O'Neill") == "ONeill")
    check("an empty family becomes unknown", _naming._family_token("") == "unknown")
    check("a family of only punctuation becomes unknown",
          _naming._family_token("---") == "unknown")

    # --- citation_key --------------------------------------------------------
    check("a free key is used as is", _naming.citation_key("Lee", 2026, set()) == "lee-2026")
    check("a taken key gets a letter",
          _naming.citation_key("Lee", 2026, {"lee-2026"}) == "lee-2026a")
    check("letters advance past the first",
          _naming.citation_key("Lee", 2026, {"lee-2026", "lee-2026a"}) == "lee-2026b")
    exhausted = {"lee-2026"} | {"lee-2026%s" % c for c in "abcdefghijklmnopqrstuvwxyz"}
    check("past z it falls back to numbers",
          _naming.citation_key("Lee", 2026, exhausted) == "lee-2026-1", )
    check("a missing year becomes nd", _naming.citation_key("Lee", None, set()) == "lee-nd")
    check("a missing family becomes unknown",
          _naming.citation_key("", 2026, set()) == "unknown-2026")
    check("the key is lowercased and stripped",
          _naming.citation_key("van der Berg", 2026, set()) == "vanderberg-2026")

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all naming tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
