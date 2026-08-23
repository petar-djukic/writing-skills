#!/usr/bin/env python3
import os
import re
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



def _write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


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


class FigureCollapseTest(unittest.TestCase):
    """GH-102. Both halves of a markdown image nest, and a character class
    cannot count. `[^)]*` truncated at the first `)`; `[^\\]]*` was worse —
    it matched nothing at all, so alt text carrying a citation delivered the
    whole construct, markdown and URL, to a critic as prose."""

    def test_a_parenthesised_url_collapses_without_residue(self):
        self.assertEqual(
            prepare_copy.collapse_figures(
                "![alt](figures/throughput-(baseline).png)"),
            "[figure]", "the reported case: left '.png)' behind")

    def test_bracketed_alt_text_collapses_at_all(self):
        self.assertEqual(
            prepare_copy.collapse_figures("![see [1] for detail](fig.png)"),
            "[figure]", "previously not collapsed at all")

    def test_nesting_on_both_sides_at_depth(self):
        self.assertEqual(
            prepare_copy.collapse_figures("![a [b [c]] d](x-(y-(z)).png)"),
            "[figure]")

    def test_two_figures_collapse_independently(self):
        self.assertEqual(
            prepare_copy.collapse_figures(
                "![a](x.png) and ![b](y-(2).png) together"),
            "[figure] and [figure] together")

    def test_prose_around_a_figure_is_byte_intact(self):
        self.assertEqual(
            prepare_copy.collapse_figures("Before. ![x](a.png) After."),
            "Before. [figure] After.")

    def test_an_unterminated_construct_is_left_alone(self):
        """The guard that matters. Consuming to end of document would delete
        the article to tidy a caption — worse than the bug being fixed."""
        for src in ("![alt](unterminated.png",
                    "![alt unterminated](f.png",
                    "![no bracket close (f.png)"):
            self.assertEqual(prepare_copy.collapse_figures(src), src, src)

    def test_an_unterminated_construct_does_not_hide_a_later_figure(self):
        got = prepare_copy.collapse_figures(
            "![broken](no-close and then ![good](a.png) after")
        self.assertIn("[figure]", got, "the scan must recover")
        self.assertIn("![broken]", got, "and leave the broken one as text")

    def test_a_bare_link_is_not_a_figure(self):
        self.assertEqual(
            prepare_copy.collapse_figures("[link](url) is not a figure"),
            "[link](url) is not a figure")

    def test_empty_alt_text(self):
        self.assertEqual(prepare_copy.collapse_figures("![](x.png)"), "[figure]")

    def test_many_unclosed_openers_terminate(self):
        src = "![" * 200 + " no closes at all"
        self.assertEqual(prepare_copy.collapse_figures(src), src)

    def test_collapse_runs_inside_prepare(self):
        out = prepare_copy.prepare("Body ![alt](f-(1).png) end.\n")
        self.assertIn("[figure]", out)
        self.assertNotIn(".png", out)


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


VERDICT = """## Diagnosis
{diag}

## Findings
{findings}
## Verdict
{verdict}
"""

FINDING = """### {n}
Passage: {passage}
Finding: {finding}
Fix: {fix}

"""


def _verdict(tmp, name, diag, findings, verdict):
    """A verdict report; `findings` is a list of (passage, finding, fix)."""
    blocks = "".join(
        FINDING.format(n=i, passage=p, finding=f, fix=x)
        for i, (p, f, x) in enumerate(findings, 1))
    return _write(tmp, f"{name}.md",
                  VERDICT.format(diag=diag, findings=blocks, verdict=verdict))


class VerdictTest(unittest.TestCase):
    """GH-97. A diagnostician quotes the passage and names the defect; forcing
    that into `Replacement:` yields a line edit for a conceptual problem, so
    the kind is a parse-time distinction rather than a report-shape one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_verdict_report_parses(self):
        p = _verdict(self.t, "fowler", "Names a distinction it never defines.",
                     [("The layer mediates between intent and execution.",
                       "Used three ways in eight pages.",
                       "Define it once at first use.")],
                     "The concept is fuzzy.")
        r = converge.parse(p)
        self.assertEqual(r["kind"], "verdict")
        self.assertEqual(len(r["items"]), 1)
        item = r["items"][0]
        self.assertEqual(item["Passage"], "The layer mediates between intent and execution.")
        self.assertEqual(item["Finding"], "Used three ways in eight pages.")
        self.assertEqual(item["Fix"], "Define it once at first use.")
        self.assertEqual(item["quote"], item["Passage"], "grouping reads quote")
        self.assertEqual(r["verdict"], "The concept is fuzzy.")

    def test_two_verdict_critics_on_one_passage_converge(self):
        shared = "The layer mediates between intent and execution."
        a = _verdict(self.t, "fowler", "d", [(shared, "Used three ways.", "Define it.")], "v")
        b = _verdict(self.t, "yegge", "d", [(shared, "It is a job queue.", "Say what differs.")], "v")
        groups = converge.group([converge.parse(a), converge.parse(b)])
        conv = [g for g in groups if len({i["critic"] for i in g}) > 1]
        self.assertEqual(len(conv), 1)
        self.assertEqual({i["critic"] for i in conv[0]}, {"fowler", "yegge"})

    def test_a_diagnostician_and_an_adder_converge_on_one_passage(self):
        """The reason both kinds store their verbatim text under one key."""
        shared = "The layer mediates between intent and execution."
        a = _verdict(self.t, "fowler", "d", [(shared, "Used three ways.", "Define it.")], "v")
        b = _write(self.t, "levine.md", REPORT.format(rep="A queue that files intentions.",
                                                      solo=shared))
        reports = [converge.parse(a), converge.parse(b)]
        self.assertEqual([r["kind"] for r in reports], ["verdict", "suggest"])
        groups = converge.group(reports)
        conv = [g for g in groups if len({i["critic"] for i in g}) > 1]
        self.assertEqual(len(conv), 1)
        sheet = converge.render(reports, groups)
        self.assertIn("Used three ways.", sheet, "the verdict form")
        self.assertIn("A queue that files intentions.", sheet, "the suggest form")

    def test_summary_appears_only_when_a_verdict_critic_is_present(self):
        v = _verdict(self.t, "fowler", "d", [("p", "f", "x")], "verdict text")
        s = _write(self.t, "levine.md", REPORT.format(rep="R.", solo="S."))
        with_v = [converge.parse(v)]
        without = [converge.parse(s)]
        self.assertIn("## Summary", converge.render(with_v, converge.group(with_v)))
        self.assertNotIn("## Summary", converge.render(without, converge.group(without)))
        self.assertNotIn("## Verdicts", converge.render(without, converge.group(without)))

    def test_pass_and_needs_work_partition_on_zero_findings(self):
        clean = _verdict(self.t, "cook", "The opening works.", [], "The hook is strong.")
        dirty = _verdict(self.t, "fowler", "d", [("p", "f", "x")], "The concept is fuzzy.")
        reports = [converge.parse(clean), converge.parse(dirty)]
        sheet = converge.render(reports, converge.group(reports))
        self.assertIn("**Pass**: cook", sheet)
        self.assertIn("**Needs work**: fowler", sheet)

    def test_top_fixes_caps_the_list_not_the_findings(self):
        # Genuinely distinct sentences: near-identical strings group into one
        # under THRESHOLD, which is the grouping working, not a fixture.
        shared = ["The layer mediates between intent and execution.",
                  "Every agent run costs money nobody is tracking.",
                  "We shipped it on a Friday and regretted it by Monday.",
                  "Autonomy is the wrong axis for this taxonomy."]
        a = _verdict(self.t, "fowler", "d",
                     [(p, f"finding {i}", f"fix {i}") for i, p in enumerate(shared)], "v")
        b = _verdict(self.t, "yegge", "d",
                     [(p, f"other {i}", f"otherfix {i}") for i, p in enumerate(shared)], "v")
        reports = [converge.parse(a), converge.parse(b)]
        groups = converge.group(reports)
        conv = [g for g in groups if len({i["critic"] for i in g}) > 1]
        self.assertEqual(len(conv), 4, "four passages converged")
        sheet = converge.render(reports, groups)
        self.assertIn("**Top 3 fixes**", sheet)
        for p in shared:
            self.assertIn(p, sheet, "every convergent passage is still in the sheet")

    def test_roster_sets_sheet_order_and_file_order_is_the_default(self):
        a = _verdict(self.t, "fowler", "F diagnosis.", [("p1", "f", "x")], "v")
        b = _verdict(self.t, "cook", "C diagnosis.", [("p2", "f", "x")], "v")
        reports = [converge.parse(a), converge.parse(b)]
        self.assertEqual([r["critic"] for r in converge.order(reports, None)],
                         ["fowler", "cook"])
        self.assertEqual([r["critic"] for r in converge.order(reports, ["cook", "fowler"])],
                         ["cook", "fowler"])
        sheet = converge.render(converge.order(reports, ["cook", "fowler"]), converge.group(reports))
        self.assertLess(sheet.index("C diagnosis."), sheet.index("F diagnosis."))


class ContractTest(unittest.TestCase):
    """SKILL.md prints both report formats and the critics are told to follow
    them. Nothing made the printed format and the parser agree — and a spec
    the parser disagrees with is how converge.py came to emit a
    zero-suggestion sheet from three real reports (GH-107). These feed the
    documented blocks straight to parse()."""

    def _block(self, marker):
        with open(os.path.join(os.path.dirname(SK), "SKILL.md"),
                  encoding="utf-8") as f:
            skill = f.read()
        after = skill[skill.index(marker):]
        return after.split("```")[1]

    def _parses_as(self, marker, kind, tmp):
        # `<the exact sentence, verbatim>` stands in for real text.
        body = re.sub(r"<([^>]+)>", r"sample \1", self._block(marker))
        r = converge.parse(_write(tmp, "c.md", body))
        self.assertEqual(r["kind"], kind)
        self.assertTrue(r["items"], "the documented format parsed to nothing")
        return r

    def test_the_documented_suggest_format_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._parses_as("**`suggest`**", "suggest", tmp)
            self.assertIn("Replacement", r["items"][0])
            self.assertEqual(r["items"][0]["quote"], r["items"][0]["Original"])
            self.assertTrue(r["move"], "the paragraph move section")

    def test_the_documented_verdict_format_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._parses_as("**`verdict`**", "verdict", tmp)
            self.assertIn("Finding", r["items"][0])
            self.assertIn("Fix", r["items"][0])
            self.assertEqual(r["items"][0]["quote"], r["items"][0]["Passage"])
            self.assertTrue(r["verdict"], "the verdict section")


class GoldenSheetTest(unittest.TestCase):
    """The suggest path, pinned against the sheet the real Strategy Theatre
    panel actually produced — not against a fixture authored to match the
    parser. A synthetic fixture cannot catch a parser that disagrees with what
    critics really write, which is how converge.py came to emit a
    zero-suggestion sheet from three real reports without anyone noticing."""

    def test_a_suggest_only_run_reproduces_the_golden_sheet(self):
        td = os.path.join(SK, "testdata")
        paths = [os.path.join(td, f"{n}.md")
                 for n in ("levine", "didion", "hemingway")]
        reports = [converge.parse(p) for p in paths]
        got = converge.render(reports, converge.group(reports))
        with open(os.path.join(td, "panel2-golden-sheet.md"), encoding="utf-8") as f:
            self.assertEqual(got, f.read())

    def test_the_golden_inputs_are_all_suggest_kind(self):
        td = os.path.join(SK, "testdata")
        for n in ("levine", "didion", "hemingway"):
            r = converge.parse(os.path.join(td, f"{n}.md"))
            self.assertEqual(r["kind"], "suggest")
            self.assertTrue(r["items"], f"{n} parsed to zero items")


if __name__ == "__main__":
    unittest.main()
