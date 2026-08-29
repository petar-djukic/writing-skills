#!/usr/bin/env python3
"""Tests for the burstiness pass (GH-129).

No network, no model: every test injects a fake generator, so what is under
test is the gate and the splice rather than gemma's prose. The one thing that
cannot be faked is whether a rejected paragraph keeps its original text, and
that is what most of these check.

Run: python3 <skill>/scripts/testdata/test_burstiness.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import burstiness  # noqa: E402
import rewrite  # noqa: E402

STYLE = burstiness._style()
SPAN_LOCKS = burstiness._span_locks()

ARTICLE = """# Draft

The system reads the file and writes the result to disk without checking it.
The parser walks the tree and emits the nodes it finds along the way. The
driver loads the model and returns whatever text comes back.

Short one.

A second paragraph carries a citation [@djukic-2007] and the number 42 percent,
and it runs long enough to be eligible because it holds well over twenty five
words across the sentences that make it up.
"""


def write(text, suffix=".md"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def para_of(prompt):
    """The paragraph a prompt carries, minus the conditional lock rule.

    A fake generator that returns the raw slice would hand the driver the
    rule text as prose and trip the word-count band, which is a property of
    the test double rather than of the pass.
    """
    body = prompt.split("Paragraph:\n", 1)[1].rsplit(
        "\n\nRewritten paragraph:", 1)[0]
    return body.split("\n\nThe text contains ", 1)[0].rstrip()


# --------------------------------------------------------------------------- #
# normalize
# --------------------------------------------------------------------------- #

def test_normalize_strips_lead_in():
    assert burstiness.normalize("Rewritten paragraph: The cat sat.") == "The cat sat."
    assert burstiness.normalize("Output:\nThe cat sat.") == "The cat sat."
    assert burstiness.normalize("Here is the rewrite: The cat sat.") == "The cat sat."


def test_normalize_strips_wrapping_quotes():
    assert burstiness.normalize('"The cat sat."') == "The cat sat."
    # an internal quote pair is content, not a wrapper
    assert burstiness.normalize('He said "no" to it.') == 'He said "no" to it.'


def test_normalize_removes_banned_dashes():
    out = burstiness.normalize("The cat sat — the dog ran.")
    assert "—" not in out and "–" not in out
    assert out == "The cat sat. the dog ran."
    assert burstiness.normalize("pages 3 – 4 held it.") == "pages 3, 4 held it."


def test_normalize_collapses_runs():
    assert burstiness.normalize("The  cat   sat.") == "The cat sat."


# --------------------------------------------------------------------------- #
# defect classes
# --------------------------------------------------------------------------- #

def test_defect_counts_finds_each_class():
    c = burstiness.defect_counts(
        "It was fast, cheap, and correct. The meter measured pressure, not flow.")
    assert c["tricolon"] == 1, c
    assert c["x-not-y"] == 1, c


def test_added_defects_is_a_delta_not_a_level():
    """The author's own tricolon is not the pass's to remove or to count."""
    original = "It was fast, cheap, and correct in every run."
    same = "It was fast, cheap, and correct. Every run."
    assert burstiness.added_defects(original, same) == {}


def test_added_defects_catches_an_introduced_construction():
    original = "The meter measured pressure and nothing else at all."
    candidate = "The meter measured pressure, not flow. It said so."
    added = burstiness.added_defects(original, candidate)
    assert "x-not-y" in added, added
    assert added["x-not-y"] == {"before": 0, "after": 1}


# --------------------------------------------------------------------------- #
# judge
# --------------------------------------------------------------------------- #

def judge(original, candidate):
    return burstiness.judge(original, candidate, STYLE, SPAN_LOCKS)


def test_judge_accepts_a_clean_split():
    original = ("The system reads the file and writes the result to disk "
                "without ever checking that the write succeeded.")
    candidate = ("The system reads the file. It writes the result to disk "
                 "without ever checking that the write succeeded.")
    ok, status = judge(original, candidate)
    assert ok, status
    assert status["verdict"] == "rewritten"
    assert status["sentences"]["after"] > status["sentences"]["before"]


def test_judge_rejects_empty():
    ok, status = judge("Some original text here.", "")
    assert not ok and status["reason"] == "empty-response"


def test_judge_rejects_summarised_and_padded():
    original = " ".join(["word"] * 40) + "."
    ok, status = judge(original, "word word.")
    assert not ok and status["reason"] == "word-count-band", status
    ok, status = judge(original, " ".join(["word"] * 90) + ".")
    assert not ok and status["reason"] == "word-count-band", status


def test_judge_rejects_a_lost_citation():
    original = "The result held in the field trial [@djukic-2007] and after."
    candidate = "The result held in the field trial. It held after."
    ok, status = judge(original, candidate)
    assert not ok and status["reason"] == "gate", status
    assert "citations" in status["detail"], status


def test_judge_rejects_an_altered_number():
    original = "Throughput rose by 42 percent across the whole measured run."
    candidate = "Throughput rose by 40 percent. It rose across the whole run."
    ok, status = judge(original, candidate)
    assert not ok and status["reason"] == "gate", status
    assert "numbers" in status["detail"], status


def test_judge_rejects_an_added_defect_class():
    original = ("The meter measured pressure and nothing else, which is what "
                "the specification asked of it in the first place.")
    candidate = ("The meter measured pressure, not flow. That is what the "
                 "specification asked of it.")
    ok, status = judge(original, candidate)
    assert not ok and status["reason"] == "added-defect-class", status


def test_judge_rejects_a_dropped_lock_token():
    original = "Before the token [[LOCK-1]] and a good deal of text after it."
    candidate = "Before the token. A good deal of text after it."
    ok, status = judge(original, candidate)
    assert not ok and status["reason"] == "lock-token", status


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def test_dry_run_calls_no_model_and_reports_eligibility():
    path = write(ARTICLE)
    def explode(*a, **kw):
        raise AssertionError("dry run called the model")
    report = burstiness.run(path, dry_run=True, generate_fn=explode)
    assert report["dry_run"] is True
    assert report["eligible"] == 2, report
    skipped = [r for r in report["paragraphs"] if r["verdict"] == "skipped"]
    assert len(skipped) == 1 and "under 25 words" in skipped[0]["reason"]
    assert report["burstiness"]["before"]["cv"] > 0
    os.unlink(path)


def test_run_splits_sentences_and_reports_a_cv_rise():
    path = write(ARTICLE)
    out = path.replace(".md", "-out.md")

    def splitter(prompt, **kw):
        para = para_of(prompt)
        # split on the first "and", producing one short sentence and one long
        return para.replace(" and ", ". ", 1)

    report = burstiness.run(path, out_path=out, generate_fn=splitter)
    assert report["counts"].get("rewritten") == 2, report["counts"]
    assert report["burstiness"]["delta"]["cv"]["delta"] != 0
    assert os.path.exists(out)
    os.unlink(path)
    os.unlink(out)


def test_a_rejected_paragraph_keeps_its_original_text():
    path = write(ARTICLE)
    out = path.replace(".md", "-out.md")

    def drops_the_citation(prompt, **kw):
        para = para_of(prompt)
        return para.replace("[@djukic-2007] ", "")

    report = burstiness.run(path, out_path=out, generate_fn=drops_the_citation)
    written = open(out).read()
    assert "[@djukic-2007]" in written, "the gate let a lost citation through"
    rejected = [r for r in report["paragraphs"] if r["verdict"] == "rejected"]
    assert len(rejected) == 1 and rejected[0]["reason"] == "gate", report
    os.unlink(path)
    os.unlink(out)


def test_control_arm_sends_the_control_prompt():
    path = write(ARTICLE)
    out = path.replace(".md", "-out.md")
    seen = []

    def capture(prompt, **kw):
        seen.append(kw.get("system"))
        return para_of(prompt)

    report = burstiness.run(path, out_path=out, control=True, generate_fn=capture)
    assert report["arm"] == "control"
    assert seen and all(s == burstiness.CONTROL_SYSTEM for s in seen)
    assert "Keep the same number of sentences" in burstiness.CONTROL_SYSTEM
    os.unlink(path)
    os.unlink(out)


def test_burstiness_arm_sends_the_burstiness_prompt():
    path = write(ARTICLE)
    out = path.replace(".md", "-out.md")
    seen = []

    def capture(prompt, **kw):
        seen.append(kw)
        return para_of(prompt)

    burstiness.run(path, out_path=out, generate_fn=capture)
    assert all(kw["system"] == burstiness.BURSTINESS_SYSTEM for kw in seen)
    # a thinking model's chain-of-thought must not land in the response
    assert all(kw["think"] is False for kw in seen), seen
    os.unlink(path)
    os.unlink(out)


def test_block_locked_text_never_reaches_the_model():
    locked = ARTICLE + """
<!-- lock -->
This authored sentence must survive the pass byte for byte, and it is long
enough that the pass would otherwise rewrite it without a second thought.
<!-- /lock -->
"""
    path = write(locked)
    out = path.replace(".md", "-out.md")
    seen = []

    def capture(prompt, **kw):
        seen.append(prompt)
        return para_of(prompt).replace(" and ", ". ", 1)

    burstiness.run(path, out_path=out, generate_fn=capture)
    assert seen, "no paragraph was sent"
    assert not any("byte for byte" in p for p in seen), "locked text was sent"
    assert "must survive the pass byte for byte" in open(out).read()
    os.unlink(path)
    os.unlink(out)


def test_inline_lock_survives_a_rewrite():
    # Long enough to clear the min-words gate with the locked span excised:
    # word count is measured on the text the model would see, where a lock
    # counts as one anchor token, so a paragraph that is mostly quotation is
    # correctly treated as having little prose to reshape.
    article = ("# Draft\n\nThe system reads the file and then it writes "
               "<!-- lock -->the exact result<!-- /lock --> to disk without "
               "checking that the write actually succeeded, which is the kind "
               "of omission that survives review for years before anyone "
               "notices it at all.\n")
    path = write(article)
    out = path.replace(".md", "-out.md")

    def splitter(prompt, **kw):
        para = para_of(prompt)
        return para.replace(" and ", ". ", 1)

    report = burstiness.run(path, out_path=out, generate_fn=splitter)
    assert report["counts"].get("rewritten") == 1, report
    written = open(out).read()
    assert "<!-- lock -->the exact result<!-- /lock -->" in written, written
    assert "[[LOCK-" not in written, "an anchor token leaked into the output"
    assert written != article, "the paragraph was not actually rewritten"
    os.unlink(path)
    os.unlink(out)


def test_report_warns_when_the_control_moves_cv():
    report = {
        "article": "a.md", "out": "b.md", "arm": "control", "model": "m",
        "paragraphs": [], "counts": {"rewritten": 3},
        "burstiness": {
            "before": {"cv": 0.62}, "after": {"cv": 0.71},
            "delta": {"cv": {"before": 0.62, "after": 0.71, "delta": 0.09}},
        },
    }
    text = burstiness.format_report(report)
    assert "WARNING" in text, text
    report["burstiness"]["after"]["cv"] = 0.621
    report["burstiness"]["delta"]["cv"]["delta"] = 0.001
    assert "WARNING" not in burstiness.format_report(report)


# --------------------------------------------------------------------------- #
# shared transport
# --------------------------------------------------------------------------- #

def test_generate_sends_system_and_think_only_when_asked():
    """A server that predates either field must see the request it saw before."""
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"response": "text"}).encode()

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return FakeResponse()

    real = rewrite.urllib.request.urlopen
    rewrite.urllib.request.urlopen = fake_urlopen
    try:
        rewrite.generate("p", model="m")
        assert "system" not in captured["body"]
        assert "think" not in captured["body"]
        rewrite.generate("p", model="m", system="S", think=False)
        assert captured["body"]["system"] == "S"
        assert captured["body"]["think"] is False
        assert captured["body"]["stream"] is False
    finally:
        rewrite.urllib.request.urlopen = real


def test_lock_rule_is_absent_when_the_paragraph_has_no_tokens():
    """Naming the token unconditionally is what taught the model to invent it."""
    prompt = burstiness.build_prompt("Plain prose with no tokens at all.",
                                     SPAN_LOCKS)
    assert "LOCK" not in prompt, prompt
    assert "[[LOCK-n]]" not in burstiness.BURSTINESS_SYSTEM
    assert "[[LOCK-n]]" not in burstiness.CONTROL_SYSTEM


def test_lock_rule_appears_with_a_count_when_tokens_are_present():
    prompt = burstiness.build_prompt("Before [[LOCK-1]] and after [[LOCK-2]].",
                                     SPAN_LOCKS)
    assert "2 token(s)" in prompt, prompt
    assert prompt.rstrip().endswith("Rewritten paragraph:")


def test_an_invented_lock_token_is_still_rejected():
    """The prompt no longer invites it; the gate still refuses it."""
    ok, status = judge("Plain prose with no tokens at all in it anywhere.",
                       "Plain prose [[LOCK-1]] with no tokens in it anywhere.")
    assert not ok and status["reason"] == "lock-token", status


def test_cv_is_measured_on_prose_not_on_the_raw_file():
    """Headings and code fences are not sentences."""
    noisy = ARTICLE + """
## A heading that is not a sentence

```python
x = 1
```

| a | b |
|---|---|
| 1 | 2 |
"""
    plain = write(ARTICLE)
    loud = write(noisy)
    def explode(*a, **kw):
        raise AssertionError("dry run called the model")
    a = burstiness.run(plain, dry_run=True, generate_fn=explode)
    b = burstiness.run(loud, dry_run=True, generate_fn=explode)
    assert a["burstiness"]["before"] == b["burstiness"]["before"], (
        "markup changed the burstiness reading")
    os.unlink(plain)
    os.unlink(loud)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_burstiness: all assertions passed")


if __name__ == "__main__":
    main()
