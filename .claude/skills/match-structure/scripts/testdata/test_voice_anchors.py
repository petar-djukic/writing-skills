#!/usr/bin/env python3
"""Offline tests for voice_anchors ranking. Run: python3 testdata/test_voice_anchors.py

Builds a synthetic writing-voice corpus in a temp directory, so the assertions
are about the ranking rule rather than about any particular corpus.

The bug these pin (GH-216): role used to be the first term of the sort tuple,
which made it a partition — every author-voice passage outranked every
venue-voice passage regardless of similarity. Retrieval found the right anchors
and discarded them.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import voice_anchors as va  # noqa: E402

# Two registers, deliberately disjoint in vocabulary so similarity is
# decidable. Paragraphs run past 40 words because _passages skips shorter ones —
# a sample built of one-line punches would yield no passages at all.
PUNCHY = (
    "Ship it. The tool runs git, not the agents, and that is the whole rule "
    "here. Agents branch when they should not. Agents merge when nobody asked. "
    "Agents lose work in ways you find out about later. Let the orchestrator "
    "run git and the entire class of problem simply goes away for good.\n\n"
    "Worktrees are cheap. Branches are cheap. Losing an afternoon of agent "
    "output because two of them raced on the same index is not cheap at all, "
    "so keep git in one place and let the agents do the work they are good at "
    "instead of fighting each other over the repository state.\n")
ACADEMIC = (
    "We evaluate the proposed scheduler under offered load and report the "
    "median latency across twenty independent runs of the experiment. The "
    "variance across runs is small enough that the median is representative "
    "of the underlying distribution for the configurations we consider here.\n\n"
    "The scheduling algorithm allocates one slot per link per frame, and we "
    "prove convergence under the stated assumptions on the arrival process. "
    "Simulation results confirm the analysis for network sizes up to sixty "
    "four nodes, with the delay bound holding in every configuration tested.\n")


def corpus(tmp, entries):
    """entries: [(filename, role, text)] -> writing-voice dir path."""
    d = os.path.join(tmp, "writing-voice")
    os.makedirs(d, exist_ok=True)
    lines = ["exemplars:"]
    for name, role, text in entries:
        with open(os.path.join(d, name), "w") as f:
            f.write(text)
        lines += [f"  - id: {name[:-3]}", f"    file: {name}", f"    role: {role}"]
    with open(os.path.join(d, "manifest.yaml"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return d


def main():
    tmp = tempfile.mkdtemp(prefix="test-anchors-")
    try:
        d = corpus(tmp, [
            ("punchy.md", "venue-voice", PUNCHY),
            ("academic.md", "author-voice", ACADEMIC),
        ])

        # 1. The regression. A venue-voice passage clearly nearer the draft must
        #    win — this is the exact shape of the GH-216 failure.
        got = va.anchors(d, "Let the orchestrator run git, not the agents.", k=1)
        assert got, "expected an anchor"
        assert got[0]["role"] == "venue-voice", (
            f"nearer venue-voice passage must outrank author-voice, got "
            f"{got[0]['role']} ({got[0]['file']})")

        # 2. The intent survives. On an academic passage the author's own prose
        #    is both nearer AND weighted, so it wins comfortably.
        got = va.anchors(d, "We evaluate the scheduler under offered load and "
                            "report median latency across runs.", k=1)
        assert got[0]["role"] == "author-voice", got[0]

        # 3. The weight is a tiebreak at comparable similarity, which is the
        #    behaviour the partition was crudely approximating.
        assert va.AUTHOR_VOICE_WEIGHT > 1.0
        near = corpus(os.path.join(tmp, "near"), [
            ("a.md", "author-voice", ACADEMIC),
            ("b.md", "venue-voice", ACADEMIC),   # identical text, differing role
        ])
        got = va.anchors(near, "We evaluate the scheduler under load.", k=1)
        assert got[0]["role"] == "author-voice", "equal scores: author-voice wins"

        # 4. Every anchor reports score, weighted, and role, so an
        #    inappropriate mix is visible without re-deriving it by hand.
        #    Default is for_diction=True, so the diction weight applies.
        for c in va.anchors(d, "Ship it.", k=2):
            assert {"score", "weighted", "role", "file", "text"} <= set(c), c
            expect = round(c["score"] * (va.AUTHOR_VOICE_DICTION_WEIGHT
                                         if c["role"] == "author-voice" else 1.0), 4)
            assert abs(c["weighted"] - expect) < 1e-9, c

        # 5. An explicit role still filters hard — the escape hatch the
        #    operator reaches for when they know what they want. Note it can
        #    legitimately return nothing: filtering to a role whose samples
        #    share no vocabulary with the passage should yield no anchors
        #    rather than irrelevant ones.
        got = va.anchors(d, "We evaluate the scheduler under load.", k=3,
                         role="author-voice")
        assert got and all(c["role"] == "author-voice" for c in got), got
        assert va.anchors(d, "Let the orchestrator run git.", k=3,
                          role="author-voice") == [], \
            "a hard filter with no topical match returns nothing, not noise"

        # 6. Stratum cuts ACROSS roles — the distinction role cannot express.
        strat = corpus(os.path.join(tmp, "strat"), [])
        import textwrap
        for name, role, yr, extra in (("old_paper.md", "author-voice", 2007, ""),
                                      ("old_punch.md", "venue-voice", 2011, ""),
                                      ("new_essay.md", "venue-voice", 2026, ""),
                                      ("claimed.md", "venue-voice", 2024,
                                       "    pre_ai: true\n")):
            open(os.path.join(strat, name), "w").write(ACADEMIC)
            with open(os.path.join(strat, "manifest.yaml"), "a") as f:
                f.write(f"  - id: {name[:-3]}\n    file: {name}\n"
                        f"    role: {role}\n    year: {yr}\n{extra}")
        pre = {os.path.basename(p) for p, _ in va.sample_paths(strat, pre_ai=True)}
        assert pre == {"old_paper.md", "old_punch.md", "claimed.md"}, pre
        #    ...and the curator's explicit flag beats the year: claimed.md is
        #    2024 but marked pre_ai, and it is included.
        assert "claimed.md" in pre and "new_essay.md" not in pre
        #    A pre-AI filter spans both roles, which --role alone cannot do.
        assert {r for _, r in va.sample_paths(strat, pre_ai=True)} == \
            {"author-voice", "venue-voice"}

        # 7. Tags select the pool; similarity still ranks WITHIN it. The
        #    register that fits is often the one LEAST topically similar, so
        #    this deliberately overrides similarity — measured on the reference
        #    corpus, tag selection returns Krugman at 0.04 over Yegge at 0.14.
        tagd = corpus(os.path.join(tmp, "tagged"), [])
        for name, role, tags in (("econ.md", "venue-voice", "[economics, diction]"),
                                 ("soft.md", "venue-voice", "[workflow, diction]"),
                                 ("shape.md", "venue-voice", "[workflow, structure-only]")):
            open(os.path.join(tagd, name), "w").write(
                ACADEMIC if name == "econ.md" else PUNCHY)
            with open(os.path.join(tagd, "manifest.yaml"), "a") as f:
                f.write(f"  - id: {name[:-3]}\n    file: {name}\n"
                        f"    role: {role}\n    tags: {tags}\n")
        sel = {os.path.basename(p) for p, _ in va.sample_paths(tagd, tags=["economics"])}
        assert sel == {"econ.md"}, sel

        #    structure-only is excluded from DICTION anchoring even when its
        #    other tags match — otherwise --anchor-tags workflow quietly admits
        #    a shape reference into a voice rewrite.
        sel = {os.path.basename(p) for p, _ in va.sample_paths(tagd, tags=["workflow"])}
        assert sel == {"soft.md"}, sel
        #    ...but it is available when asked for by name, or for shape.
        sel = {os.path.basename(p) for p, _ in va.sample_paths(tagd, tags=["structure-only"])}
        assert "shape.md" in sel, sel
        sel = {os.path.basename(p) for p, _ in
               va.sample_paths(tagd, tags=["workflow"], for_diction=False)}
        assert "shape.md" in sel, sel

        #    No tags passed: unchanged behaviour apart from the structure-only
        #    exclusion, which is the point of the label.
        sel = {os.path.basename(p) for p, _ in va.sample_paths(tagd)}
        assert sel == {"econ.md", "soft.md"}, sel

        #    A tag matching nothing yields nothing, rather than falling back to
        #    every sample — silently ignoring the filter would be worse.
        assert va.sample_paths(tagd, tags=["nonexistent"]) == []

        # 8. Nothing similar returns nothing rather than noise.
        assert va.anchors(d, "zzzz qqqq xxxx", k=3) == []

        # 9. An empty corpus is a normal state, not a crash.
        assert va.anchors(corpus(os.path.join(tmp, "empty"), []), "anything") == []

        print("test_voice_anchors: all assertions passed (no network)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
