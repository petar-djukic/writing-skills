#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

SK = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SK)
import converge  # noqa: E402
import prepare_copy  # noqa: E402

REPORT = """## Diagnosis
It explains its receipts.
## Suggestions
### 1
Original: This is the problem in a single, very scary, experiment.
Replacement: {rep}
Buys: the number carries the fear.
### 2
Original: {solo}
Replacement: Something else.
Buys: pace.
## Paragraph move
Cut the last section.
"""


class PrepareTest(unittest.TestCase):
    def test_locks_marked_and_refs_dropped(self):
        src = ("---\ntitle: x\n---\nBody <!-- lock -->kept<!-- /lock --> "
               "![alt](f.png)\n\n## REFERENCES\n[1] ref\n")
        out = prepare_copy.prepare(src)
        self.assertIn("[[LOCKED: kept :LOCKED]]", out)
        self.assertIn("[figure]", out)
        self.assertNotIn("REFERENCES", out)
        self.assertNotIn("title:", out)


    def test_an_rst_marker_with_an_arrow_is_stripped(self):
        """GH-96. `[^>]*` stops at the first `>`, which in `-> 8` is inside the
        marker, so the pattern never matched and the marker survived whole —
        machine annotation handed to a critic as prose."""
        src = ("<!-- rst: elaboration -> 8 | Extends the published cases -->\n"
               "Real prose.\n")
        out = prepare_copy.prepare(src)
        self.assertNotIn("<!--", out)
        self.assertNotIn("rst:", out)
        self.assertNotIn("elaboration", out)
        self.assertIn("Real prose.", out)

    def test_a_marker_without_an_arrow_still_strips(self):
        """The case that already worked; it is here so a future rewrite of the
        pattern cannot fix the arrow and break the plain one."""
        out = prepare_copy.prepare("<!-- rst: nucleus | the point -->\nProse.\n")
        self.assertEqual(out.strip(), "Prose.")

    def test_a_multi_line_comment_strips(self):
        src = "<!-- a comment\nspanning two lines -->\nProse.\n"
        self.assertEqual(prepare_copy.prepare(src).strip(), "Prose.")

    def test_locks_survive_the_general_strip(self):
        """The ordering constraint: locks are converted before the strip runs,
        so they no longer look like comments when it does."""
        src = ("<!-- lock -->kept<!-- /lock -->\n\n"
               "<!-- rst: joint -> 3 | unattached -->\nAfter.\n")
        out = prepare_copy.prepare(src)
        self.assertIn("[[LOCKED: kept :LOCKED]]", out)
        self.assertNotIn("joint", out)
        self.assertIn("After.", out)

    def test_prose_around_a_stripped_marker_is_untouched(self):
        src = ("Before the marker.\n\n"
               "<!-- rst: evidence -> 2 | the survey numbers -->\n"
               "After the marker.\n")
        out = prepare_copy.prepare(src)
        self.assertIn("Before the marker.", out)
        self.assertIn("After the marker.", out)
        self.assertNotIn("survey", out)

    def test_two_markers_do_not_swallow_the_prose_between_them(self):
        """Why non-greedy. `<!--.*-->` with DOTALL matches from the first
        opener to the last closer and takes the article with it."""
        src = ("<!-- rst: nucleus | one -->\nKeep this paragraph.\n\n"
               "<!-- rst: elaboration -> 1 | two -->\nAnd this one.\n")
        out = prepare_copy.prepare(src)
        self.assertIn("Keep this paragraph.", out)
        self.assertIn("And this one.", out)


class ConvergeTest(unittest.TestCase):
    def test_convergence_grouping(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, rep, solo in (("a", "One experiment.", "Alpha only."),
                                    ("b", "One table.", "Beta only.")):
                p = os.path.join(tmp, f"{name}.md")
                with open(p, "w") as f:
                    f.write(REPORT.format(rep=rep, solo=solo))
                paths.append(p)
            reports = [converge.parse(p) for p in paths]
            groups = converge.group(reports)
            conv = [g for g in groups if len(g) > 1]
            self.assertEqual(len(conv), 1)
            self.assertEqual({s["critic"] for s in conv[0]}, {"a", "b"})
            sheet = converge.render(reports, groups)
            self.assertLess(sheet.index("very scary"), sheet.index("Alpha only"))
            self.assertIn("Cut the last section.", sheet)


if __name__ == "__main__":
    unittest.main()
