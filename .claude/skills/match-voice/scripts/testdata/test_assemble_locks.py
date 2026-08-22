#!/usr/bin/env python3
"""Offline tests for inline span locks on match-voice's markdown path (GH-82).

The fixture is the measured failure: the GH-77 harness run over
strategy-theatre returned two inline-locked spans modified — one with bold
inserted inside the lock, one with its em-dash spacing changed — while every
block lock in the same article survived byte-identical. Both lock forms were
handled by span_locks and prose_document, and the markdown driver used
neither: parse_paragraphs read the raw parse, so the model saw the locked
bytes, and assemble_draft spliced raw lines, so splice() never ran.

No network, no model. Run: python3 <skill>/scripts/testdata/test_assemble_locks.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402

SPAN_SNARK = ("<!-- lock --><!-- snark:L1-F2 -->That is the profession he is "
              "imitating, run as an experiment — 758 of them.<!-- /lock -->")
SPAN_DASH = ("<!-- lock -->The other half — the customer, the choice, the "
             "argument — was never in the machine.<!-- /lock -->")

ARTICLE = f"""# Strategy theatre

The first paragraph has enough words to be rewritten and carries nothing
locked at all, so it is the control for the rest of the file.

<!-- lock -->
A block lock on its own lines never becomes a paragraph.
<!-- /lock -->

Upstream of that deck sits a first-timer in consulting cosplay. {SPAN_SNARK} The
costume was supplied by a language model and the sentence after the lock
keeps going with enough words to matter.

Half of what the deck contains was produced by the machine. {SPAN_DASH} That
half is the part the client was paying for.
"""


def _write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _parse(tmp):
    art = _write(tmp, "article.md", ARTICLE)
    lines, _fm, paras, _cov, _un, doc = drive.parse_paragraphs(art, 0)
    return art, lines, paras, doc


def test_model_facing_text_carries_tokens_not_bytes():
    """The surface the rewrite model sees: anchor tokens, no lock bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        _art, _lines, paras, _doc = _parse(tmp)
        texts = [t for _s, _e, t in paras]
        assert len(texts) == 3, texts
        joined = "\n".join(texts)
        assert "<!-- lock -->" not in joined, "lock bytes reached the model surface"
        assert "snark:L1-F2" not in joined
        assert "The other half" not in joined
        assert "[[LOCK-1]]" in texts[1] and "[[LOCK-2]]" in texts[2], texts
        assert "A block lock" not in joined
    print("  model_facing_text_carries_tokens_not_bytes: ok")


def test_accepted_rewrite_splices_locked_bytes_back():
    """A candidate that kept its token lands with the locked span verbatim."""
    with tempfile.TemporaryDirectory() as tmp:
        art, lines, paras, doc = _parse(tmp)
        out = os.path.join(tmp, "article.vr-draft.md")
        accept = {
            2: "A first-timer in consulting cosplay sits upstream. [[LOCK-1]] "
               "A language model supplied the costume.",
            3: "The machine produced half the deck. [[LOCK-2]] The client paid "
               "for the other half.",
        }
        rng = {n: (s, e) for n, (s, e, _) in enumerate(paras, 1)}
        refused = drive.assemble_draft(art, lines, accept, rng, out)
        assert refused == [], refused
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert SPAN_SNARK in content, "snark-adjacent span not byte-identical"
        assert SPAN_DASH in content, "em-dash span not byte-identical"
        assert "[[LOCK-" not in content, "a token leaked into the draft"
        assert "sits upstream" in content and "paid" in content
        assert "A block lock on its own lines" in content
        sl = drive._span_locks()
        assert sl.verify_preserved(doc.locked_spans(), content) == []
    print("  accepted_rewrite_splices_locked_bytes_back: ok")


def test_candidate_without_token_is_refused_and_original_kept():
    with tempfile.TemporaryDirectory() as tmp:
        art, lines, paras, _doc = _parse(tmp)
        out = os.path.join(tmp, "article.vr-draft.md")
        accept = {2: "A rewrite that ate the anchor and its locked sentence.",
                  3: "The machine produced half the deck. [[LOCK-2]] The rest."}
        rng = {n: (s, e) for n, (s, e, _) in enumerate(paras, 1)}
        refused = drive.assemble_draft(art, lines, accept, rng, out)
        assert refused == [2], refused
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert SPAN_SNARK in content and SPAN_DASH in content
        assert "consulting cosplay" in content, "refused paragraph lost its original"
        assert "ate the anchor" not in content
        assert "The rest." in content, "the good candidate was not written"
    print("  candidate_without_token_is_refused_and_original_kept: ok")


def test_check_tokens_catches_the_loop_faults():
    """What the loop checks before the gate: dropped, duplicated, invented."""
    sl = drive._span_locks()
    orig = "Lead [[LOCK-3]] tail."
    assert sl.check_tokens(orig, "Lead [[LOCK-3]] tail rewritten.") is None
    assert "LOCK-3" in sl.check_tokens(orig, "Lead tail rewritten.")
    assert "2 times" in sl.check_tokens(orig, "[[LOCK-3]] and [[LOCK-3]].")
    assert "unknown" in sl.check_tokens(orig, "[[LOCK-3]] and [[LOCK-9]].")
    assert sl.check_tokens("no tokens here", "none here either") is None
    print("  check_tokens_catches_the_loop_faults: ok")


def test_verify_preserved_flags_the_harness_edits():
    """The post-assembly assertion sees exactly the two measured drifts."""
    with tempfile.TemporaryDirectory() as tmp:
        _art, _lines, _paras, doc = _parse(tmp)
        sl = drive._span_locks()
        spans = doc.locked_spans()
        assert len(spans) == 3, spans
        assert sl.verify_preserved(spans, ARTICLE) == []
        bolded = ARTICLE.replace("run as an experiment", "run as **an experiment**")
        unspaced = ARTICLE.replace("half — the customer", "half—the customer")
        assert sl.verify_preserved(spans, bolded) == [SPAN_SNARK]
        assert sl.verify_preserved(spans, unspaced) == [SPAN_DASH]
    print("  verify_preserved_flags_the_harness_edits: ok")


def test_lock_note_rides_only_on_token_paragraphs():
    assert "[[LOCK-1]]" in drive.LOCK_NOTE
    assert drive.compose_note("style", drive.LOCK_NOTE).startswith("style ")
    assert drive.compose_note("", "") == ""
    print("  lock_note_rides_only_on_token_paragraphs: ok")


def main():
    test_model_facing_text_carries_tokens_not_bytes()
    test_accepted_rewrite_splices_locked_bytes_back()
    test_candidate_without_token_is_refused_and_original_kept()
    test_check_tokens_catches_the_loop_faults()
    test_verify_preserved_flags_the_harness_edits()
    test_lock_note_rides_only_on_token_paragraphs()
    print("test_assemble_locks: all assertions passed")


if __name__ == "__main__":
    main()
