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
