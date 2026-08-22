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
{substrate}"""

# substrate block mirrors the real bank's shape: particle rows carry the
# journal rate the target derives from, and nekako is covered by a marker.
SUBSTRATE_TEMPLATE = """\
substrate:
  policy: 'Both tiers applied directly at target rates; the gate is the filter.'
  particles:
    table:
    - {{serbian: 'nekako / onako', english: 'kind of', talk: 9.7, journal: 2.4, marker: kind-of}}
    - {{serbian: 'zapravo / upravo', english: 'actually / actual (emphatic)', talk: 5.8, journal: 1.7, marker: null}}
    - {{serbian: 'recimo', english: "let's say (example-introducer)", talk: 0.3, journal: 0.0, marker: null}}
  calques:
    attested:
    - {{serbian: zapravo, english: 'actually (emphatic)'{zapravo_extra}}}
    - {{serbian: nekako, english: 'kind of'}}
    - {{serbian: recimo, english: "let's say"{recimo_extra}}}
    - {{serbian: ne ide, english: 'does not go = does not work'{ne_ide_extra}}}
    - {{serbian: 'sve u svemu', english: 'all in all'}}
    proposed:
    - {{serbian: konkretno, english: 'concretely for specifically'{konkretno_extra}}}
    - {{serbian: 'drzati predavanje', english: 'hold a lecture/presentation'{drzati_extra}}}
    - {{serbian: 'doneti odluku', english: 'bring a decision'{doneti_extra}}}
    - {{serbian: 'do petka', english: 'till Friday (deadline till)'{petka_extra}}}
    - {{serbian: kontrolisati, english: 'control = check/verify'}}
"""

DEFAULT_TARGETS = dict(colon_verdict=0.1, em_dash=0.1, antithesis=0.1,
                       kind_of=100.0, so_initial=100.0, i_think=100.0,
                       maybe=100.0)
CALQUE_KEYS = ("zapravo", "recimo", "ne_ide", "konkretno", "drzati",
               "doneti", "petka")
# Defaults are chosen so nothing fires unless a test moves a target:
# restore-ops sit above tolerance at ~0 targets only when text has none,
# reduce-ops sit far below their huge targets.


def make_repo(tmp, doc_text, substrate=True, calque_targets=None, **targets):
    """calque_targets: {key: essay_target} written onto the catalog
    entries (keys from CALQUE_KEYS); absent keys derive their target from
    the particle table or the trace default, as in a real bank.
    substrate=False writes a bank with no substrate block."""
    t = dict(DEFAULT_TARGETS)
    t.update(targets)
    extras = {f"{k}_extra": "" for k in CALQUE_KEYS}
    for k, v in (calque_targets or {}).items():
        extras[f"{k}_extra"] = f", essay_target: {v}"
    t["substrate"] = SUBSTRATE_TEMPLATE.format(**extras) if substrate else ""
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


# --- calques (GH-67) -----------------------------------------------------------
# ~70 filler words; at target 50/1000 the budget rounds to 4, at 15 to 1.

def _calque_edits(ed, key):
    return [e for e in ed.edits if e["operator"] == f"calque:{key}" and e["kept"]]


def test_calque_zapravo_sites():
    text = (FILLER +
            "The log said the gate was open. But the gate is closed. "
            "Run it again and you get the agent back.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"zapravo": 50.0})
        doc, ed, report = iv.run(path)
        out = doc.text()
        assert "But the gate is actually closed." in out, out
        assert "you actually get the agent" in out, out
        edits = _calque_edits(ed, "zapravo")
        assert len(edits) == 2
        assert all("attested calque zapravo" in e["note"] for e in edits)
        c = report["calques"]["zapravo"]
        assert c["tier"] == "attested" and c["status"] == "applied"
        assert c["target_source"] == "essay_target"
        assert c["rate_after"] > c["rate_before"]
    print("  calque_zapravo_sites: ok")


def test_calque_recimo_sites():
    text = (FILLER +
            "Suppose you have a task to run. For example, we run it twice. "
            "Imagine the queue fills up. Say the word and it stops.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"recimo": 50.0})
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "Let's say you have a task to run." in out, out
        assert "Let's say we run it twice." in out, out
        assert "Let's say the queue fills up." in out, out
        assert "Say the word" in out, "no example-introducer follows: untouched"
    print("  calque_recimo_sites: ok")


def test_calque_ne_ide_site():
    text = (FILLER +
            "That argument doesn't work. The plan does not work either. "
            "The merge doesn't work out, and the fix won't work on Windows.\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"ne_ide": 50.0})
        doc, ed, _ = iv.run(path)
        out = doc.text()
        assert "That argument doesn't go." in out, out
        assert "The plan does not go either." in out, out
        assert "doesn't work out" in out, "phrasal verb keeps its verb"
        assert "won't work on Windows" in out, "phrasal verb keeps its verb"
    print("  calque_ne_ide_site: ok")


def test_calque_rate_capped():
    text = (FILLER +
            "But the gate is closed. But the log is stale. "
            "Run it and you get the agent back.\n")
    with tempfile.TemporaryDirectory() as tmp:
        # target 15 over ~85 words -> budget rounds to 1 of three sites.
        path = make_repo(tmp, text, calque_targets={"zapravo": 15.0})
        doc, ed, _ = iv.run(path)
        assert doc.text().count("actually") == 1, doc.text()
        assert len(_calque_edits(ed, "zapravo")) == 1
    with tempfile.TemporaryDirectory() as tmp:
        # already at target: one "actually" present, nothing more fires.
        path = make_repo(tmp, text.replace("is stale", "is actually stale"),
                         calque_targets={"zapravo": 15.0})
        doc, ed, report = iv.run(path)
        assert not _calque_edits(ed, "zapravo")
        assert report["calques"]["zapravo"]["status"] == "within tolerance"
    with tempfile.TemporaryDirectory() as tmp:
        # short draft, real-bank-sized target: the budget rounds to zero
        # and the report says so rather than claiming the target is met.
        path = make_repo(tmp, text, calque_targets={"zapravo": 0.85})
        _, ed, report = iv.run(path)
        assert not _calque_edits(ed, "zapravo")
        assert report["calques"]["zapravo"]["status"] == \
            "below target, budget rounds to zero"
    print("  calque_rate_capped: ok")


def test_calque_target_resolution():
    text = FILLER + "A plain paragraph with no calque sites in it at all.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text)
        _, _, report = iv.run(path, calque_tiers=iv.CALQUE_TIERS)
        c = report["calques"]
        assert c["zapravo"]["target"] == 0.85, "journal 1.7 damped to midpoint"
        assert c["zapravo"]["target_source"] == "particle journal rate / 2"
        assert c["recimo"]["target"] == iv.CALQUE_TRACE_TARGET, \
            "journal 0.0 floors at trace, not silence"
        assert c["ne ide"]["target"] == iv.CALQUE_TRACE_TARGET
        assert c["ne ide"]["target_source"] == "trace default"
        assert c["konkretno"]["tier"] == "proposed"
        assert c["konkretno"]["target"] == iv.CALQUE_TRACE_TARGET
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"zapravo": 0})
        _, _, report = iv.run(path)
        assert report["calques"]["zapravo"]["target"] == 0.0, \
            "an explicit zero is the curator's call and wins over the floor"
    print("  calque_target_resolution: ok")


def test_calque_catalog_reported_not_guessed():
    text = FILLER + "The run was kind of slow, all in all, and we checked it.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"zapravo": 50.0})
        doc, ed, report = iv.run(path)
        c = report["calques"]
        assert c["nekako"]["status"] == "covered by marker kind-of"
        assert c["sve u svemu"]["status"].startswith("no site operator")
        assert c["kontrolisati"]["status"].startswith("no site operator")
        assert doc.text().count("kind of") == 1, "never injected via calques"
        assert not any(e["operator"].startswith("calque:") for e in ed.edits)
    print("  calque_catalog_reported_not_guessed: ok")


def test_calque_proposed_behind_flag():
    text = (FILLER +
            "Specifically, the team will make a decision by Friday. "
            "She gave a talk on it and gives a presentation each spring.\n")
    targets = {"konkretno": 50.0, "drzati": 50.0, "doneti": 50.0, "petka": 50.0}
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets=targets)
        doc, ed, report = iv.run(path)
        assert doc.text().split("\n")[-2].endswith(
            "each spring."), doc.text()
        assert "Specifically, the team will make a decision by Friday" in doc.text()
        assert report["calques"]["konkretno"]["status"] == \
            "tier not enabled (--calques proposed)"
        assert not any(e["operator"].startswith("calque:") for e in ed.edits)
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets=targets)
        doc, ed, report = iv.run(path, calque_tiers=iv.CALQUE_TIERS)
        out = doc.text()
        assert "Concretely, the team will bring a decision till Friday." in out, out
        assert "She held a talk on it and holds a presentation" in out, out
        for key in ("konkretno", "doneti odluku", "do petka", "drzati predavanje"):
            assert report["calques"][key]["status"] == "applied", key
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets=targets)
        _, ed, report = iv.run(path, calque_tiers=())
        assert not any(e["operator"].startswith("calque:") for e in ed.edits)
        assert report["calques"]["zapravo"]["status"].startswith("tier not enabled")
    print("  calque_proposed_behind_flag: ok")


def test_calque_quotes_and_locks_guarded():
    text = (FILLER +
            'He wrote "Suppose you have a task" on the board. '
            "Suppose you have a second one. "
            "<!-- lock -->Suppose you have a task.<!-- /lock -->\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"recimo": 50.0})
        doc, ed, _ = iv.run(path)
        doc.save()
        with open(path, encoding="utf-8") as f:
            out = f.read()
        assert '"Suppose you have a task"' in out, "quoted speech survives"
        assert "<!-- lock -->Suppose you have a task.<!-- /lock -->" in out, \
            "locked bytes survive verbatim"
        assert "Let's say you have a second one." in out, out
        assert len(_calque_edits(ed, "recimo")) == 1
    print("  calque_quotes_and_locks_guarded: ok")


def test_calque_idempotent_and_logged():
    text = (FILLER +
            "But the gate is closed. Suppose you have a task to run. "
            "That argument doesn't work. Specifically, we make a decision by Friday.\n")
    targets = {"zapravo": 50.0, "recimo": 50.0, "ne_ide": 50.0,
               "konkretno": 50.0, "doneti": 50.0, "petka": 50.0}
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets=targets)
        import prose_document
        originals = [p.text for p in prose_document.ProseDocument.open(path).paragraphs]
        doc, ed, _ = iv.run(path, calque_tiers=iv.CALQUE_TIERS)
        calque_edits = [e for e in ed.edits if e["operator"].startswith("calque:")]
        assert len(calque_edits) >= 5, [e["operator"] for e in calque_edits]
        replay = list(originals)
        for e in ed.edits:
            if e["kept"]:
                assert replay[e["paragraph"]] == e["before"]
                replay[e["paragraph"]] = e["after"]
        assert replay == [p.text for p in doc.paragraphs], "log replays the diff"
        doc.save()
        doc2, ed2, _ = iv.run(path, calque_tiers=iv.CALQUE_TIERS)
        assert not ed2.edits, \
            f"second run must be a no-op, got {[e['operator'] for e in ed2.edits]}"
    print("  calque_idempotent_and_logged: ok")


def test_calque_verifier_can_drop():
    text = FILLER + "But the gate is closed. Suppose you have a task.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, calque_targets={"zapravo": 50.0, "recimo": 50.0})
        drop_calques = lambda op, before, after: not op.startswith("calque:")
        doc, ed, _ = iv.run(path, judge=drop_calques)
        assert "But the gate is closed. Suppose you have a task." in doc.text()
        dropped = [e for e in ed.edits if e["operator"].startswith("calque:")]
        assert dropped and all(not e["kept"] for e in dropped)
    print("  calque_verifier_can_drop: ok")


def test_no_substrate_unchanged():
    text = FILLER + "But the gate is closed. Suppose you have a task.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = make_repo(tmp, text, substrate=False)
        doc, ed, report = iv.run(path, calque_tiers=iv.CALQUE_TIERS)
        assert report["calques"] == {}
        assert "But the gate is closed. Suppose you have a task." in doc.text()
    print("  no_substrate_unchanged: ok")


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
    test_calque_zapravo_sites()
    test_calque_recimo_sites()
    test_calque_ne_ide_site()
    test_calque_rate_capped()
    test_calque_target_resolution()
    test_calque_catalog_reported_not_guessed()
    test_calque_proposed_behind_flag()
    test_calque_quotes_and_locks_guarded()
    test_calque_idempotent_and_logged()
    test_calque_verifier_can_drop()
    test_no_substrate_unchanged()
    print("test_inject_vernacular: all assertions passed")


if __name__ == "__main__":
    main()
