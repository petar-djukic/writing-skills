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
