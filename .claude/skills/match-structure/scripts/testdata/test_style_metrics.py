#!/usr/bin/env python3
"""Tests for expanded writing metrics in style.py."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import style


class TestSyllableCount(unittest.TestCase):
    KNOWN = {
        "the": 1,
        "cat": 1,
        "table": 2,
        "beautiful": 3,
        "university": 5,
        "I": 1,
        "a": 1,
        "eye": 1,
        "simple": 2,
        "people": 2,
        "computer": 3,
        "information": 4,
        "understanding": 4,
    }

    def test_known_words(self):
        for word, expected in self.KNOWN.items():
            got = style._syllable_count(word)
            self.assertEqual(got, expected, f"{word}: expected {expected}, got {got}")


class TestReadability(unittest.TestCase):
    PASSAGE = (
        "The cat sat on the mat. "
        "It was a very good cat. "
        "The dog was also there. "
        "They played in the yard together."
    )

    def test_flesch_fields_present(self):
        m = style.text_metrics(self.PASSAGE)
        for key in ("flesch_reading_ease", "flesch_kincaid_grade",
                     "gunning_fog", "smog_index"):
            self.assertIn(key, m, f"missing {key}")
            self.assertIsInstance(m[key], float, f"{key} not float")

    def test_simple_text_high_flesch(self):
        m = style.text_metrics(self.PASSAGE)
        self.assertGreater(m["flesch_reading_ease"], 60,
                           "simple passage should score above 60 Flesch RE")
        self.assertLess(m["flesch_kincaid_grade"], 8,
                        "simple passage should be below grade 8 F-K")

    def test_formula_consistency(self):
        """Flesch RE and F-K grade move in opposite directions."""
        simple = "The cat sat. The dog ran. The bird flew."
        hard = ("The implementation of sophisticated algorithmic methodologies "
                "necessitates comprehensive understanding of computational "
                "complexity. Furthermore, the utilization of mathematical "
                "abstractions facilitates the derivation of theoretical bounds.")
        ms = style.text_metrics(simple)
        mh = style.text_metrics(hard)
        self.assertGreater(ms["flesch_reading_ease"], mh["flesch_reading_ease"])
        self.assertLess(ms["flesch_kincaid_grade"], mh["flesch_kincaid_grade"])


class TestLexicalDiversity(unittest.TestCase):
    def test_fields_present(self):
        text = "The cat sat on the mat. The dog sat on the log."
        m = style.text_metrics(text)
        for key in ("type_token_ratio", "corrected_ttr", "hapax_ratio", "yules_k"):
            self.assertIn(key, m)

    def test_repetitive_vs_diverse(self):
        repetitive = "The cat and the cat and the cat sat. The cat was the cat."
        diverse = ("Algorithms differ from heuristics. Computers execute programs. "
                   "Networks transport packets. Databases store records.")
        mr = style.text_metrics(repetitive)
        md = style.text_metrics(diverse)
        self.assertLess(mr["type_token_ratio"], md["type_token_ratio"])

    def test_ttr_range(self):
        text = "One two three four five six seven eight nine ten."
        m = style.text_metrics(text)
        self.assertGreater(m["type_token_ratio"], 0)
        self.assertLessEqual(m["type_token_ratio"], 1.0)

    def test_hapax_all_unique(self):
        text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa."
        m = style.text_metrics(text)
        self.assertAlmostEqual(m["hapax_ratio"], 1.0, places=1)

    def test_yules_k_repeated(self):
        text = "The cat the cat the cat the cat the cat the cat."
        m = style.text_metrics(text)
        self.assertGreater(m["yules_k"], 0)


class TestSyntactic(unittest.TestCase):
    def test_cv_present(self):
        text = "Short sentence. A much longer sentence with many more words in it."
        m = style.text_metrics(text)
        self.assertIn("sentence_length_cv", m)
        self.assertGreater(m["sentence_length_cv"], 0)

    def test_clause_length(self):
        text = "The cat sat, and the dog ran; the bird flew over the fence."
        m = style.text_metrics(text)
        self.assertIn("mean_clause_length", m)
        self.assertGreater(m["mean_clause_length"], 0)
        self.assertLess(m["mean_clause_length"], m["sentence_length_mean"])


class TestStylometrics(unittest.TestCase):
    def test_function_word_ratio(self):
        text = "The cat sat on the mat by the door in the hall."
        m = style.text_metrics(text)
        self.assertIn("function_word_ratio", m)
        self.assertGreater(m["function_word_ratio"], 0.3,
                           "this passage is heavy on function words")

    def test_punctuation_profile(self):
        text = ("First clause, second clause; third clause: elaboration. "
                "Another sentence — with a dash.")
        m = style.text_metrics(text)
        self.assertIn("punctuation_per_1000w", m)
        p = m["punctuation_per_1000w"]
        for key in ("commas", "semicolons", "em_dashes", "colons"):
            self.assertIn(key, p)
        self.assertGreater(p["commas"], 0)
        self.assertGreater(p["semicolons"], 0)


class TestParagraphCohesion(unittest.TestCase):
    def test_cohesion_present(self):
        text = ("Algorithms process data efficiently. They reduce computational time.\n\n"
                "Algorithms also handle large datasets. Processing scales linearly.\n\n"
                "Overall, algorithms improve performance. Efficiency gains compound.")
        m = style.text_metrics(text)
        self.assertIn("paragraph_cohesion", m)
        self.assertIsNotNone(m["paragraph_cohesion"])
        self.assertGreater(m["paragraph_cohesion"], 0)

    def test_single_paragraph_none(self):
        text = "Just one paragraph with a few sentences. Nothing else here."
        m = style.text_metrics(text)
        self.assertIsNone(m["paragraph_cohesion"])

    def test_related_vs_unrelated(self):
        related = ("Cats are domestic animals. They are popular pets worldwide.\n\n"
                   "Cats hunt mice and small birds. Domestic cats retain hunting instincts.\n\n"
                   "Cat owners provide food and shelter. Pet cats live longer than strays.")
        unrelated = ("Quantum mechanics describes particle behavior. Wave functions collapse.\n\n"
                     "Renaissance art flourished in Italy. Michelangelo painted the Sistine Chapel.\n\n"
                     "Volcanic eruptions reshape landscapes. Magma solidifies into igneous rock.")
        mr = style.text_metrics(related)
        mu = style.text_metrics(unrelated)
        self.assertGreater(mr["paragraph_cohesion"], mu["paragraph_cohesion"])


class TestPercentileAndHistogram(unittest.TestCase):
    def test_percentile_endpoints_and_median(self):
        vals = [1, 2, 3, 4, 5]
        self.assertEqual(style._percentile(vals, 0.0), 1)
        self.assertEqual(style._percentile(vals, 1.0), 5)
        self.assertEqual(style._percentile(vals, 0.5), 3)

    def test_percentile_interpolates(self):
        # halfway between 10 and 20
        self.assertAlmostEqual(style._percentile([10, 20], 0.5), 15.0)

    def test_percentile_empty_and_single(self):
        self.assertEqual(style._percentile([], 0.5), 0)
        self.assertEqual(style._percentile([7], 0.9), 7.0)

    def test_histogram_bucket_boundaries(self):
        h = style._histogram([1, 5, 6, 10, 11, 41, 500])
        self.assertEqual(h["1-5"], 2)
        self.assertEqual(h["6-10"], 2)
        self.assertEqual(h["11-15"], 1)
        self.assertEqual(h["41+"], 2)

    def test_histogram_counts_every_sentence(self):
        lengths = [3, 8, 17, 22, 29, 35, 60]
        self.assertEqual(sum(style._histogram(lengths).values()), len(lengths))


class TestBurstinessStats(unittest.TestCase):
    def test_none_on_empty(self):
        self.assertIsNone(style.burstiness_stats([]))

    def test_cv_is_stdev_over_mean(self):
        lengths = [5, 10, 15, 20]
        s = style.burstiness_stats(lengths)
        self.assertAlmostEqual(s["cv"], s["stdev"] / s["mean"], places=3)

    def test_uniform_text_has_zero_cv(self):
        s = style.burstiness_stats([12, 12, 12, 12])
        self.assertEqual(s["cv"], 0)
        self.assertEqual(s["stdev"], 0)

    def test_extremes_and_percentiles(self):
        s = style.burstiness_stats([2, 4, 6, 8, 40])
        self.assertEqual(s["min"], 2)
        self.assertEqual(s["max"], 40)
        self.assertEqual(s["median"], 6)
        self.assertEqual(s["sentences"], 5)

    def test_cv_separates_uniform_from_varied_prose(self):
        """The discriminative property the burstiness pass exists to move."""
        uniform = ("The system reads the file and writes the result. "
                   "The parser walks the tree and emits the nodes. "
                   "The driver loads the model and returns the text. "
                   "The gate checks the numbers and keeps the draft.")
        varied = ("The system reads the file. It works. "
                  "The parser walks the tree and emits the nodes it finds "
                  "along the way, which is more work than it sounds. Done. "
                  "The gate checks numbers.")
        flat = style.burstiness_stats(style.sentence_lengths(uniform))
        bursty = style.burstiness_stats(style.sentence_lengths(varied))
        self.assertLess(flat["cv"], bursty["cv"])


class TestBurstinessInProfile(unittest.TestCase):
    PASSAGE = ("The cat sat on the mat by the door. "
               "It slept. "
               "The dog ran through the yard and out the gate before anyone "
               "could stop him or call his name. "
               "Rain fell.")

    def test_new_fields_present(self):
        m = style.text_metrics(self.PASSAGE)
        for key in ("sentence_length_min", "sentence_length_max",
                    "sentence_length_median", "sentence_length_p10",
                    "sentence_length_p90", "sentence_length_histogram"):
            self.assertIn(key, m, f"missing {key}")

    def test_profile_agrees_with_burstiness_stats(self):
        m = style.text_metrics(self.PASSAGE)
        s = style.burstiness_stats(style.sentence_lengths(self.PASSAGE))
        self.assertEqual(m["sentence_length_cv"], s["cv"])
        self.assertEqual(m["sentence_length_min"], s["min"])
        self.assertEqual(m["sentence_length_max"], s["max"])
        self.assertEqual(m["sentence_length_histogram"], s["histogram"])

    def test_aggregatable_keys_in_metric_keys(self):
        for key in ("sentence_length_cv", "sentence_length_median",
                    "sentence_length_p10", "sentence_length_p90"):
            self.assertIn(key, style.METRIC_KEYS)

    def test_extrema_and_histogram_stay_out_of_metric_keys(self):
        """METRIC_KEYS entries are averaged across a corpus. A sample minimum
        and maximum move with sample size rather than with style, and the
        histogram is a dict — neither survives mean_of()."""
        for key in ("sentence_length_min", "sentence_length_max",
                    "sentence_length_histogram"):
            self.assertNotIn(key, style.METRIC_KEYS)

    def test_metric_keys_all_aggregate(self):
        m = style.text_metrics(self.PASSAGE)
        for key in style.METRIC_KEYS:
            v = m.get(key)
            self.assertNotIsInstance(v, dict, f"{key} is a dict, cannot aggregate")


class TestBurstinessDelta(unittest.TestCase):
    def test_signed_deltas(self):
        before = style.burstiness_stats([10, 10, 10, 10])
        after = style.burstiness_stats([4, 8, 12, 24])
        d = style.burstiness_delta(before, after)
        self.assertGreater(d["cv"]["delta"], 0)
        self.assertEqual(d["cv"]["before"], before["cv"])
        self.assertEqual(d["cv"]["after"], after["cv"])
        self.assertEqual(d["max"]["delta"], 14)

    def test_covers_every_scalar(self):
        s = style.burstiness_stats([3, 9, 21])
        d = style.burstiness_delta(s, s)
        self.assertEqual(set(d), set(style.BURSTINESS_SCALARS))
        self.assertTrue(all(v["delta"] == 0 for v in d.values()))


class TestBurstinessProfile(unittest.TestCase):
    TEXT = ("First paragraph runs long and then stops short. Yes.\n\n"
            "Second paragraph holds a single sentence of moderate length "
            "that carries on for a while without any real break in it.\n\n"
            "Third has two. Both of them are short enough to notice.\n")

    def _write(self):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as f:
            f.write(self.TEXT)
        self.addCleanup(os.unlink, path)
        return path

    def test_document_view(self):
        path = self._write()
        out = style.burstiness_profile(path)
        self.assertEqual(out["file"], path)
        self.assertGreater(out["document"]["sentences"], 3)
        self.assertNotIn("paragraphs", out)

    def test_per_paragraph_rows_carry_index(self):
        path = self._write()
        out = style.burstiness_profile(path, per_paragraph=True)
        self.assertTrue(out["paragraphs"], "expected at least one multi-sentence paragraph")
        for row in out["paragraphs"]:
            self.assertIn("index", row)
            self.assertGreaterEqual(row["sentences"], 2)

    def test_text_rendering_is_one_line_per_document(self):
        path = self._write()
        out = style.burstiness_profile(path)
        rendered = style.format_burstiness(out)
        lines = rendered.splitlines()
        self.assertEqual(len(lines), 2)          # document line + histogram
        self.assertIn("cv=", lines[0])
        self.assertTrue(lines[1].startswith("histogram"))

    def test_text_rendering_with_baseline_shows_delta(self):
        path = self._write()
        out = style.burstiness_profile(path)
        rendered = style.format_burstiness(out, baseline=out)
        self.assertIn("before", rendered)
        self.assertIn("after", rendered)
        self.assertIn("delta", rendered)


class TestExistingMetricsUnchanged(unittest.TestCase):
    """Verify existing fields still appear and behave the same."""

    def test_basic_fields(self):
        text = "The cat sat. The dog ran."
        m = style.text_metrics(text)
        for key in ("sentences", "words", "sentence_length_mean",
                     "sentence_length_stdev", "passive_per_100_sentences",
                     "hedges_per_1000_words", "top_sentence_openers"):
            self.assertIn(key, m, f"missing existing field {key}")

    def test_empty_returns_none(self):
        self.assertIsNone(style.text_metrics(""))


if __name__ == "__main__":
    unittest.main()
