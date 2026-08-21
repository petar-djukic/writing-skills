#!/usr/bin/env python3
"""Offline tests for voice_critic.py (GH-57 sub-issue #60).

The judged dimensions run through stub judges; nothing touches a model or
the network. Fixtures carry known marker counts, locks, and snark
instances so every verdict is hand-checkable.
Run: python3 <skill>/scripts/test_voice_critic.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import voice_critic as vc  # noqa: E402

BANK = """\
purpose: test bank
markers:
- id: colon-verdict
  regex: '\\w: +[A-Za-z"'']'
  essay_target: 5.5
- id: em-dash
  regex: '—|--'
  essay_target: 8.0
- id: okay
  regex: '\\bokay\\b (case-insensitive)'
  essay_target: 0.0
- id: article-density
  regex: '\\b(the|a|an)\\b (case-insensitive)'
  essay_target: null
- id: sentence-length
  regex: 'split on [.!?] plus space'
  essay_target: 15.0
"""

CONSTITUTION = "# Voice constitution\n\nTest rubric stand-in.\n"


def make_repo(tmp, doc_text, bank=BANK, constitution=CONSTITUTION):
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd)
    if bank is not None:
        with open(os.path.join(vd, "idiolect.yaml"), "w") as f:
            f.write(bank)
    if constitution is not None:
        with open(os.path.join(vd, "voice-constitution.md"), "w") as f:
            f.write(constitution)
    path = os.path.join(tmp, "draft.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc_text)
    return path


# ~60 words per repetition, receipt-free, marker-free.
FILLER = ("The reviewers walked through every section of the build report "
          "and compared what they found against what the team believed "
          "about their own process, then wrote down where those two "
          "pictures diverged and what would have to change before anyone "
          "could trust the pipeline to run without a person watching it "
          "end to end each night. ")


class StubJudge:
    """Deterministic judge: canned answers, records calls."""

    def __init__(self, stance=None, tom=None, snark_by_para=None,
                 unhedged_by_para=None):
        self._stance = stance or {"verdict": "PASS", "note": "", "quotes": []}
        self._tom = tom or {"verdict": "PASS", "note": "", "quotes": []}
        self._snark = snark_by_para or {}
        self._unhedged = unhedged_by_para or {}
        self.snark_calls = 0
        self.unhedged_calls = 0

    def stance(self, text):
        return self._stance

    def tom(self, text):
        return self._tom

    def snark(self, paragraph):
        i = self.snark_calls
        self.snark_calls += 1
        return self._snark.get(i, [])

    def unhedged(self, paragraph):
        i = self.unhedged_calls
        self.unhedged_calls += 1
        return self._unhedged.get(i, [])


def test_refuses_without_rubric():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "draft.md")
        with open(path, "w") as f:
            f.write(FILLER + "\n")
        try:
            vc.Critic(path)
            assert False, "should refuse without writing-voice/"
        except SystemExit as e:
            assert "writing-voice" in str(e)
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, FILLER + "\n", constitution=None)
        try:
            vc.Critic(path)
            assert False, "should refuse without voice-constitution.md"
        except SystemExit as e:
            assert "voice-constitution" in str(e)
    print("  refuses_without_rubric: ok")


def test_read_only():
    text = FILLER + "\nThe verdict is simple: the gate held.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        with open(path, "rb") as f:
            before = f.read()
        vc.Critic(path).run()
        with open(path, "rb") as f:
            assert f.read() == before, "critic must never modify the input"
    print("  read_only: ok")


def test_marker_profile_hand_computed():
    # Exactly two colon-verdicts, one em-dash pair, one "okay".
    text = (FILLER +
            "The rule is simple: receipts land first. The other rule "
            "holds too: nobody ships unreviewed. The gate —the mechanical "
            "half— held, and everyone said okay.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        c = vc.Critic(path)
        rep = c.run()["dimensions"]["marker-profile"]
        words = c.words
        m = rep["markers"]
        assert m["colon-verdict"]["rate"] == round(2 * 1000.0 / words, 2)
        assert m["em-dash"]["rate"] == round(2 * 1000.0 / words, 2)
        assert m["okay"]["status"] == "over", "target-0 marker present"
        assert "article-density" not in m, "null target skipped"
        assert "sentence-length" not in m, "prose-spec marker skipped"
        assert rep["verdict"] == "FLAG"
    print("  marker_profile_hand_computed: ok")


def test_marker_profile_within_tolerance_passes():
    # One colon-verdict and one em-dash pair over ~200 words: colon rate
    # ~5.0 (target 5.5) and em-dash ~10.0 (target 8.0, hi 10.4) — inside.
    text = (FILLER * 3 +
            "The rule is simple: receipts land first —always— and the "
            "review holds every verdict to that ordering before anything "
            "ships to a reader anywhere, because a verdict that arrives "
            "ahead of its evidence reads as opinion and gets requeued.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        rep = vc.Critic(path).run()["dimensions"]["marker-profile"]
        assert rep["markers"]["colon-verdict"]["status"] == "ok", rep
        assert rep["markers"]["em-dash"]["status"] == "ok", rep
        assert rep["verdict"] == "PASS", rep
    print("  marker_profile_within_tolerance_passes: ok")


def test_disproportion_needs_a_lock():
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, FILLER + "\n")
        d = vc.Critic(path).run()["dimensions"]["disproportion"]
        assert d["verdict"] == "FLAG" and "lock" in d["note"]
    locked = (FILLER +
              "This stays <!-- lock -->the declared overrun, protected"
              "<!-- /lock --> in place.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, locked)
        d = vc.Critic(path).run()["dimensions"]["disproportion"]
        assert d["verdict"] == "PASS" and d["spans"]
    print("  disproportion_needs_a_lock: ok")


def test_tom_screen():
    full = (FILLER +
            "Maybe I'm wrong, but here's my model of the reviewer. "
            "I expect the gate to reject half the batch. "
            "It turned out the gate rejected all of it.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, full)
        d = vc.Critic(path).run()["dimensions"]["tom-device"]
        assert d["verdict"] == "PASS" and not d["missing_parts"]
        assert len(d["spans"]) == 3
    partial = FILLER + "Maybe I'm wrong, but here's my model of him.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, partial)
        d = vc.Critic(path).run()["dimensions"]["tom-device"]
        assert d["verdict"] == "FLAG"
        assert "prediction" in d["missing_parts"]
        assert "tested" in d["missing_parts"]
    print("  tom_screen: ok")


def test_unjudged_without_judge():
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, FILLER + "\n")
        dims = vc.Critic(path).run()["dimensions"]
        assert dims["stance"]["verdict"] == "UNJUDGED"
        assert dims["snark-audit"]["verdict"] == "UNJUDGED"
    print("  unjudged_without_judge: ok")


def test_snark_hard_rules():
    # Para 0: receipt-free filler. Para 1: receipt-free L1 (its
    # predecessor carries no receipt either — a receipt in the preceding
    # paragraph WOULD license the verdict, the factual-run-then-verdict
    # shape). Para 2: receipted L2 (clean) plus an L5 at a living person.
    text = (FILLER + "\n\n" +
            "A dry aside lands here with no evidence anywhere near it.\n\n" +
            "The vendor deck claims 99.9% uptime and the log shows 94%. "
            "Pointed irony lands here. "
            "And ridicule of a named person follows.\n")
    judge = StubJudge(snark_by_para={
        1: [{"quote": "A dry aside lands here", "level": 1,
             "target": "artifact"}],
        2: [{"quote": "Pointed irony lands here.", "level": 2,
             "target": "artifact"},
            {"quote": "And ridicule of a named person follows.", "level": 5,
             "target": "person"}],
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        rep = vc.Critic(path, judge=judge).run()
        d = rep["dimensions"]["snark-audit"]
        assert d["verdict"] == "FAIL"
        by_quote = {i["quote"]: i for i in d["instances"]}
        assert by_quote["Pointed irony lands here."]["violations"] == [], \
            "receipted L2 at a safe target is clean"
        aside = by_quote["A dry aside lands here"]
        assert any("receipt-first" in v for v in aside["violations"])
        l5 = by_quote["And ridicule of a named person follows."]
        assert any("L5" in v for v in l5["violations"])
        assert any("unsafe target" in v for v in l5["violations"])
        assert rep["verdict"] == "FAIL"
    print("  snark_hard_rules: ok")


def test_snark_density_cap():
    text = FILLER + "The log shows 94% uptime, and one dry aside follows.\n"
    judge = StubJudge(snark_by_para={
        0: [{"quote": "one dry aside follows", "level": 1,
             "target": "artifact"}]})
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        d = vc.Critic(path, form="essay", judge=judge).run()[
            "dimensions"]["snark-audit"]
        # ~70 words -> one L1 is ~14/1000, far over the essay cap of 2.
        assert d["verdict"] == "FAIL"
        assert "density" in d["note"] and "cap" in d["note"]
    big = FILLER * 10 + "The log shows 94% uptime, and one dry aside follows.\n"
    judge2 = StubJudge(snark_by_para={
        0: [{"quote": "one dry aside follows", "level": 1,
             "target": "artifact"}]})
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, big)
        d = vc.Critic(path, form="essay", judge=judge2).run()[
            "dimensions"]["snark-audit"]
        assert d["verdict"] == "PASS", d["note"]
        assert d["density_per_1000"] <= 2.0
    print("  snark_density_cap: ok")


def test_stance_judge_spans_located():
    text = FILLER + "\n\nThey never learn and never will.\n"
    judge = StubJudge(stance={"verdict": "FLAG",
                              "note": "contempt without curiosity",
                              "quotes": ["They never learn and never will."]})
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        d = vc.Critic(path, judge=judge).run()["dimensions"]["stance"]
        assert d["verdict"] == "FLAG"
        assert d["spans"] and d["spans"][0]["start_line"] > 1
    print("  stance_judge_spans_located: ok")


def test_unhedged_predictions():
    text = (FILLER + "\n\n" +
            "The reviewer wants the section gone because he hates asides. "
            "The build passed 14 of 15 checks on the second try.\n")
    judge = StubJudge(unhedged_by_para={
        1: [{"quote": "The reviewer wants the section gone because he "
                      "hates asides."},
            {"quote": "The build passed 14 of 15 checks on the second try."},
            {"quote": "A sentence that is not in the paragraph at all."}],
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        rep = vc.Critic(path, judge=judge).run()
        flags = rep["unhedged_predictions"]
        assert len(flags) == 1, flags
        assert flags[0]["paragraph"] == 1
        assert flags[0]["quote"].startswith("The reviewer wants")
        assert flags[0]["start_line"] > 1
        # The receipted sentence (14 of 15) and the absent quote are
        # filtered mechanically; the bank never hedges a receipted claim.
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        rep = vc.Critic(path).run()
        assert rep["unhedged_predictions"] == [], "no judge -> empty list"
    print("  unhedged_predictions: ok")


def test_all_five_reported_and_cli():
    text = FILLER + "\nThe verdict is simple: the gate held.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        rep = vc.Critic(path).run()
        assert set(rep["dimensions"]) == {
            "stance", "tom-device", "disproportion", "marker-profile",
            "snark-audit"}
        for d in rep["dimensions"].values():
            assert "verdict" in d and "spans" in d
        script = os.path.join(HERE, "voice_critic.py")
        out = os.path.join(tmp, "report.json")
        r = subprocess.run(
            [sys.executable, script, path, "--json", "--report", out],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        with open(out) as f:
            j = json.load(f)
        assert j["verdict"] in ("PASS", "FAIL")
        assert len(j["dimensions"]) == 5
    print("  all_five_reported_and_cli: ok")


def main():
    test_refuses_without_rubric()
    test_read_only()
    test_marker_profile_hand_computed()
    test_marker_profile_within_tolerance_passes()
    test_disproportion_needs_a_lock()
    test_tom_screen()
    test_unjudged_without_judge()
    test_snark_hard_rules()
    test_snark_density_cap()
    test_stance_judge_spans_located()
    test_unhedged_predictions()
    test_all_five_reported_and_cli()
    print("test_voice_critic: all assertions passed")


if __name__ == "__main__":
    main()
