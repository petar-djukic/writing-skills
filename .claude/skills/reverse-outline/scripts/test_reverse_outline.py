#!/usr/bin/env python3
"""Offline tests for reverse-outline (GH-88).

The marker tree is what an author cuts paragraphs from, so a broken tree must
fail loudly rather than rank quietly — the same rule span_locks follows for
protection markers. These pin the grammar, every validation error, the strip
round trip, renumbering after a deletion, and the property the whole design
rests on: a marker survives a rewrite pass byte-identical and stays attached
to its paragraph.

No network, no model. Run: python3 <skill>/scripts/test_reverse_outline.py
"""
import os
import sys
import tempfile
import unittest

SK = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
for _d in (SHARED, SK):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import md_paragraphs                                        # noqa: E402
import prose_document                                       # noqa: E402
import rst_markers as rm                                    # noqa: E402

GOOD = """---
title: Strategy Theatre
thesis: a document that cannot say what, for whom, and for how much is not a strategy
---

## The Three Questions
<!-- rst: evidence | the three blanks every lender already enforces -->

<!-- rst: nucleus | a strategy answers what / who pays / how much -->
The difference between a real strategy and a document that looks like one is
whether it answers three questions that anyone lending money already asks.

<!-- rst: evidence | a bank's loan form enforces the same three blanks daily -->
A plumber financing a second truck fills in a form that will not accept a
diagram in place of a number, and the bank does this every working day.

<!-- rst: elaboration -> 2 | unpacks the loan-form analogy -->
The form has no box for a diagram, which is the whole of the comparison and
the reason it is worth making at all.

<!-- rst: restatement | says the three questions again -->
These questions are boring, which is exactly the point of asking them.
"""


def _write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _kinds(problems):
    return sorted({p.kind for p in problems})


class Grammar(unittest.TestCase):
    def test_parses_relation_target_and_gloss(self):
        m = rm.MARKER.match("<!-- rst: elaboration -> 2 | unpacks the analogy -->")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("relation"), "elaboration")
        self.assertEqual(m.group("target"), "2")
        self.assertEqual(m.group("gloss"), "unpacks the analogy")

    def test_target_is_optional(self):
        m = rm.MARKER.match("<!-- rst: nucleus | the point of the section -->")
        self.assertIsNotNone(m)
        self.assertIsNone(m.group("target"))

    def test_escaped_bang_spelling(self):
        m = rm.MARKER.match("<\\!-- rst: summary | says it shorter -->")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("relation"), "summary")

    def test_non_markers_are_not_matched(self):
        for line in ("<!-- lock -->", "<!-- subscribe-block -->",
                     "Ordinary prose about rst: labels.",
                     "<!-- rst: missing the pipe -->"):
            self.assertIsNone(rm.MARKER.match(line), line)

    def test_relation_set_is_closed_and_complete(self):
        self.assertEqual(len(rm.RELATIONS), 21)
        for name in ("nucleus", "split", "joint", "evidence", "restatement",
                     "elaboration", "solutionhood", "sequence"):
            self.assertIn(name, rm.RELATIONS)


class ParseAndDepth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = _write(self.tmp.name, "a.md", GOOD)
        self.o = rm.parse(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_unit_is_labelled(self):
        self.assertEqual(len(self.o.paragraphs), 4)
        self.assertTrue(all(u.labelled for u in self.o.units))
        self.assertEqual([u.relation for u in self.o.paragraphs],
                         ["nucleus", "evidence", "elaboration", "restatement"])

    def test_heading_is_a_unit_with_its_own_marker(self):
        head = [u for u in self.o.units if u.kind == "heading"]
        self.assertEqual(len(head), 1)
        self.assertEqual(head[0].relation, "evidence")
        self.assertIsNone(head[0].target)

    def test_positions_are_per_section(self):
        self.assertEqual([u.position for u in self.o.paragraphs], [1, 2, 3, 4])

    def test_depth_counts_hops_to_the_nucleus(self):
        by_pos = {u.position: u for u in self.o.paragraphs}
        self.assertEqual(self.o.depth(by_pos[1]), 0)     # the nucleus
        self.assertEqual(self.o.depth(by_pos[2]), 1)     # satellite of nucleus
        self.assertEqual(self.o.depth(by_pos[3]), 2)     # satellite of a satellite
        self.assertEqual(self.o.depth(by_pos[4]), 1)

    def test_valid_tree_has_no_problems(self):
        self.assertEqual(rm.check(self.o), [])


class Validation(unittest.TestCase):
    """Every violation the author must be told about, each failing loudly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, text):
        return rm.check(rm.parse(_write(self.tmp.name, "a.md", text)))

    def test_two_nuclei(self):
        bad = GOOD.replace(
            "<!-- rst: evidence | a bank's loan form enforces the same three blanks daily -->",
            "<!-- rst: nucleus | a second paragraph claiming to be the point -->")
        self.assertIn("two-nuclei", _kinds(self._check(bad)))

    def test_no_nucleus(self):
        bad = GOOD.replace(
            "<!-- rst: nucleus | a strategy answers what / who pays / how much -->",
            "<!-- rst: background | sets up the three questions -->")
        self.assertIn("no-nucleus", _kinds(self._check(bad)))

    def test_dangling_target(self):
        bad = GOOD.replace("elaboration -> 2", "elaboration -> 9")
        self.assertIn("dangling-target", _kinds(self._check(bad)))

    def test_self_target(self):
        bad = GOOD.replace("elaboration -> 2", "elaboration -> 3")
        self.assertIn("self-target", _kinds(self._check(bad)))

    def test_cycle(self):
        bad = GOOD.replace(
            "<!-- rst: evidence | a bank's loan form enforces the same three blanks daily -->",
            "<!-- rst: evidence -> 3 | points at the paragraph that points back -->")
        self.assertIn("cycle", _kinds(self._check(bad)))

    def test_unlabelled_paragraph(self):
        bad = GOOD.replace(
            "<!-- rst: restatement | says the three questions again -->\n", "")
        self.assertIn("unlabelled", _kinds(self._check(bad)))

    def test_unknown_relation(self):
        bad = GOOD.replace("rst: restatement |", "rst: repetition |")
        self.assertIn("unknown-relation", _kinds(self._check(bad)))

    def test_empty_gloss(self):
        bad = GOOD.replace("rst: restatement | says the three questions again",
                           "rst: restatement |  ")
        self.assertIn("empty-gloss", _kinds(self._check(bad)))

    def test_nucleus_may_not_carry_a_target(self):
        bad = GOOD.replace("rst: nucleus |", "rst: nucleus -> 2 |")
        self.assertIn("nucleus-target", _kinds(self._check(bad)))

    def test_heading_may_not_carry_a_target(self):
        bad = GOOD.replace(
            "<!-- rst: evidence | the three blanks every lender already enforces -->",
            "<!-- rst: evidence -> 1 | the three blanks -->")
        self.assertIn("heading-target", _kinds(self._check(bad)))

    def test_orphan_marker_is_reported(self):
        """A marker floating between blank lines labels nothing, and would be
        a silent no-op if it were not reported."""
        bad = GOOD.replace(
            "These questions are boring, which is exactly the point of asking them.",
            "These questions are boring, which is exactly the point of asking them.\n\n"
            "<!-- rst: summary | attached to nothing at all -->")
        self.assertIn("orphan-marker", _kinds(self._check(bad)))

    def test_problems_carry_line_numbers(self):
        bad = GOOD.replace("elaboration -> 2", "elaboration -> 9")
        problems = self._check(bad)
        self.assertTrue(all(isinstance(p.line, int) and p.line > 0
                            for p in problems), problems)


class Strip(unittest.TestCase):
    def test_removes_markers_and_nothing_else(self):
        out = rm.strip(GOOD)
        self.assertNotIn("rst:", out)
        for keep in ("## The Three Questions", "A plumber financing",
                     "title: Strategy Theatre", "These questions are boring"):
            self.assertIn(keep, out)

    def test_leaves_other_comments_alone(self):
        text = ("<!-- lock -->kept exactly<!-- /lock --> and prose after it.\n\n"
                "<!-- rst: nucleus | the point -->\n"
                "A paragraph with enough words to be extracted by the parser.\n\n"
                "<!-- subscribe-block -->\n")
        out = rm.strip(text)
        self.assertIn("<!-- lock -->kept exactly<!-- /lock -->", out)
        self.assertIn("<!-- subscribe-block -->", out)
        self.assertNotIn("rst:", out)

    def test_round_trip_restores_the_original(self):
        """strip(insert(strip(x))) == strip(x) — annotating and stripping
        cannot lose or move a byte of prose."""
        with tempfile.TemporaryDirectory() as tmp:
            bare = rm.strip(GOOD)
            src = rm.parse(_write(tmp, "src.md", GOOD))
            path = _write(tmp, "bare.md", bare)
            stripped = rm.parse(path)
            # Match units between the two versions by their own position.
            key = lambda u: (u.kind, u.section, u.position)
            want = {key(u): (u.relation, u.target, u.gloss) for u in src.units}
            by_line = {}
            for u in stripped.units:
                if key(u) in want:
                    by_line[u.line] = want[key(u)]
            annotated = rm.insert(path, by_line)
            self.assertEqual(rm.strip(annotated).rstrip("\n"), bare.rstrip("\n"))
            # And the re-annotated document is the document we started with.
            round_tripped = _write(tmp, "rt.md", annotated)
            self.assertEqual(rm.check(rm.parse(round_tripped)), [])


class Insert(unittest.TestCase):
    def test_refuses_to_write_inside_a_locked_span(self):
        text = ("Lead paragraph with enough words to be prose here.\n\n"
                "<!-- lock -->\n"
                "A block-locked paragraph the author wrote by hand.\n"
                "<!-- /lock -->\n\n"
                "Tail paragraph with enough words to be prose as well.\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", text)
            with self.assertRaises(rm.RstError):
                rm.insert(path, {4: ("nucleus", None, "inside the lock")})

    def test_rejects_a_relation_outside_the_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", rm.strip(GOOD))
            with self.assertRaises(rm.RstError):
                rm.insert(path, {6: ("invented", None, "not a relation")})


class Renumber(unittest.TestCase):
    """The pre/post diff. Positions alone cannot say which paragraph a target
    meant once its neighbours moved, so the supported path takes the pre-edit
    version and matches paragraphs by their gloss.

    The two deletions below are the two cases, and they differ by which
    paragraph went: delete the one a target POINTS AT and the repair cannot be
    inferred; delete any other and the referent simply sits somewhere new.
    """

    # The evidence paragraph is what `elaboration -> 2` points at.
    REFERENT_GONE = GOOD.replace(
        "<!-- rst: evidence | a bank's loan form enforces the same three blanks daily -->\n"
        "A plumber financing a second truck fills in a form that will not accept a\n"
        "diagram in place of a number, and the bank does this every working day.\n\n",
        "")
    # The nucleus goes; the referent survives and shifts from position 2 to 1.
    NUCLEUS_GONE = GOOD.replace(
        "<!-- rst: nucleus | a strategy answers what / who pays / how much -->\n"
        "The difference between a real strategy and a document that looks like one is\n"
        "whether it answers three questions that anyone lending money already asks.\n\n",
        "")

    def test_repairs_a_target_whose_referent_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = _write(tmp, "before.md", GOOD)
            after = _write(tmp, "after.md", self.NUCLEUS_GONE)
            text, problems = rm.renumber(after, against=before)
            self.assertIn("renumbered", _kinds(problems))
            self.assertIn("-> 1", text)
            self.assertNotIn("-> 2", text)

    def test_reports_when_the_referent_itself_was_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = _write(tmp, "before.md", GOOD)
            after = _write(tmp, "after.md", self.REFERENT_GONE)
            _text, problems = rm.renumber(after, against=before)
            self.assertIn("target-deleted", _kinds(problems))
            self.assertNotIn("renumbered", _kinds(problems))

    def test_without_a_reference_the_shift_is_only_visible_to_check(self):
        """No pre-edit version, so the moved target still looks in range. It
        now points at its own paragraph, which check reports."""
        with tempfile.TemporaryDirectory() as tmp:
            after = _write(tmp, "after.md", self.REFERENT_GONE)
            self.assertIn("self-target", _kinds(rm.check(rm.parse(after))))

    def test_repaired_document_validates(self):
        """The realistic edit: the nucleus is cut and the evidence promoted."""
        promoted = self.NUCLEUS_GONE.replace(
            "rst: evidence | a bank's loan form", "rst: nucleus | a bank's loan form")
        with tempfile.TemporaryDirectory() as tmp:
            before = _write(tmp, "before.md", GOOD)
            after = _write(tmp, "after.md", promoted)
            text, _ = rm.renumber(after, against=before)
            fixed = _write(tmp, "fixed.md", text)
            self.assertEqual(rm.check(rm.parse(fixed)), [])

    def test_valid_targets_are_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", GOOD)
            same = _write(tmp, "same.md", GOOD)
            text, problems = rm.renumber(path, against=same)
            self.assertEqual(problems, [])
            self.assertEqual(text.rstrip("\n"), GOOD.rstrip("\n"))

    def test_out_of_range_target_repaired_without_a_reference(self):
        bad = GOOD.replace("elaboration -> 2", "elaboration -> 7")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", bad)
            text, problems = rm.renumber(path)
            self.assertIn("renumbered", _kinds(problems))
            self.assertIn("-> 4", text)


class MarkerSurvival(unittest.TestCase):
    """The property the whole design rests on: markers ride the pipeline."""

    def test_marker_survives_a_prose_document_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", GOOD)
            before = rm.parse(path)
            target = before.paragraphs[1]
            marker_text = before.lines[target.marker_line - 1]

            doc = prose_document.ProseDocument.open(path)
            idx = next(p.index for p in doc.paragraphs
                       if "plumber financing" in p.text)
            doc.replace(idx, "A plumber buying a second truck fills in a form "
                             "that takes numbers and refuses diagrams.")
            doc.save()

            after = rm.parse(path)
            self.assertIn(marker_text, after.lines, "marker line not byte-identical")
            moved = next(u for u in after.paragraphs if u.position == 2)
            self.assertEqual(moved.relation, "evidence")
            self.assertEqual(moved.gloss, target.gloss)
            self.assertIn("plumber buying", moved.text)
            self.assertEqual(rm.check(after), [])

    def test_markers_are_comments_to_the_shared_extractor(self):
        """md_paragraphs must see markers as comment lines, and the prose
        paragraph count must not move when a document is annotated."""
        bare = rm.strip(GOOD)
        before = md_paragraphs.parse(bare)
        after = md_paragraphs.parse(GOOD)
        self.assertEqual(len(before.paragraphs), len(after.paragraphs))
        marker_lines = [ln for ln, raw in enumerate(GOOD.split("\n"), 1)
                        if "rst:" in raw]
        self.assertTrue(marker_lines)
        for ln in marker_lines:
            self.assertEqual(after.coverage.get(ln), "comment", f"line {ln}")

    def test_no_marker_text_reaches_a_paragraph(self):
        after = md_paragraphs.parse(GOOD)
        joined = "\n".join(t for _s, _e, t in after.paragraphs)
        self.assertNotIn("rst:", joined)


if __name__ == "__main__":
    unittest.main(verbosity=1)
