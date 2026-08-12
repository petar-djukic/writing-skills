#!/usr/bin/env python3
"""Tests for the diction-weight split (GH-245).

Run: python3 testdata/test_diction_weight.py

The hypothesis: when venue-voice anchors dominate retrieval, the model copies
their conversational register (filler, asides) — anchor drift, not a prose
defect. The fix: for_diction=True (the default, and what a rewrite wants) uses
a stronger author-voice weight so venue-voice needs a much larger relevance gap
to outrank author-voice for word choice.

These tests pin the split in both directions:
  - for_diction=True: stronger weight, author-voice dominates unless venue-voice
    is dramatically more relevant
  - for_diction=False: gentler weight, venue-voice wins on moderate relevance
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import voice_anchors as va  # noqa: E402

# Controlled corpus: software-ops passage (PUNCHY) is venue-voice, scheduling
# passage (ACADEMIC) is author-voice. Both are long enough to pass _passages.
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
    tmp = tempfile.mkdtemp(prefix="test-diction-weight-")
    try:
        # --- constants exist and have the right relationship ---
        assert hasattr(va, "AUTHOR_VOICE_WEIGHT")
        assert hasattr(va, "AUTHOR_VOICE_DICTION_WEIGHT")
        assert va.AUTHOR_VOICE_DICTION_WEIGHT > va.AUTHOR_VOICE_WEIGHT, \
            "diction weight must be stronger than shape weight"
        assert va.AUTHOR_VOICE_WEIGHT > 1.0
        assert va.AUTHOR_VOICE_DICTION_WEIGHT > 1.0
        print(f"  weights: shape={va.AUTHOR_VOICE_WEIGHT}, "
              f"diction={va.AUTHOR_VOICE_DICTION_WEIGHT}")

        d = corpus(tmp, [
            ("punchy.md", "venue-voice", PUNCHY),
            ("academic.md", "author-voice", ACADEMIC),
        ])

        # --- 1. for_diction=True uses the diction weight ---
        got = va.anchors(d, "Ship it and let the orchestrator run git.", k=2,
                         for_diction=True)
        for c in got:
            if c["role"] == "author-voice":
                expect = round(c["score"] * va.AUTHOR_VOICE_DICTION_WEIGHT, 4)
                assert abs(c["weighted"] - expect) < 1e-9, \
                    f"diction mode should use {va.AUTHOR_VOICE_DICTION_WEIGHT}x, " \
                    f"got weighted={c['weighted']} vs expected={expect}"

        # --- 2. for_diction=False uses the shape weight ---
        got = va.anchors(d, "Ship it and let the orchestrator run git.", k=2,
                         for_diction=False)
        for c in got:
            if c["role"] == "author-voice":
                expect = round(c["score"] * va.AUTHOR_VOICE_WEIGHT, 4)
                assert abs(c["weighted"] - expect) < 1e-9, \
                    f"shape mode should use {va.AUTHOR_VOICE_WEIGHT}x, " \
                    f"got weighted={c['weighted']} vs expected={expect}"

        # --- 3. The split changes outcomes at the boundary ---
        # A query where venue-voice is moderately more relevant (not 3x) but
        # the diction weight suppresses it. Use a mixed query that has partial
        # overlap with both registers.
        mixed_query = (
            "The agents run git operations on the scheduling framework and "
            "report latency across the repository state under load.")

        # Both modes should return at least one anchor.
        diction = va.anchors(d, mixed_query, k=2, for_diction=True)
        shape = va.anchors(d, mixed_query, k=2, for_diction=False)
        assert diction, "expected anchors in diction mode"
        assert shape, "expected anchors in shape mode"

        # In both modes, the first anchor wins by weighted score. Under the
        # stronger weight, author-voice is harder to beat.
        # Verify the weight actually makes a difference in the weighted scores.
        diction_author = [c for c in diction if c["role"] == "author-voice"]
        shape_author = [c for c in shape if c["role"] == "author-voice"]
        if diction_author and shape_author:
            assert diction_author[0]["weighted"] > shape_author[0]["weighted"], \
                "diction mode should give author-voice a higher weighted score"

        # --- 4. Extreme relevance still wins in diction mode ---
        # The orchestrator query is so much nearer PUNCHY that even 2.5x can't
        # save the academic passage.
        got = va.anchors(d, "Let the orchestrator run git, not the agents.", k=1,
                         for_diction=True)
        assert got, "expected an anchor even in diction mode"
        assert got[0]["role"] == "venue-voice", \
            "a dramatically more relevant venue-voice passage still wins"

        # --- 5. Equal similarity: author-voice wins under both modes ---
        same = corpus(os.path.join(tmp, "same"), [
            ("a.md", "author-voice", ACADEMIC),
            ("b.md", "venue-voice", ACADEMIC),
        ])
        for mode in (True, False):
            got = va.anchors(same, "We evaluate the scheduler under load.",
                             k=1, for_diction=mode)
            assert got[0]["role"] == "author-voice", \
                f"equal similarity: author-voice wins (for_diction={mode})"

        # --- 6. Default is for_diction=True (the diction weight) ---
        got_default = va.anchors(d, mixed_query, k=2)
        got_explicit = va.anchors(d, mixed_query, k=2, for_diction=True)
        assert got_default == got_explicit, \
            "default should be for_diction=True"

        # --- 7. for_diction still filters structure-only samples ---
        tagged = corpus(os.path.join(tmp, "tagged"), [])
        for name, role, tags in (("soft.md", "venue-voice", "[workflow, diction]"),
                                 ("shape.md", "venue-voice",
                                  "[workflow, structure-only]")):
            open(os.path.join(tagged, name), "w").write(PUNCHY)
            with open(os.path.join(tagged, "manifest.yaml"), "a") as f:
                f.write(f"  - id: {name[:-3]}\n    file: {name}\n"
                        f"    role: {role}\n    tags: {tags}\n")
        got_diction = va.anchors(tagged, "Ship it.", k=3,
                                 tags=["workflow"], for_diction=True)
        got_shape = va.anchors(tagged, "Ship it.", k=3,
                               tags=["workflow"], for_diction=False)
        diction_files = {c["file"] for c in got_diction}
        shape_files = {c["file"] for c in got_shape}
        assert "shape.md" not in diction_files, \
            "structure-only excluded from diction retrieval"
        assert "shape.md" in shape_files, \
            "structure-only available for shape retrieval"

        # --- 8. The weight cannot become a partition ---
        # Verify that AUTHOR_VOICE_DICTION_WEIGHT is not so high that it
        # effectively partitions (a reasonable venue-voice passage must still
        # be able to beat a dissimilar author-voice passage).
        assert va.AUTHOR_VOICE_DICTION_WEIGHT <= 4.0, \
            "weight too high — effectively a partition"

        print("test_diction_weight: all assertions passed (no network)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
