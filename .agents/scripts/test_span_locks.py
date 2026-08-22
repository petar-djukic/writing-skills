#!/usr/bin/env python3
"""Offline tests for span_locks.py and its integration into the shared
drivers (md_paragraphs.py, prose_document.py). GH-57 sub-issue #58.

The invariant under test: bytes inside a lock survive extraction,
replacement, and save byte-identical, and broken markers fail loudly.
Run: python3 <surface>/scripts/test_span_locks.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import md_paragraphs  # noqa: E402
import prose_document as pd  # noqa: E402
import span_locks as sl  # noqa: E402


MD_SAMPLE = """# Title

First paragraph with enough words to count as prose for the extractor.

<!-- lock -->
This whole block is hand-written and locked.

```python
code_inside_lock()
```
<!-- /lock -->

Second paragraph carries an inline span: <!-- lock -->the authored snark
stays exactly as written<!-- /lock --> and the tail keeps going with words.

```text
<!-- lock --> markers inside a code fence are example text, not a lock
```

Third paragraph is plain prose with no locks anywhere in it at all.
"""


# ---------------------------------------------------------------------------
# span_locks primitives
# ---------------------------------------------------------------------------

def test_excise_splice_round_trip():
    text = ("Lead-in. <!-- lock -->first span<!-- /lock --> middle "
            "<!-- lock -->second\nspan<!-- /lock --> tail.")
    clean, manifest = sl.excise(text)
    assert len(manifest) == 2
    assert "first span" not in clean
    assert "second" not in clean
    assert "[[LOCK-1]]" in clean and "[[LOCK-2]]" in clean
    assert sl.splice(clean, manifest) == text
    print("  excise_splice_round_trip: ok")


def test_excise_no_locks_is_identity():
    text = "Plain paragraph, no markers at all."
    clean, manifest = sl.excise(text)
    assert clean == text and manifest == {}
    print("  excise_no_locks_is_identity: ok")


def test_excise_escaped_bang_spelling():
    text = "Prose <\\!-- lock -->kept<\\!-- /lock --> tail."
    clean, manifest = sl.excise(text)
    assert len(manifest) == 1
    assert sl.splice(clean, manifest) == text
    print("  excise_escaped_bang_spelling: ok")


def test_excise_rejects_nested():
    try:
        sl.excise("a <!-- lock -->b <!-- lock -->c<!-- /lock --> d<!-- /lock -->",
                  base_line=10)
        assert False, "nested lock should raise"
    except sl.LockError as e:
        assert "nested" in str(e) and "line 10" in str(e)
    print("  excise_rejects_nested: ok")


def test_excise_rejects_close_without_open():
    try:
        sl.excise("a<!-- /lock --> b")
        assert False, "close without open should raise"
    except sl.LockError as e:
        assert "without open" in str(e)
    print("  excise_rejects_close_without_open: ok")


def test_excise_rejects_unclosed():
    try:
        sl.excise("line one\nline two <!-- lock -->never closed", base_line=5)
        assert False, "unclosed lock should raise"
    except sl.LockError as e:
        assert "unclosed" in str(e) and "line 6" in str(e)
    print("  excise_rejects_unclosed: ok")


def test_splice_rejects_dropped_duplicated_unknown():
    clean, manifest = sl.excise("x <!-- lock -->y<!-- /lock --> z")
    for bad, why in [("x  z", "dropped"),
                     ("x [[LOCK-1]] mid [[LOCK-1]] z", "duplicated"),
                     ("x [[LOCK-1]] [[LOCK-9]] z", "unknown")]:
        try:
            sl.splice(bad, manifest)
            assert False, f"{why} token should raise"
        except sl.LockError:
            pass
    print("  splice_rejects_dropped_duplicated_unknown: ok")


# ---------------------------------------------------------------------------
# md_paragraphs block locks
# ---------------------------------------------------------------------------

def test_md_block_lock_classified():
    r = md_paragraphs.parse(MD_SAMPLE)
    locked = [ln for ln, cat in r.coverage.items() if cat == "locked"]
    assert locked, "no lines classified locked"
    joined = " ".join(p[2] for p in r.paragraphs)
    assert "hand-written and locked" not in joined
    assert "code_inside_lock" not in joined
    assert r.unaccounted == []
    print("  md_block_lock_classified: ok")


def test_md_lock_opaque_to_fences_and_fences_shield_markers():
    r = md_paragraphs.parse(MD_SAMPLE)
    # The fence lines inside the lock are locked, not code.
    lines = MD_SAMPLE.split("\n")
    fence_in_lock = next(i + 1 for i, l in enumerate(lines)
                         if l.strip() == "```python")
    assert r.coverage[fence_in_lock] == "locked"
    # The marker inside the ```text fence is code, and parsing succeeded
    # (an interpreted marker there would have raised unclosed-lock).
    marker_in_fence = next(i + 1 for i, l in enumerate(lines)
                           if "example text" in l)
    assert r.coverage[marker_in_fence] == "code"
    print("  md_lock_opaque_to_fences_and_fences_shield_markers: ok")


def test_md_block_malformed_raise():
    for text, want in [
            ("a\n<!-- lock -->\n<!-- lock -->\n<!-- /lock -->\n", "nested"),
            ("a\n<!-- /lock -->\n", "without open"),
            ("a\n<!-- lock -->\nnever closed\n", "unclosed")]:
        try:
            md_paragraphs.parse(text)
            assert False, f"{want} should raise"
        except sl.LockError as e:
            assert want in str(e), f"{want}: {e}"
            assert "line" in str(e)
    print("  md_block_malformed_raise: ok")


# ---------------------------------------------------------------------------
# prose_document markdown backend
# ---------------------------------------------------------------------------

def _write(tmp, name, content):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_md_locked_text_never_in_paragraphs():
    with tempfile.TemporaryDirectory() as tmp:
        doc = pd.ProseDocument.open(_write(tmp, "s.md", MD_SAMPLE))
        for p in doc.paragraphs:
            assert "authored snark" not in p.text
            assert "hand-written and locked" not in p.text
        inline_para = next(p for p in doc.paragraphs if "[[LOCK-1]]" in p.text)
        assert "inline span" in inline_para.text
    print("  md_locked_text_never_in_paragraphs: ok")


def test_md_byte_identical_round_trip_replacing_everything():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "s.md", MD_SAMPLE)
        doc = pd.ProseDocument.open(path)
        for i in range(len(doc.paragraphs)):
            doc.replace(i, doc.paragraphs[i].text)
        doc.save()
        with open(path, encoding="utf-8") as f:
            assert f.read() == MD_SAMPLE, "round-trip changed bytes"
    print("  md_byte_identical_round_trip_replacing_everything: ok")


def test_md_replace_keeps_locked_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "s.md", MD_SAMPLE)
        doc = pd.ProseDocument.open(path)
        idx = next(p.index for p in doc.paragraphs if "[[LOCK-1]]" in p.text)
        doc.replace(idx, "A rewritten paragraph where [[LOCK-1]] sits elsewhere now.")
        doc.save()
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert ("<!-- lock -->the authored snark\nstays exactly as written"
                "<!-- /lock -->") in content
        assert "[[LOCK-1]]" not in content
        assert "rewritten paragraph where" in content
    print("  md_replace_keeps_locked_bytes: ok")


def test_md_replace_dropping_token_refused():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "s.md", MD_SAMPLE)
        doc = pd.ProseDocument.open(path)
        idx = next(p.index for p in doc.paragraphs if "[[LOCK-1]]" in p.text)
        before = doc.text()
        try:
            doc.replace(idx, "A rewrite that ate the anchor token entirely.")
            assert False, "dropping the token should raise"
        except sl.LockError:
            pass
        assert doc.text() == before, "refused replace must not modify the doc"
    print("  md_replace_dropping_token_refused: ok")


def test_md_lock_report():
    with tempfile.TemporaryDirectory() as tmp:
        doc = pd.ProseDocument.open(_write(tmp, "s.md", MD_SAMPLE))
        rep = doc.lock_report()
        assert len(rep["block_ranges"]) == 1
        s, e = rep["block_ranges"][0]
        assert s < e
        assert len(rep["inline"]) == 1 and rep["inline"][0]["tokens"] == 1
    print("  md_lock_report: ok")


# ---------------------------------------------------------------------------
# prose_document YAML backend
# ---------------------------------------------------------------------------

YAML_SAMPLE = """id: sample
overview: |
  This paragraph has enough words to be prose and it carries a locked
  span right here: <!-- lock -->the exact authored words<!-- /lock --> before
  the tail finishes the thought with a few more words.
notes: a short value
"""


def test_yaml_inline_lock_excised_and_spliced():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "s.yaml", YAML_SAMPLE)
        doc = pd.ProseDocument.open(path)
        para = next(p for p in doc.paragraphs if "overview" in p.context)
        assert "exact authored words" not in para.text
        assert "[[LOCK-1]]" in para.text
        doc.replace(para.index,
                    "New overview text where [[LOCK-1]] still anchors the span.\n")
        doc.save()
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "<!-- lock -->the exact authored words<!-- /lock -->" in content
        assert "[[LOCK-1]]" not in content
        rep = doc.lock_report()
        assert rep["inline"] and rep["inline"][0]["tokens"] == 1
    print("  yaml_inline_lock_excised_and_spliced: ok")


def test_yaml_replace_dropping_token_refused():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "s.yaml", YAML_SAMPLE)
        doc = pd.ProseDocument.open(path)
        para = next(p for p in doc.paragraphs if "overview" in p.context)
        try:
            doc.replace(para.index, "A rewrite that lost the anchor.\n")
            assert False, "dropping the token should raise"
        except sl.LockError:
            pass
    print("  yaml_replace_dropping_token_refused: ok")


# ---------------------------------------------------------------------------
# CLI audit
# ---------------------------------------------------------------------------

def test_cli_audit():
    script = os.path.join(HERE, "span_locks.py")
    with tempfile.TemporaryDirectory() as tmp:
        good = _write(tmp, "good.md", MD_SAMPLE)
        r = subprocess.run([sys.executable, script, good],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "locked span" in r.stdout
        assert "block" in r.stdout and "inline" in r.stdout

        bad = _write(tmp, "bad.md", "text\n<!-- lock -->\nnever closed\n")
        r = subprocess.run([sys.executable, script, bad],
                           capture_output=True, text=True)
        assert r.returncode == 1
        assert "MALFORMED" in r.stderr
    print("  cli_audit: ok")


# ---------------------------------------------------------------------------
# GH-82: the adapter view, the snark-adjacent span, and the written-bytes check
# ---------------------------------------------------------------------------

def test_md_to_parse_result_is_the_excised_view():
    """The surface the drivers read: tokens, not lock bytes. Until GH-82 this
    re-parsed the raw source for markdown, so match-voice and tighten-style
    sent inline-locked text to the model while doc.paragraphs held the
    token form one call away."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = pd.ProseDocument.open(_write(tmp, "s.md", MD_SAMPLE))
        r = doc.to_parse_result()
        texts = [t for _s, _e, t in r.paragraphs]
        assert len(texts) == len(doc.paragraphs) == 3, texts
        joined = "\n".join(texts)
        assert "[[LOCK-1]]" in texts[1], texts[1]
        assert "authored snark" not in joined
        assert "hand-written and locked" not in joined
        # Same Result shape, same line numbers and coverage as the raw parse.
        raw = md_paragraphs.parse(MD_SAMPLE)
        assert [(s, e) for s, e, _ in r.paragraphs] == \
            [(s, e) for s, e, _ in raw.paragraphs]
        assert r.coverage == raw.coverage and r.fm_close == raw.fm_close
        assert r.lines == raw.lines and r.unaccounted == raw.unaccounted
    print("  md_to_parse_result_is_the_excised_view: ok")


def test_inline_lock_with_adjacent_snark_comment():
    """The harness case: a snark tag immediately inside the opening marker,
    an em-dash and a number inside the span. One token, bytes intact."""
    span = ("<!-- lock --><!-- snark:L1-F2 -->That is the profession he is "
            "imitating, run as an experiment — 758 of them.<!-- /lock -->")
    text = f"Lead sentence. {span} Tail sentence."
    clean, manifest = sl.excise(text)
    assert clean == "Lead sentence. [[LOCK-1]] Tail sentence.", clean
    assert manifest == {"[[LOCK-1]]": span}
    assert sl.splice("New lead. [[LOCK-1]] New tail.", manifest) == \
        f"New lead. {span} New tail."
    print("  inline_lock_with_adjacent_snark_comment: ok")


def test_locked_spans_and_verify_preserved():
    """locked_spans lists block and inline spans in document order, and
    verify_preserved sees exactly the span an edit touched."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = pd.ProseDocument.open(_write(tmp, "s.md", MD_SAMPLE))
        spans = doc.locked_spans()
        assert len(spans) == 2, spans
        assert spans[0].startswith("<!-- lock -->\nThis whole block")
        assert spans[0].endswith("```\n<!-- /lock -->"), spans[0]
        assert spans[1] == ("<!-- lock -->the authored snark\nstays exactly "
                            "as written<!-- /lock -->")
        assert sl.verify_preserved(spans, MD_SAMPLE) == []
        bolded = MD_SAMPLE.replace("authored snark", "authored **snark**")
        assert sl.verify_preserved(spans, bolded) == [spans[1]]
        assert sl.verify_preserved(spans, "nothing survived") == spans
        # Multiplicity: one copy does not satisfy two locks of the same text.
        assert sl.verify_preserved(["<!-- lock -->x<!-- /lock -->"] * 2,
                                   "<!-- lock -->x<!-- /lock -->") == \
            ["<!-- lock -->x<!-- /lock -->"]
    print("  locked_spans_and_verify_preserved: ok")


def test_check_tokens():
    orig = "Lead [[LOCK-2]] tail."
    assert sl.check_tokens(orig, "Lead [[LOCK-2]] tail rewritten.") is None
    assert sl.check_tokens("plain", "also plain") is None
    assert "[[LOCK-2]] appears 0 times" in sl.check_tokens(orig, "Lead tail.")
    assert "appears 2 times" in sl.check_tokens(orig, "[[LOCK-2]] [[LOCK-2]]")
    assert "unknown token [[LOCK-7]]" in sl.check_tokens(orig, "[[LOCK-2]] [[LOCK-7]]")
    assert sl.tokens_in("a [[LOCK-3]] b [[LOCK-1]]") == ["[[LOCK-3]]", "[[LOCK-1]]"]
    print("  check_tokens: ok")


def main():
    test_excise_splice_round_trip()
    test_excise_no_locks_is_identity()
    test_excise_escaped_bang_spelling()
    test_excise_rejects_nested()
    test_excise_rejects_close_without_open()
    test_excise_rejects_unclosed()
    test_splice_rejects_dropped_duplicated_unknown()
    test_md_block_lock_classified()
    test_md_lock_opaque_to_fences_and_fences_shield_markers()
    test_md_block_malformed_raise()
    test_md_locked_text_never_in_paragraphs()
    test_md_byte_identical_round_trip_replacing_everything()
    test_md_replace_keeps_locked_bytes()
    test_md_replace_dropping_token_refused()
    test_md_lock_report()
    test_yaml_inline_lock_excised_and_spliced()
    test_yaml_replace_dropping_token_refused()
    test_cli_audit()
    test_md_to_parse_result_is_the_excised_view()
    test_inline_lock_with_adjacent_snark_comment()
    test_locked_spans_and_verify_preserved()
    test_check_tokens()
    print("test_span_locks: all assertions passed")


if __name__ == "__main__":
    main()
