#!/usr/bin/env python3
"""Offline tests for inject_vernacular.py (GH-57 sub-issue #59).

Everything runs against a synthetic writing-voice/idiolect.yaml so each
operator can be driven across its target from a small fixture. No model,
no network: the verifier is exercised through an injected judge.
Run: python3 <skill>/scripts/test_inject_vernacular.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import inject_vernacular as iv  # noqa: E402


BANK_TEMPLATE = """\
purpose: test bank
markers:
- id: colon-verdict
  regex: '\\w: +[A-Za-z"'']'
  essay_target: {colon_verdict}
- id: em-dash
  regex: '—|--'
  essay_target: {em_dash}
- id: antithesis-not
  regex: ', not '
  essay_target: {antithesis}
- id: kind-of
  regex: '\\bkind of\\b (case-insensitive)'
  essay_target: {kind_of}
- id: okay
  regex: '\\bokay\\b (case-insensitive)'
  essay_target: 0.0
- id: you-know
  regex: '\\byou know\\b (case-insensitive)'
  essay_target: 0.0
- id: right-tag
  regex: '\\bright\\?'
  essay_target: 0.0
- id: so-initial
  regex: '(?:^|[.!?] +)So\\b,?'
  essay_target: {so_initial}
- id: ai-connectives
  regex: '\\b(however|moreover|furthermore|additionally)\\b (case-insensitive)'
  essay_target: 0.0
- id: i-think
  regex: '\\bI think\\b'
  essay_target: {i_think}
- id: maybe
  regex: '\\bmaybe\\b (case-insensitive)'
  essay_target: {maybe}
- id: probably
  regex: '\\bprobably\\b (case-insensitive)'
  essay_target: 0.4
- id: be-able-to
  regex: '\\bbe able to\\b (case-insensitive)'
  essay_target: 0.1
- id: he-agent
  regex: '\\bhe\\b (case-insensitive; referent not machine-checkable)'
  essay_target: 1.5
- id: article-density
  regex: '\\b(the|a|an)\\b (case-insensitive)'
  essay_target: null
- id: sentence-length
  regex: 'split on [.!?] plus space'
  essay_target: 15.0
"""

DEFAULT_TARGETS = dict(colon_verdict=0.1, em_dash=0.1, antithesis=0.1,
                       kind_of=100.0, so_initial=100.0, i_think=100.0,
                       maybe=100.0)
# Defaults are chosen so nothing fires unless a test moves a target:
# restore-ops sit above tolerance at ~0 targets only when text has none,
# reduce-ops sit far below their huge targets.


def make_repo(tmp, doc_text, **targets):
    t = dict(DEFAULT_TARGETS)
    t.update(targets)
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd)
    with open(os.path.join(vd, "idiolect.yaml"), "w", encoding="utf-8") as f:
        f.write(BANK_TEMPLATE.format(**t))
    path = os.path.join(tmp, "draft.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc_text)
    return path


FILLER = ("The system holds steady under load and the operators know it. " * 4)


def test_refuses_without_voice_dir():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "draft.md")
        with open(path, "w") as f:
            f.write("A paragraph with enough words to be prose here.\n")
        try:
            iv.run(path, voice_dir=None)
            assert False, "should refuse without writing-voice/"
        except SystemExit as e:
            assert "writing-voice" in str(e)
    print("  refuses_without_voice_dir: ok")


def test_perhaps_becomes_maybe():
    text = FILLER + "Perhaps the run will finish, and perhaps it will not.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "Perhaps" not in out and "perhaps" not in out
        assert "Maybe the run" in out and "and maybe it" in out
    print("  perhaps_becomes_maybe: ok")


def test_spoken_markers_stripped_outside_quotes():
    text = (FILLER +
            'Okay, the run finished and you know the result held. '
            'He said "okay, you know the drill" in the meeting. '
            'That is all they mean, right?\n')
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert '"okay, you know the drill"' in out, "quoted speech must survive"
        assert "Okay, the run" not in out
        assert out.count("you know") == 1  # only the quoted one
        assert "right?" not in out
        assert "The run finished" in out  # recapitalized after strip
        assert "all they mean." in out
    print("  spoken_markers_stripped_outside_quotes: ok")


def test_so_initial_capped():
    text = (FILLER +
            "So the gate held. So the next run went out on schedule.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, so_initial=0.0)
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "So the" not in out
        assert "The gate held." in out and "The next run" in out
    print("  so_initial_capped: ok")


def test_ai_connectives_substituted():
    text = (FILLER +
            "However, the gate held. Moreover, the log agrees with it. "
            "Furthermore, the operators signed off on the change.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "However," not in out and "Moreover," not in out
        assert "Furthermore," not in out
        assert "But the gate held." in out
        assert out.count("And the") + out.count("And a") >= 1
    print("  ai_connectives_substituted: ok")


def test_colon_verdict_restore():
    text = (FILLER +
            "The gate rejected every paragraph. That is, nothing changed.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, colon_verdict=50.0)
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "every paragraph: nothing changed." in out
        assert "That is," not in out
    print("  colon_verdict_restore: ok")


def test_antithesis_restore():
    text = (FILLER +
            "We measure outcomes rather than intentions in every review.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, antithesis=50.0)
        doc, ed, _ = iv.run(path)
        assert "outcomes, not intentions" in doc.text()
    print("  antithesis_restore: ok")


def test_em_dash_restore_and_reduce():
    up = FILLER + "The gate (the mechanical half) held again this week.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, up, em_dash=50.0)
        doc, ed, _ = iv.run(path)
        assert "—the mechanical half—" in doc.text()
    down = FILLER + "The gate —the mechanical half— held again this week.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, down, em_dash=0.0)
        doc, ed, _ = iv.run(path)
        assert "—" not in doc.text()
        assert "(the mechanical half)" in doc.text()
    print("  em_dash_restore_and_reduce: ok")


def test_kind_of_trace_never_injected():
    text = (FILLER +
            "The run was kind of slow and the merge was kind of risky.\n")
    with tempfile.TemporaryDirectory() as tmp:
        # Target keeps roughly one per this word count: excess goes.
        path = make_repo(tmp, text, kind_of=15.0)
        doc, ed, _ = iv.run(path)
        assert doc.text().count("kind of") == 1
    clean = FILLER + "The run was slow and the merge was risky.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, clean, kind_of=15.0)
        doc, ed, _ = iv.run(path)
        assert "kind of" not in doc.text(), "never inject"
    print("  kind_of_trace_never_injected: ok")


def test_spoken_never_injected_when_absent():
    text = FILLER + "A plain paragraph that carries no spoken markers at all.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        out = doc.text().lower()
        for tok in ("okay", "you know", "right?"):
            assert tok not in out
        assert not ed.edits or all(
            e["operator"] not in ("okay", "you-know", "right-tag", "so-initial")
            for e in ed.edits)
    print("  spoken_never_injected_when_absent: ok")


def test_sentence_split():
    long_sent = ("The scheduler assigns every link a slot in the frame and "
                 "the controller confirms the assignment against the demand "
                 "matrix; the nodes then transmit in their slots without any "
                 "further coordination from the central controller at all.")
    assert len(long_sent.split()) > 30
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, FILLER + long_sent + "\n")
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "matrix. The nodes" in out
        assert ";" not in out.split("matrix.")[1].split("\n")[0]
    print("  sentence_split: ok")


def test_idempotent():
    text = (FILLER +
            "Perhaps the gate holds. However, the log disagrees with it. "
            "So the operators re-ran the suite to be sure of the result.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, so_initial=0.0)
        doc, ed, _ = iv.run(path)
        doc.save()
        doc2, ed2, _ = iv.run(path)
        assert not ed2.edits, (
            f"second run must be a no-op, got {[e['operator'] for e in ed2.edits]}")
    print("  idempotent: ok")


def test_locked_spans_untouched():
    text = (FILLER +
            "The verdict stands <!-- lock -->okay, this bit is mine, "
            "right?<!-- /lock --> and the rest is fair game, right?\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        doc.save()
        with open(path, encoding="utf-8") as f:
            out = f.read()
        assert ("<!-- lock -->okay, this bit is mine, right?<!-- /lock -->"
                in out), "locked bytes must survive verbatim"
        assert out.rstrip().endswith("fair game."), "unlocked tag must strip"
    print("  locked_spans_untouched: ok")


def test_edit_log_covers_diff():
    text = (FILLER +
            "Perhaps the gate holds. However, the log disagrees entirely. "
            "We measure outcomes rather than intentions in every review.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, antithesis=50.0)
        import prose_document
        originals = [p.text for p in prose_document.ProseDocument.open(path).paragraphs]
        doc, ed, _ = iv.run(path)
        assert ed.edits, "fixture should produce edits"
        replay = list(originals)
        for e in ed.edits:
            if not e["kept"]:
                continue
            assert replay[e["paragraph"]] == e["before"], \
                "log must replay: before-state mismatch"
            replay[e["paragraph"]] = e["after"]
        finals = [p.text for p in doc.paragraphs]
        assert replay == finals, "log must cover 100% of the diff"
    print("  edit_log_covers_diff: ok")


def test_verifier_judges_never_writes():
    text = (FILLER +
            "Perhaps the gate holds. However, the log disagrees entirely.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        reject_all = lambda op, before, after: False
        doc, ed, _ = iv.run(path, judge=reject_all)
        finals = [p.text for p in doc.paragraphs]
        import prose_document
        originals = [p.text for p in prose_document.ProseDocument.open(path).paragraphs]
        assert finals == originals, "all-dropped edits must leave text untouched"
        assert ed.edits and all(not e["kept"] for e in ed.edits)
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        keep_all = lambda op, before, after: True
        doc_k, ed_k, _ = iv.run(path, judge=keep_all)
        doc_m, ed_m, _ = iv.run(path, judge=None)
        assert doc_k.text() == doc_m.text(), \
            "keep-all verifier must equal the mechanical output"
    print("  verifier_judges_never_writes: ok")


def test_report_marks_retained_and_gate_read():
    text = FILLER + "He said the parser will probably be able to keep up.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, report = iv.run(path)
        assert "retained" in report["markers"]["probably"]["status"]
        assert "retained" in report["markers"]["be-able-to"]["status"]
        assert "gate-read" in report["markers"]["he-agent"]["status"]
        assert "probably be able to" in doc.text(), "RETAIN markers untouched"
    print("  report_marks_retained_and_gate_read: ok")


def test_i_think_restore_with_critic_flags():
    text = (FILLER +
            "The reviewer wants the section gone entirely. "
            "Claude wants it kept as an aside. "
            "The build passed 14 of 15 checks on the second try.\n")
    flags = [
        {"paragraph": 0, "quote": "The reviewer wants the section gone"},
        {"paragraph": 0, "quote": "Claude wants it kept"},
        {"paragraph": 0, "quote": "The build passed 14 of 15 checks"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path, critic_flags=flags)
        out = doc.text()
        assert "I think the reviewer wants the section gone entirely." in out
        assert "I think Claude" not in out and "I think claude" not in out, \
            "proper-noun first word must be skipped, not lowercased"
        assert "Claude wants it kept as an aside." in out
        assert "The build passed 14 of 15 checks" in out, \
            "receipted claim never hedged"
        assert "I think the build" not in out.lower() or \
            "I think the build" not in out
        restore = [e for e in ed.edits if e["operator"] == "i-think"]
        assert len(restore) == 1 and "critic" in restore[0]["note"]
        # Rerun on the output with the same flags: the flagged sentence now
        # carries the hedge, so the guard skips it — no further edits.
        doc.save()
        doc2, ed2, _ = iv.run(path, critic_flags=flags)
        assert not [e for e in ed2.edits if e["operator"] == "i-think"], \
            "restore must be idempotent under the same flags"
    print("  i_think_restore_with_critic_flags: ok")


def test_i_think_restore_never_past_target():
    text = (FILLER +
            "The reviewer wants the section gone entirely. "
            "The operators want the pipeline left alone tonight.\n")
    flags = [
        {"paragraph": 0, "quote": "The reviewer wants the section gone"},
        {"paragraph": 0, "quote": "The operators want the pipeline"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        # ~70 words at target 15/1000 -> budget rounds to 1: two valid
        # flags, one application.
        path = make_repo(tmp, text, i_think=15.0)
        doc, ed, _ = iv.run(path, critic_flags=flags)
        assert doc.text().count("I think") == 1, doc.text()
    print("  i_think_restore_never_past_target: ok")


def test_i_think_no_flags_unchanged():
    text = FILLER + "The reviewer wants the section gone entirely.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        doc, ed, _ = iv.run(path)
        assert "I think" not in doc.text(), \
            "no critic flags -> RESTORE never fires"
    print("  i_think_no_flags_unchanged: ok")


def main():
    test_refuses_without_voice_dir()
    test_perhaps_becomes_maybe()
    test_spoken_markers_stripped_outside_quotes()
    test_so_initial_capped()
    test_ai_connectives_substituted()
    test_colon_verdict_restore()
    test_antithesis_restore()
    test_em_dash_restore_and_reduce()
    test_kind_of_trace_never_injected()
    test_spoken_never_injected_when_absent()
    test_sentence_split()
    test_idempotent()
    test_locked_spans_untouched()
    test_edit_log_covers_diff()
    test_verifier_judges_never_writes()
    test_report_marks_retained_and_gate_read()
    test_i_think_restore_with_critic_flags()
    test_i_think_restore_never_past_target()
    test_i_think_no_flags_unchanged()
    print("test_inject_vernacular: all assertions passed")


if __name__ == "__main__":
    main()
