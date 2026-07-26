#!/usr/bin/env python3
"""Offline tests for register_markers.py. Run: python3 test_register_markers.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import register_markers as rm  # noqa: E402

# The GH-220 control paragraph: textbook assistant register.
BUREAUCRATIC = (
    "Git operations are executed by the orchestrator rather than the agents. "
    "Grouping serves two primary purposes. A specific structural detail must "
    "be noted. The removal of the worktree is performed by the orchestrator. "
    "However, this pattern possesses its own failure modes. Therefore, the "
    "implementation of the verification is required before the integration.")

PLAIN = (
    "The orchestrator runs git, not the agents. The grouping does two jobs. "
    "One structural detail deserves attention before it becomes a bug. The "
    "orchestrator removes the worktree. This pattern has failure modes of its "
    "own. Verify first, then integrate.")


def main():
    b = rm.markers(BUREAUCRATIC)
    p = rm.markers(PLAIN)

    # 1. The bureaucratic control fires on every axis; the plain one is near
    #    zero. This pair IS the distinction the tool exists to measure.
    assert b["counts"]["passive"] >= 3, b["counts"]
    assert b["counts"]["agentive"] >= 2, b["counts"]
    assert b["counts"]["nominalization"] >= 5, b["counts"]
    assert b["counts"]["connectives"] == 2, b["counts"]
    assert p["counts"]["passive"] == 0, p["counts"]
    assert p["counts"]["agentive"] == 0
    assert p["counts"]["connectives"] == 0

    # 2. Direction, the thing reports rely on: bureaucratic sits far from
    #    plain, and each text sits at distance zero from itself.
    assert rm.distance(b, p) > 20, rm.distance(b, p)
    assert rm.distance(b, b) == 0.0

    # 3. Irregular participles are passives too — "is done", "was written"
    #    would otherwise slip the -ed pattern.
    m = rm.markers("The work is done by the team. The report was written by "
                   "the committee before the deadline passed quietly.")
    assert m["counts"]["passive"] >= 2 and m["counts"]["agentive"] >= 2, m["counts"]

    # 4. Adjectival be+participle is not a passive: flagging "is interested"
    #    would inflate ordinary prose and teach people to ignore the number.
    m = rm.markers("She is interested in the result. He was tired after the "
                   "long run and pleased with the outcome overall.")
    assert m["counts"]["passive"] == 0, m["counts"]

    # 5. Connectives count only at sentence starts — "however" mid-sentence is
    #    ordinary contrast, not the formal-transition tic.
    m = rm.markers("The result, however, held. However, the second run failed.")
    assert m["counts"]["connectives"] == 1, m["counts"]

    # 6. Empty text does not divide by zero.
    z = rm.markers("")
    assert z["words"] == 0 and z["per_1000"]["passive"] == 0.0

    print("test_register_markers: all assertions passed")


if __name__ == "__main__":
    main()
