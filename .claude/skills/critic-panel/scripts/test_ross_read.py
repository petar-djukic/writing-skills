#!/usr/bin/env python3
"""Offline tests for the ross comprehension-read runner (GH-264)."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import converge
import ross_read

ARTICLE = """---
title: "T"
---

Opening paragraph with a claim.

![Two bars: $9 against $1.](figures/a.svg)

Middle paragraph.

![Split by meter: reads 64%.](figures/b.svg)

Closing paragraph.
"""

REPORT = """## Diagnosis
Three sentences here.
## Findings
### 1
Passage: Opening paragraph with a claim.
Finding: Reader knows nothing; the text assumes a claim.
Fix: Name the claim.
## Defect classes
### A
Class: Pattern.
Instance: Opening paragraph with a claim.
Sweep: Everywhere.
## Verdict
The reader loses the thread at the opening. Knows vs assumes. The fix: fix it.
"""


def write_article(directory, text=ARTICLE):
    path = os.path.join(directory, "2026-01-01-t.md")
    with open(path, "w") as f:
        f.write(text)
    return path


class CopyTest(unittest.TestCase):
    def test_alt_text_replaces_every_figure_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            copy = ross_read.reading_copy(write_article(d))
        self.assertNotIn("[figure]", copy)
        first = copy.index("[CHART THE READER SEES: Two bars: $9 against $1.]")
        second = copy.index("[CHART THE READER SEES: Split by meter: reads 64%.]")
        self.assertLess(first, second)

    def test_mismatched_figure_count_is_an_error(self):
        # An image inside an HTML comment: the alt scan sees it, prepare_copy
        # drops the comment, and the counts diverge rather than mislabel.
        broken = ARTICLE + "\n<!-- example: ![stray](figures/c.svg) -->\n"
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ross_read.reading_copy(write_article(d, broken))


class PromptTest(unittest.TestCase):
    def test_prompt_carries_persona_reader_and_every_protocol_clause(self):
        with tempfile.TemporaryDirectory() as d:
            p = ross_read.prompt(write_article(d))
        for needle in ("Harold Ross", ross_read.READER,
                       "Your confidence is not evidence",
                       "Read strictly forward",
                       "the sentence itself and the one just before it",
                       "nothing they could repeat to a colleague",
                       "what the reader knows at that point",
                       ross_read.CHART_NOTE, "## Verdict",
                       "never write replacement prose"):
            self.assertIn(needle, p)

    def test_article_file_is_never_written(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_article(d)
            before = open(path).read()
            ross_read.prompt(path)
            ross_read.reading_copy(path)
            self.assertEqual(open(path).read(), before)


class ReportPathTest(unittest.TestCase):
    def test_model_name_is_slugged(self):
        self.assertEqual(
            ross_read.report_path("a/2026-01-01-t.md", "kimi-k3.1-pro:cloud"),
            "a/2026-01-01-t.critic-ross-kimi-k3.1-pro-cloud.md")


class OllamaTest(unittest.TestCase):
    def run_with(self, payload):
        with tempfile.TemporaryDirectory() as d:
            return ross_read.run_ollama(
                write_article(d), "m", "http://x", 60000,
                opener=lambda req: io.StringIO(json.dumps(payload)))

    def test_report_content_is_returned(self):
        self.assertEqual(self.run_with({"message": {"content": REPORT}}), REPORT)

    def test_thinking_only_response_names_the_remedy(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_with({"message": {"content": "", "thinking": "x" * 10},
                           "done_reason": "length"})
        self.assertIn("num-predict", str(caught.exception))


class ConvergeTest(unittest.TestCase):
    def test_converge_parses_a_ross_report(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "2026-01-01-t.critic-ross-m.md")
            with open(path, "w") as f:
                f.write(REPORT)
            report = converge.parse(path)
        items = report["items"] if isinstance(report, dict) else report.items
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
