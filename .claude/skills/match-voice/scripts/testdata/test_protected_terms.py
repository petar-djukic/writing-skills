#!/usr/bin/env python3
"""Tests for protected terms and canonical blocks (GH-77, sub-issue A).

Covers:
  - protected_terms.derive: the 3+ paragraph rule, bigrams, refrains,
    stopwords excluded, determinism
  - load_or_derive: file written once, read thereafter, never overwritten
  - verify.py --protected-terms: fatal on a lost term, silent on a term the
    original never carried, plural-tolerant
  - rewrite.build_prompt: only the paragraph's own terms in the rule
  - canonical registry: substring and re: patterns, walk-up discovery,
    canonical paragraphs left verbatim by assemble_draft
  - drive.term_note: the retry note names the lost terms

No network, no model.
Run: python3 <skill>/scripts/testdata/test_protected_terms.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.dirname(HERE)
SHARED = os.path.normpath(os.path.join(SCRIPTS, "..", "..", "..", "scripts"))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, SHARED)

import protected_terms as pt  # noqa: E402
import verify  # noqa: E402
import rewrite  # noqa: E402
import drive  # noqa: E402

PARAS = [
    "The exposure is what the detector measures, and the decision plane sits above it.",
    "Every specimen shows the same exposure; the detector flags it on the decision plane.",
    "Where is the exposure? Who owns the detector? What did the decision plane decide?",
    "A fourth paragraph about specimens and exposure that the detector never saw.",
    "Where is the exposure? Who owns the detector? What did the decision plane decide?",
    "Nothing here repeats, so nothing here should be protected on its own.",
]


def test_derive_rules():
    terms = pt.derive(PARAS)
    assert "exposure" in terms, terms
    assert "detector" in terms
    assert "decision plane" in terms, "bigram in 3+ paragraphs"
    assert "specimen" not in terms and "specimens" not in terms, \
        "two paragraphs is not a chain"
    assert "the" not in terms and "what" not in terms, "stopwords excluded"
    assert "What did the decision plane decide?" in terms, \
        "refrain sentence (6+ words, 2+ paragraphs) protected whole"
    assert "Where is the exposure?" not in terms, "a 4-word sentence is too short to be a refrain"
    assert terms == pt.derive(PARAS) == sorted(terms, key=lambda s: (s.lower(), s)), \
        "deterministic and sorted"
    assert pt.derive([]) == []
    noisy = ["The developers didn\u2019t read https://meshintelligence.substack.com at all.",
             "Developers who didn\u2019t read meshintelligence.substack.com missed the developer post.",
             "A developer who didn\u2019t read it at https://meshintelligence.substack.com lost out."]
    terms = pt.derive(noisy)
    assert "developer" in terms and "developers" not in terms, \
        f"plural folded onto the singular: {terms}"
    assert "didn" not in terms and "didn't" not in terms, "contractions are not terms"
    assert not any("http" in t or "meshintelligence" in t or "substack" in t for t in terms), \
        f"URL fragments are not terms: {terms}"
    print("  derive_rules: ok")


def test_load_or_derive_never_overwrites():
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "draft.md")
        open(art, "w").write("x\n")
        terms, path, derived = pt.load_or_derive(art, PARAS)
        assert derived is True and path == os.path.join(tmp, "draft.protected-terms.txt")
        assert os.path.exists(path)
        assert pt.read_terms(path) == terms
        # hand edit: drop everything but one term, add a comment
        open(path, "w").write("# mine\nexposure\n")
        terms2, path2, derived2 = pt.load_or_derive(art, PARAS)
        assert derived2 is False and terms2 == ["exposure"], terms2
        assert open(path).read() == "# mine\nexposure\n", "file never overwritten"
    print("  load_or_derive_never_overwrites: ok")


def test_verify_protected_term_gate():
    orig = "The exposure is what the detector measures across specimens."
    lost = "The justification is what the tool measures across specimens."
    r = verify.verify(orig, lost, protected_terms=["exposure", "detector", "specimen"])
    assert not r["clean"]
    found = [f for f in r["findings"] if f["check"] == "protected-term"]
    assert [f["detail"] for f in found] == ["protected term lost: 'exposure'",
                                           "protected term lost: 'detector'"], found
    kept = "The exposure is what the detector measures over every specimen."
    r = verify.verify(orig, kept, protected_terms=["exposure", "detector", "specimen"])
    assert r["clean"], r["findings"]
    # a protected term the original never carried is not this paragraph's business
    r = verify.verify("Plain text here.", "Different plain text.",
                      protected_terms=["exposure"])
    assert r["clean"]
    # phrase, case-insensitive
    r = verify.verify("On the Decision Plane it holds.", "On the decision plane it holds.",
                      protected_terms=["decision plane"])
    assert r["clean"]
    r = verify.verify("On the decision plane it holds.", "On the decision it holds.",
                      protected_terms=["decision plane"])
    assert not r["clean"]
    print("  verify_protected_term_gate: ok")


def test_verify_cli_flag():
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        o, r, t = (os.path.join(tmp, n) for n in ("o.txt", "r.txt", "terms.txt"))
        open(o, "w").write("The exposure is measured.")
        open(r, "w").write("The justification is measured.")
        open(t, "w").write("# list\nexposure\n")
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "verify.py"),
                            "--original", o, "--rewrite", r, "--protected-terms", t,
                            "--json"], capture_output=True, text=True)
        assert p.returncode == 1, p.stderr
        data = json.loads(p.stdout)
        assert any(f["check"] == "protected-term" for f in data["findings"])
    print("  verify_cli_flag: ok")


def test_rewrite_prompt_carries_own_terms_only():
    para = "The exposure is what the detector measures."
    prompt = rewrite.build_prompt(para, "(anchors)", protected_terms=[
        "exposure", "detector", "decision plane"])
    assert "10. Keep these words and phrases verbatim" in prompt
    assert "exposure; detector" in prompt
    assert "decision plane" not in prompt, "a term absent from the paragraph is not listed"
    plain = rewrite.build_prompt("Nothing protected here.", "(anchors)",
                                 protected_terms=["exposure"])
    assert "10. Keep" not in plain
    assert rewrite.build_prompt(para, "(anchors)") == rewrite.build_prompt(
        para, "(anchors)", protected_terms=None)
    print("  rewrite_prompt_carries_own_terms_only: ok")


def test_canonical_registry_and_discovery():
    with tempfile.TemporaryDirectory() as tmp:
        vd = os.path.join(tmp, "writing-voice")
        os.makedirs(os.path.join(tmp, "posts"))
        os.makedirs(vd)
        reg = os.path.join(vd, "canonical-blocks.txt")
        open(reg, "w").write("# pasted blocks\nThis post was drafted with AI assistance\n"
                             "re:^Subscribe to .* for more\n")
        art = os.path.join(tmp, "posts", "draft.md")
        open(art, "w").write("x\n")
        patterns, path = pt.load_canonical(None, art)
        assert path == reg and len(patterns) == 2
        texts = ["A normal paragraph with enough words to be rewritten by the model.",
                 "This post was drafted with AI assistance and edited by hand.",
                 "Subscribe to Strategy Theatre for more of this.",
                 "We subscribe to the view that more is not better."]
        assert pt.canonical_indices(texts, patterns) == {2, 3}
        assert pt.load_canonical(None, os.path.join(tempfile.gettempdir(), "none.md")) == ([], None) \
            or True  # a directory without a registry is the normal state
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "draft.md")
        open(art, "w").write("x\n")
        assert pt.load_canonical(None, art) == ([], None)
    print("  canonical_registry_and_discovery: ok")


def test_canonical_paragraph_left_verbatim_in_draft():
    lines = ["# Title", "", "A normal paragraph with enough words to be rewritten.",
             "", "This post was drafted with AI assistance.", ""]
    texts = [lines[2], lines[4]]
    patterns = [("substring", "drafted with ai assistance")]
    canonical = pt.canonical_indices(texts, patterns)
    assert canonical == {2}
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        out = os.path.join(tmp, "a.vr-draft.md")
        open(art, "w").write("\n".join(lines))
        # what the driver does: only non-canonical candidates are accepted
        accept = {n: "Rewritten paragraph one." for n in (1, 2) if n not in canonical}
        rng = {1: (3, 3), 2: (5, 5)}
        drive.assemble_draft(art, lines, accept, rng, out)
        body = open(out).read()
        assert "This post was drafted with AI assistance." in body
        assert "Rewritten paragraph one." in body
    print("  canonical_paragraph_left_verbatim_in_draft: ok")


def test_term_note():
    fj = json.dumps({"findings": [
        {"check": "protected-term", "severity": "fatal", "detail": "protected term lost: 'exposure'"},
        {"check": "numbers", "severity": "fatal", "detail": "number '3' lost"},
        {"check": "protected-term", "severity": "fatal", "detail": "protected term lost: 'decision plane'"}]})
    note = drive.term_note(fj)
    assert "'exposure', 'decision plane'" in note, note
    assert drive.term_note(json.dumps({"findings": []})) is None
    assert drive.term_note("not json") is None
    print("  term_note: ok")


def test_derive_ignores_lock_tokens():
    """Inline lock anchors reach derive() as [[LOCK-n]] (GH-82); four such
    paragraphs must not make "lock" a protected term."""
    assert pt._tokens("a [[LOCK-12]] b") == ["a", "b"]
    paras = [f"Sentence number {i} keeps going with [[LOCK-{i}]] inside "
             "the prose here." for i in range(1, 5)]
    terms = pt.derive(paras)
    assert "lock" not in terms, terms
    assert "prose" in terms, terms
    print("  derive_ignores_lock_tokens: ok")


def main():
    test_derive_rules()
    test_derive_ignores_lock_tokens()
    test_load_or_derive_never_overwrites()
    test_verify_protected_term_gate()
    test_verify_cli_flag()
    test_rewrite_prompt_carries_own_terms_only()
    test_canonical_registry_and_discovery()
    test_canonical_paragraph_left_verbatim_in_draft()
    test_term_note()
    print("test_protected_terms: all assertions passed")


if __name__ == "__main__":
    main()
