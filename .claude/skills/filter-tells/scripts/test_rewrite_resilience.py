#!/usr/bin/env python3
"""One paragraph's rewrite error must not abandon the rest of the pass
(GH-157), and a cause that recurs for every paragraph must stop the run.

Offline: rewrite_passage is monkeypatched, no model, no network.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import drive  # noqa: E402

# Four paragraphs, each long enough for md_paragraphs to keep, each carrying a
# distinct marker so the assembled draft says which ones were rewritten.
ARTICLE = "\n\n".join(
    f"Paragraph {tag} carries enough ordinary words to be extracted as a "
    f"target by the paragraph parser, and it mentions marker-{tag} so the "
    f"test can find it in the assembled draft afterwards."
    for tag in ("one", "two", "three", "four"))

# A scan that targets everything and validates to not-clean once, then stops
# on no-improvement — one pass is all these tests need.
def _scan():
    return {"lexical": {"issue_count": 4, "issues": []},
            "structural": {"issue_count": 0, "issues": []},
            "verdict": "likely-ai", "needs_step3": True}


def _run(rewrite_fn, max_passes=1):
    orig_rewrite, orig_lex, orig_struct = (
        drive.rewrite_passage, drive.run_lexical, drive.run_structural)
    drive.rewrite_passage = rewrite_fn
    drive.run_lexical = lambda path: {"issue_count": 4, "issues": []}
    drive.run_structural = lambda path, vp=None: {"issue_count": 0, "issues": []}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            art = os.path.join(tmp, "a.md")
            with open(art, "w") as f:
                f.write(ARTICLE)
            result = drive.run_rewrite(art, _scan(), None, "http://unused",
                                       "test-model", 5, max_passes=max_passes)
            draft = open(result["draft_path"]).read() if "draft_path" in result else ""
            return result, draft
    finally:
        drive.rewrite_passage, drive.run_lexical, drive.run_structural = (
            orig_rewrite, orig_lex, orig_struct)


def test_one_failure_does_not_abandon_the_pass():
    def flaky(text, issues, endpoint, model, timeout):
        if "marker-two" in text:
            raise RuntimeError("empty output from Cohere 'm': no text blocks.")
        return text.replace("marker", "REWRITTEN")

    result, draft = _run(flaky)
    p1 = result["passes"][-1]
    assert p1["rewrites_applied"] == 3, p1
    assert "REWRITTEN-one" in draft and "REWRITTEN-three" in draft \
        and "REWRITTEN-four" in draft, draft[:200]
    assert "marker-two" in draft, "failed paragraph must keep its original"
    errs = p1.get("errors", [])
    assert len(errs) == 1 and errs[0]["cause"] == "empty/sanitized-to-empty", errs
    assert "stopped" not in p1 or p1["stopped"] == "no improvement", p1
    print("  one_failure_does_not_abandon_the_pass: ok")


def test_fatal_cause_stops_the_run():
    calls = {"n": 0}

    def refused(text, issues, endpoint, model, timeout):
        calls["n"] += 1
        raise RuntimeError("no Cohere API key. Set COHERE_API_KEY.")

    result, _ = _run(refused, max_passes=3)
    assert calls["n"] == 1, f"a run-fatal cause must not be retried per paragraph, got {calls['n']} calls"
    p1 = result["passes"][-1]
    assert p1.get("stopped", "").startswith("fatal: no-api-key"), p1
    assert len(result["passes"]) == 1, "fatal must also stop later passes"
    print("  fatal_cause_stops_the_run: ok")


def test_per_paragraph_errors_are_each_recorded():
    def always_timeout(text, issues, endpoint, model, timeout):
        raise RuntimeError("Ollama timed out after 5s on model 'm'.")

    result, draft = _run(always_timeout)
    p1 = result["passes"][-1]
    errs = p1.get("errors", [])
    assert len(errs) == 4, errs
    assert all(e["cause"] == "timeout" for e in errs), errs
    assert {e["line"] for e in errs} == {e["line"] for e in errs}  # distinct lines recorded
    assert len({e["line"] for e in errs}) == 4, errs
    assert "marker-one" in draft and "marker-four" in draft, "originals kept"
    print("  per_paragraph_errors_are_each_recorded: ok")


def main():
    test_one_failure_does_not_abandon_the_pass()
    test_fatal_cause_stops_the_run()
    test_per_paragraph_errors_are_each_recorded()
    print("test_rewrite_resilience: all assertions passed")


if __name__ == "__main__":
    main()
