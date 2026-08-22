#!/usr/bin/env python3
"""Tests for accent_dial.py: gates, ranking, and the dial's prefix property."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SK = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SK)
import accent_dial as ad  # noqa: E402


class GateTest(unittest.TestCase):
    def test_locked_span_ineligible(self):
        self.assertEqual(ad.gate("<!-- lock -->kept text<!-- /lock -->",
                                 "changed text"), "locked-span")

    def test_citation_drift(self):
        self.assertEqual(ad.gate("as shown [7] and [9].",
                                 "as shown [7] and [8]."), "citation-drift")

    def test_number_drift(self):
        self.assertEqual(ad.gate("we saw 758 consultants win",
                                 "we saw 757 consultants win"), "number-drift")

    def test_number_reformat_passes(self):
        # 3,000 vs 3.000 tokenizes to the same digit runs.
        self.assertIsNone(ad.gate("a doctrine of 3,000 words, long and vague",
                                  "a doctrine of 3.000 words, long and empty"))

    def test_length_drift(self):
        self.assertEqual(ad.gate("short one here", "this translation grew "
                                 "far far far beyond the original length "
                                 "and keeps growing"), "length-drift")

    def test_unchanged(self):
        self.assertEqual(ad.gate("same text", "same text"), "unchanged")

    def test_non_prose(self):
        self.assertEqual(ad.gate("## A Heading", "## A Heading translated"),
                         "not-prose")


class ScoreTest(unittest.TestCase):
    def test_calque_dominates_restructure(self):
        orig = "He never found out what was missing from the plan."
        calqued = "He could not survive before them without the plan."
        rewritten = "The plan's missing piece stayed unknown to him forever."
        self.assertGreater(ad.score(orig, calqued), ad.score(orig, rewritten))


class DialTest(unittest.TestCase):
    def _run(self, dial, tmp):
        art = os.path.join(tmp, "a.txt")
        rt = os.path.join(tmp, "a.roundtrip.txt")
        paras = [f"Original paragraph number {i} with some words." for i in
                 range(6)]
        rts = [f"Round-trip paragraph number {i} with other words." for i in
               range(6)]
        rts[2] = "It stayed in one's head, paragraph number 2 with words."
        with open(art, "w") as f:
            f.write("\n\n".join(paras))
        with open(rt, "w") as f:
            f.write("\n\n".join(rts))
        out = os.path.join(tmp, f"out{dial}.txt")
        subprocess.run([sys.executable, os.path.join(SK, "accent_dial.py"),
                        "--article", art, "--roundtrip", rt,
                        "--dial", str(dial), "--out", out],
                       check=True, capture_output=True)
        with open(out + ".log.json") as f:
            return json.load(f)

    def test_prefix_property(self):
        """Edits applied at a lower dial stay applied at every higher dial."""
        with tempfile.TemporaryDirectory() as tmp:
            sets = []
            for d in (0.0, 0.5, 1.0):
                log = self._run(d, tmp)
                sets.append({c["index"] for c in log["candidates"]
                             if c["applied"]})
            self.assertEqual(sets[0], set())
            self.assertTrue(sets[1] <= sets[2])
            self.assertEqual(len(sets[2]), log["gated"])

    def test_calqued_paragraph_applied_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            # One candidate out of six: index 2 carries the calque.
            log = self._run(0.17, tmp)
            applied = [c["index"] for c in log["candidates"] if c["applied"]]
            self.assertEqual(applied, [2])


if __name__ == "__main__":
    unittest.main()
