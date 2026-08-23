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
import rank as rk                                           # noqa: E402
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

RUN = """---
title: Strategy Theatre
thesis: a document that cannot say what, for whom, and for how much is not a strategy
---

## Two legitimate stances
<!-- rst: elaboration | the stay-or-leave passage -->

<!-- rst: nucleus | the choice is stay or leave, and either is defensible -->
There are two honest responses to a company that has stopped deciding things,
and the choice between them is not a moral one.

<!-- rst: sequence | stay / leave / decide, in that order -->
Two legitimate stances present themselves, and they arrive in an order that
matters more than either one taken alone.

<!-- rst: elaboration -> 2 | unpacks the stay case -->
Staying means accepting that the documents will keep arriving and that reading
them is now part of the work rather than an interruption to it.

<!-- rst: joint -> 2 | the leave case -->
Leaving means the opposite, and the people who leave rarely say so at the time
they decide it.

<!-- rst: restatement -> 4 | says the stay case again -->
To stay is to treat the arriving documents as the work, which is the same
point made a second time in different clothes.

<!-- rst: evidence | the survey numbers, nothing to do with the run -->
A survey of four hundred managers put the median time spent on documents
nobody acts on at six hours a week.
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


class Ranking(unittest.TestCase):
    """Order is the product. It has to be reproducible and it has to put the
    cheap cuts first, or the author reads the sheet once and stops."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = rm.parse(_write(self.tmp.name, "a.md", GOOD))

    def tearDown(self):
        self.tmp.cleanup()

    def test_depth_dominates_then_cut_order(self):
        got = [(c["position"], c["depth"], c["relation"])
               for c in rk.candidates(self.o)]
        self.assertEqual(got, [(3, 2, "elaboration"),      # deepest
                               (4, 1, "restatement"),      # cut rank 2
                               (2, 1, "evidence")])        # cut rank 8, last

    def test_nucleus_is_never_a_candidate(self):
        self.assertNotIn("nucleus",
                         [c["relation"] for c in rk.candidates(self.o)])

    def test_multinuclear_spans_are_not_candidates(self):
        """Each span of a contrast/sequence/list carries its own content, so
        none of them is a satellite to be cut."""
        for relation in ("contrast", "sequence", "list"):
            text = GOOD.replace("rst: restatement |", f"rst: {relation} |")
            with tempfile.TemporaryDirectory() as tmp:
                o = rm.parse(_write(tmp, "a.md", text))
                self.assertNotIn(relation,
                                 [c["relation"] for c in rk.candidates(o)])

    def test_joint_sorts_first_even_when_shallow(self):
        text = GOOD.replace("rst: restatement |", "rst: joint |")
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", text))
            first = rk.candidates(o)[0]
            self.assertEqual(first["relation"], "joint")
            self.assertEqual(first["depth"], 1, "and it beat a depth-2 paragraph")

    def test_ties_break_on_document_order_so_the_sheet_is_reproducible(self):
        text = GOOD.replace("rst: restatement | says the three questions again",
                            "rst: elaboration -> 2 | a second unpacking of the analogy")
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", text))
            tied = [c for c in rk.candidates(o) if c["relation"] == "elaboration"]
            self.assertEqual([c["position"] for c in tied], [3, 4])
            self.assertEqual(rk.candidates(o), rk.candidates(o))

    def test_a_broken_tree_sorts_to_the_top_rather_than_vanishing(self):
        text = GOOD.replace("elaboration -> 2", "elaboration -> 9")
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", text))
            first = rk.candidates(o)[0]
            self.assertTrue(first["broken"])
            self.assertEqual(first["position"], 3)

    def test_sections_rank_against_the_thesis(self):
        rows = rk.sections(self.o)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["relation"], "evidence")
        self.assertEqual(rows[0]["paragraphs"], 4)

    def test_thesis_is_read_from_front_matter(self):
        self.assertIn("cannot say what, for whom", rk.thesis_of(self.o))

    def test_split_is_listed_as_a_rewrite_not_a_deletion(self):
        text = GOOD.replace("rst: restatement | says the three questions again",
                            "rst: split | argues two things at once")
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", text))
            self.assertEqual([s["position"] for s in rk.splits(o)], [4])
            self.assertNotIn("split", [c["relation"] for c in rk.candidates(o)])


class Runs(unittest.TestCase):
    """GH-94. A multinuclear label does two jobs — "these spans are peers in a
    structure the argument needs" and "these paragraphs form a run" — and the
    second is the shape an author cuts wholesale. The exclusion that was right
    for one span left the head of a five-paragraph run out of the sheet with
    nothing said about it, which is the part that had to stop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = rm.parse(_write(self.tmp.name, "a.md", RUN))

    def tearDown(self):
        self.tmp.cleanup()

    def _variant(self, old, new):
        text = RUN.replace(old, new)
        self.assertNotEqual(text, RUN, "fixture anchor moved")
        path = _write(self.tmp.name, "v.md", text)
        return rm.parse(path)

    def test_a_deletable_run_is_one_row_naming_its_span(self):
        rows = rk.runs(self.o)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "2\u20135")
        self.assertEqual(rows[0]["relation"], "sequence")
        self.assertEqual(rows[0]["paragraphs"], 4)

    def test_the_run_head_no_longer_disappears(self):
        """The regression itself: p2 carries no cut rank, so it has no row in
        the candidates table and never will. Before GH-94 that was the end of
        it — nothing in the sheet mentioned the paragraph at all."""
        sheet = rk.build(self.o)
        self.assertNotIn(2, [c["position"] for c in sheet["candidates"]])
        text = rk.render(sheet)
        self.assertIn("### Runs, cut whole", text)
        self.assertIn("2\u20135", text)

    def test_members_keep_their_own_rows_and_carry_the_run_label(self):
        sheet = rk.build(self.o)
        labelled = {c["position"]: c["run"] for c in sheet["candidates"]}
        self.assertEqual(labelled[3], "2\u20135")
        self.assertEqual(labelled[4], "2\u20135")
        self.assertEqual(labelled[5], "2\u20135")
        self.assertIsNone(labelled[6], "the evidence paragraph is outside the run")

    def test_the_run_is_ranked_by_its_best_member(self):
        best = rk.runs(self.o)[0]["best"]
        self.assertEqual(best["position"], 4)
        self.assertEqual(best["relation"], "joint", "joint outranks depth")

    def test_a_split_inside_the_run_disqualifies_it(self):
        """`split` is a rewrite candidate, so a run carrying one is not a
        clean whole-run cut. Saying so beats ranking it."""
        o = self._variant("rst: restatement -> 4 |", "rst: split -> 4 |")
        sheet = rk.build(o)
        self.assertEqual(sheet["runs"], [])
        self.assertEqual([u["position"] for u in sheet["excluded_multinuclear"]], [2])
        self.assertIsNone(sheet["candidates"][0]["run"])

    def test_a_lone_multinuclear_paragraph_is_named_not_dropped(self):
        o = self._variant("rst: evidence | the survey numbers",
                          "rst: contrast | held against the survey")
        sheet = rk.build(o)
        left = [(u["position"], u["relation"]) for u in sheet["excluded_multinuclear"]]
        self.assertIn((6, "contrast"), left)
        self.assertIn("6 `contrast`", rk.render(sheet))

    def test_a_document_with_no_multinuclear_labels_renders_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = rk.build(rm.parse(_write(tmp, "a.md", GOOD)))
        self.assertEqual(sheet["runs"], [])
        self.assertEqual(sheet["excluded_multinuclear"], [])
        text = rk.render(sheet)
        self.assertNotIn("Runs, cut whole", text)
        self.assertNotIn("Excluded as multinuclear", text)

    def test_grouping_follows_targets_not_adjacency(self):
        """Paragraph numbers go non-contiguous the moment a cycle lands, so a
        run is what the targets say it is, not what sits next to what."""
        o = self._variant("rst: elaboration -> 2 | unpacks the stay case",
                          "rst: evidence | unrelated support")
        rows = rk.runs(o)
        self.assertEqual(rows[0]["label"], "2, 4, 5")
        self.assertEqual(rows[0]["paragraphs"], 3)

    def test_peers_sharing_relation_and_target_form_one_run(self):
        o = self._variant("rst: joint -> 2 | the leave case",
                          "rst: sequence | the leave case")
        rows = rk.runs(o)
        self.assertEqual(len(rows), 1, "both sequence spans are one group")
        self.assertEqual(sorted(rows[0]["positions"]), [2, 3, 4, 5])

    def test_a_cycle_inside_a_run_terminates_and_sorts_to_the_top(self):
        o = self._variant("rst: sequence | stay / leave / decide, in that order",
                          "rst: sequence -> 3 | stay / leave / decide")
        rows = rk.runs(o)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["best"]["broken"], "check has already said so")

    def test_a_paragraph_in_two_nested_runs_is_named_in_both(self):
        """A `list` hanging off a `sequence` peer sits inside both runs.
        Picking one label silently is the habit GH-94 exists to break."""
        o = self._variant("rst: joint -> 2 | the leave case",
                          "rst: list -> 2 | the leave case")
        sheet = rk.build(o)
        self.assertEqual(len(sheet["runs"]), 2)
        held = {c["position"]: c["run"] for c in sheet["candidates"]}
        self.assertIn(";", held[5], "p5 is in the sequence run and the list run")

    def test_a_bracketed_joint_is_named_on_the_run_row(self):
        """GH-99. `annotate` writes `joint` when nothing attaches, so a joint
        paragraph carries no `-> n` and the closure cannot reach it. The run
        then reports fewer paragraphs than the page shows, and extent is what
        the row exists to report."""
        o = self._variant("rst: joint -> 2 | the leave case",
                          "rst: joint | the leave case")
        row = rk.runs(o)[0]
        # p5 targets p4, so detaching p4 takes p5 out of the run too: the run
        # shrinks to 2-3 and the joint lands one past the end rather than
        # inside it. That is the shape that loses the most paragraphs.
        self.assertEqual(row["label"], "2\u20133")
        self.assertEqual(row["paragraphs"], 2, "membership is unchanged")
        self.assertEqual([u["position"] for u in row["unattached"]], [4])
        self.assertEqual(row["unattached"][0]["depends"], 1, "p5 went with it")
        self.assertIn("brackets p4 `joint` +1", rk.render(rk.build(o)))

    def test_a_joint_strictly_inside_the_span_is_named_too(self):
        """The other shape: nothing depends on the joint, so the run keeps its
        later members and the joint sits in the middle of them."""
        text = RUN.replace("rst: joint -> 2 | the leave case",
                           "rst: joint | the leave case")
        text = text.replace("rst: restatement -> 4 | says the stay case again",
                            "rst: restatement -> 3 | says the stay case again")
        row = rk.runs(rm.parse(_write(self.tmp.name, "in.md", text)))[0]
        self.assertEqual(row["label"], "2, 3, 5")
        self.assertEqual(row["paragraphs"], 3)
        self.assertEqual([u["position"] for u in row["unattached"]], [4])
        self.assertEqual(row["unattached"][0]["depends"], 0)

    def test_a_joint_that_attaches_is_a_member_not_a_bracket(self):
        row = rk.runs(self.o)[0]
        self.assertEqual(row["paragraphs"], 4)
        self.assertEqual(row["unattached"], [], "it joined; nothing to report")

    def test_a_targetless_elaboration_is_not_named(self):
        """It attaches to the section nucleus, which is a real statement about
        where it belongs. `joint` says the tree reaches it nowhere, and
        flattening the two would cost the distinction."""
        o = self._variant("rst: joint -> 2 | the leave case",
                          "rst: elaboration | the leave case")
        self.assertEqual(rk.runs(o)[0]["unattached"], [])

    def test_a_joint_beyond_the_abutting_position_is_not_named(self):
        """The run reaches to `hi + 1` and no further. A joint past that might
        belong to the passage, but nothing in the markers says so."""
        text = RUN.replace("rst: joint -> 2 | the leave case",
                           "rst: evidence -> 2 | the survey supports it")
        text += ("\n<!-- rst: joint | a trailing orphan -->\n"
                 "A trailing paragraph the argument does not reach at all.\n")
        path = _write(self.tmp.name, "trail.md", text)
        row = rk.runs(rm.parse(path))[0]
        self.assertEqual(max(row["positions"]), 5)
        self.assertEqual(row["unattached"], [],
                         "the trailing joint is at 7; the run reaches 6")

    def test_a_run_bracketing_nothing_renders_as_before(self):
        sheet = rk.render(rk.build(self.o))
        self.assertIn("### Runs, cut whole", sheet)
        self.assertNotIn("brackets", sheet)

    def test_the_bracketed_joint_keeps_its_own_candidate_row(self):
        """Naming it on the run does not remove it from the ranking, where it
        still sorts first as the cheapest finding the skill produces."""
        o = self._variant("rst: joint -> 2 | the leave case",
                          "rst: joint | the leave case")
        cands = rk.build(o)["candidates"]
        joint = [c for c in cands if c["relation"] == "joint"]
        self.assertEqual([c["position"] for c in joint], [4])
        self.assertEqual(cands[0]["relation"], "joint", "still rank 1")

    def test_runs_are_reproducible(self):
        self.assertEqual(rk.runs(self.o), rk.runs(self.o))
        self.assertEqual(rk.render(rk.build(self.o)), rk.render(rk.build(self.o)))


class Repetition(unittest.TestCase):
    def _pairs(self, gloss_a, gloss_b):
        text = GOOD.replace(
            "rst: evidence | a bank's loan form enforces the same three blanks daily",
            f"rst: evidence | {gloss_a}").replace(
            "rst: restatement | says the three questions again",
            f"rst: evidence | {gloss_b}")
        with tempfile.TemporaryDirectory() as tmp:
            return rk.repetitions(rm.parse(_write(tmp, "a.md", text)))

    def test_near_duplicate_glosses_pair(self):
        pairs = self._pairs("a bank's loan form enforces the three blanks",
                            "a bank's loan form enforces those three blanks")
        self.assertEqual(len(pairs), 1, pairs)
        self.assertEqual((pairs[0]["a"], pairs[0]["b"]), (2, 4))

    def test_same_relation_but_different_content_does_not_pair(self):
        pairs = self._pairs("a bank's loan form enforces the three blanks",
                            "the plumber walks out without the second truck")
        self.assertEqual(pairs, [])

    def test_different_targets_do_not_pair(self):
        """Same words about different paragraphs is not repetition."""
        text = GOOD.replace(
            "rst: elaboration -> 2 | unpacks the loan-form analogy",
            "rst: elaboration -> 2 | unpacks the analogy").replace(
            "rst: restatement | says the three questions again",
            "rst: elaboration -> 1 | unpacks the analogy")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rk.repetitions(rm.parse(_write(tmp, "a.md", text))), [])


class Sheet(unittest.TestCase):
    def test_render_has_the_four_sections_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", GOOD))
            text = rk.render(rk.build(o))
        for heading in ("## 1. The outline", "## 2. Deletion candidates",
                        "## 3. Repetition pairs", "## 4. Paragraphs to split"):
            self.assertIn(heading, text)
        self.assertIn("Nothing here has been cut", text)

    def test_ranking_does_not_modify_the_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.md", GOOD)
            rk.render(rk.build(rm.parse(path)))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), GOOD)

    def test_missing_thesis_is_said_out_loud(self):
        no_thesis = GOOD.replace(
            "thesis: a document that cannot say what, for whom, and for how much is not a strategy" + chr(10), "")
        with tempfile.TemporaryDirectory() as tmp:
            o = rm.parse(_write(tmp, "a.md", no_thesis))
            self.assertIn("No `thesis:` line", rk.render(rk.build(o)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
