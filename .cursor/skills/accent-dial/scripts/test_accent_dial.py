#!/usr/bin/env python3
"""Tests for accent_dial.py: gates, ranking, alignment, cap, and the dial's
prefix property at both grains."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SK = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SK)
import accent_dial as ad  # noqa: E402


class ParaGateTest(unittest.TestCase):
    def test_locked_span_ineligible(self):
        self.assertEqual(ad.para_gate("<!-- lock -->kept<!-- /lock -->",
                                      "changed"), "locked-span")

    def test_citation_drift(self):
        self.assertEqual(ad.para_gate("as shown [7] and [9].",
                                      "as shown [7] and [8]."),
                         "citation-drift")

    def test_number_drift(self):
        self.assertEqual(ad.para_gate("we saw 758 consultants win",
                                      "we saw 757 consultants win"),
                         "number-drift")

    def test_number_reformat_passes(self):
        # 3,000 vs 3.000 tokenizes to the same digit runs.
        self.assertIsNone(ad.para_gate(
            "a doctrine of 3,000 words, long and vague",
            "a doctrine of 3.000 words, long and empty"))

    def test_unchanged(self):
        self.assertEqual(ad.para_gate("same text", "same text"), "unchanged")

    def test_non_prose(self):
        self.assertEqual(ad.para_gate("## A Heading", "## Translated"),
                         "not-prose")


class SentenceMachineryTest(unittest.TestCase):
    def test_splitter(self):
        p = ('He asked the machine. It answered "Yes." The client was happy. '
             'Was that enough?')
        self.assertEqual(len(ad.split_sentences(p)), 4)

    def test_alignment_skips_split_sentences(self):
        orig = ["The consultant shipped hundreds of documents and never one "
                "product in his career."]
        rts = ["The consultant shipped hundreds of documents.",
               "He never shipped one product in his career."]
        pairs = ad.align_sentences(orig, rts)
        # DP matches the original to at most one half; the sentence-level
        # length gate must then kill it.
        for oi, ri, sim in pairs:
            self.assertEqual(ad.sent_gate(orig[oi], rts[ri], sim),
                             "length-drift")

    def test_quote_gate(self):
        o = 'They wrote "we are uniquely positioned" on slide two of the deck.'
        r = 'They wrote "we are in a unique position" on slide two of the deck.'
        self.assertEqual(ad.sent_gate(o, r, 0.9), "quote-drift")

    def test_quote_preserved_passes(self):
        o = 'They wrote "we are uniquely positioned" on slide two of the deck.'
        r = 'On slide two of the deck stood "we are uniquely positioned" plainly.'
        self.assertIsNone(ad.sent_gate(o, r, 0.7))

    def test_cap_enforced(self):
        ranked = [{"para": 0, "sent": s, "score": 10 - s} for s in range(5)]
        chosen = ad.select_capped(ranked, 4, 2)
        self.assertEqual(len(chosen), 2)

    def test_capped_selection_prefix_monotone(self):
        ranked = ([{"para": 0, "sent": s, "score": 9 - s} for s in range(3)]
                  + [{"para": 1, "sent": 0, "score": 1}])
        lo = {(c["para"], c["sent"]) for c in ad.select_capped(ranked, 1, 2)}
        hi = {(c["para"], c["sent"]) for c in ad.select_capped(ranked, 3, 2)}
        self.assertTrue(lo <= hi)


class ScoreTest(unittest.TestCase):
    def test_calque_dominates_restructure(self):
        orig = "He never found out what was missing from the plan."
        calqued = "He could not survive before them without the plan."
        rewritten = "The plan's missing piece stayed unknown to him forever."
        self.assertGreater(ad.score(orig, calqued), ad.score(orig, rewritten))


class DialRunTest(unittest.TestCase):
    def _run(self, dial, tmp, grain, extra=()):
        art = os.path.join(tmp, "a.txt")
        rt = os.path.join(tmp, "a.roundtrip.txt")
        paras = [(f"Original paragraph number {i} with some words. "
                  f"A second sentence sits here with more words in it.")
                 for i in range(6)]
        rts = [(f"Round-trip paragraph number {i} with other words. "
                f"A second sentence stands here with further words in it.")
               for i in range(6)]
        rts[2] = ("It stayed in one's head, paragraph number 2 with words. "
                  "A second sentence stands here with further words in it.")
        with open(art, "w") as f:
            f.write("\n\n".join(paras))
        with open(rt, "w") as f:
            f.write("\n\n".join(rts))
        out = os.path.join(tmp, f"out{grain}{dial}.txt")
        subprocess.run([sys.executable, os.path.join(SK, "accent_dial.py"),
                        "--article", art, "--roundtrip", rt,
                        "--dial", str(dial), "--grain", grain,
                        "--out", out, *extra],
                       check=True, capture_output=True)
        with open(out + ".log.json") as f:
            return json.load(f), open(out).read()

    def test_prefix_property_both_grains(self):
        for grain in ("sentence", "paragraph"):
            with tempfile.TemporaryDirectory() as tmp:
                sets = []
                for d in (0.0, 0.5, 1.0):
                    log, _ = self._run(d, tmp, grain)
                    sets.append({(c["para"], c.get("sent"))
                                 for c in log["candidates"] if c["applied"]})
                self.assertEqual(sets[0], set(), grain)
                self.assertTrue(sets[1] <= sets[2], grain)

    def test_calqued_sentence_applied_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, out = self._run(0.1, tmp, "sentence")
            applied = [(c["para"], c["sent"]) for c in log["candidates"]
                       if c["applied"]]
            self.assertEqual(applied, [(2, 0)])
            self.assertIn("in one's head", out)

    def test_sentence_grain_disperses(self):
        """At full dial with cap 1, every paragraph carries at most one
        swapped sentence — no paragraph is fully translated."""
        with tempfile.TemporaryDirectory() as tmp:
            log, out = self._run(1.0, tmp, "sentence",
                                 extra=("--max-per-para", "1"))
            per_para = {}
            for c in log["candidates"]:
                if c["applied"]:
                    per_para[c["para"]] = per_para.get(c["para"], 0) + 1
            self.assertTrue(all(v <= 1 for v in per_para.values()))
            # untouched second sentences survive verbatim
            self.assertIn("A second sentence sits here", out)


if __name__ == "__main__":
    unittest.main()
