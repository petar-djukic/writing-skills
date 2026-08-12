#!/usr/bin/env python3
"""Fixture test for extract_citations.py. Run: python3 testdata/test_extract_citations.py

Guards the three defects fixed in GH-173, all of which produced citation ids
the author never wrote. Every phantom id resolves against nothing in
references.yaml and is reported as a missing reference, so the audit's noise
scaled with how well-cited the document was.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import extract_citations as ec  # noqa: E402

SAMPLE = os.path.join(HERE, "sample_citations.md")

EXPECTED = [
    (7, "djukic-2007"),
    (9, "djukic-2007"), (9, "smith-2020"),
    (12, "a-2001"), (12, "b-2002"), (12, "c-2003"),
    (15, "kazman-2021"),
    (17, "nygard-2011"),
    (19, "bass-2021"),
    (21, "doi:10.1234/xyz"),
    (22, "smith.jones-2019"),
]


def main():
    got = [(r["line"], r["citation_id"]) for r in ec.extract_citations(SAMPLE)]
    ids = [c for _, c in got]

    # Exact set: anything extra is a phantom, anything missing is a real
    # citation the audit would never check.
    assert got == EXPECTED, (
        "extraction drifted\n"
        f"  expected: {EXPECTED}\n"
        f"  got:      {got}\n"
        f"  extra:    {[g for g in got if g not in EXPECTED]}\n"
        f"  missing:  {[e for e in EXPECTED if e not in got]}")

    # 1. Truncation (the reported bug). The last key of a multi-key bracket
    #    used to appear twice — whole, and one character short.
    assert "smith-202" not in ids, "truncated last key returned"
    #    ...and the middle key of a three-key bracket truncated too, because a
    #    semicolon follows it. This was worse than the issue described.
    assert "b-200" not in ids and "c-200" not in ids, "truncated middle key returned"

    # 2. Trailing punctuation. A sentence-final inline cite must not carry the
    #    period into the key.
    assert "nygard-2011." not in ids, "trailing period kept in key"
    assert ec.trim_key("nygard-2011.") == "nygard-2011"
    #    ...but internal punctuation is part of the key and must survive.
    assert ec.trim_key("doi:10.1234/xyz") == "doi:10.1234/xyz"
    assert "doi:10.1234/xyz" in ids and "smith.jones-2019" in ids

    # 3. Code fences. `in_code` was initialised inside the per-line loop, so it
    #    reset every iteration and the skip only covered the fence line itself.
    assert "not-a-citation" not in ids, "citation inside a code fence extracted"
    assert "also-not-one" not in ids, "string inside a code fence extracted"

    # An email is not a citation: the character before @ is a word character.
    assert not any(c.startswith("example") for c in ids), "email parsed as a citation"

    # Masking preserves offsets, so context and claim lookups stay aligned.
    line = "Two sources [@djukic-2007; @smith-2020] agree."
    assert len(ec.mask_brackets(line)) == len(line), "masking changed line length"
    assert "@" not in ec.mask_brackets(line), "bracket content survived masking"

    # Every result carries the context needed downstream.
    for r in ec.extract_citations(SAMPLE):
        assert r["claim"].strip(), f"{r['citation_id']} has an empty claim"
        assert r["context"].strip(), f"{r['citation_id']} has an empty context"

    print(f"test_extract_citations: {len(got)} citations, all assertions passed")


if __name__ == "__main__":
    main()
