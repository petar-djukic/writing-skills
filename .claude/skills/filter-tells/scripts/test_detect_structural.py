#!/usr/bin/env python3
"""Tests for filter_tells_paragraph and detect_paragraph backward compat."""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import importlib
ds = importlib.import_module("detect-structural")


def test_filter_tells_paragraph_returns_shape():
    text = (
        "The system processes incoming requests through a pipeline. "
        "The pipeline validates each request against the schema. "
        "The validator rejects malformed payloads. "
        "The rejected payloads are logged for later analysis. "
        "The logs are rotated daily to conserve disk space."
    )
    result = ds.filter_tells_paragraph(text)
    assert "issues" in result
    assert "metrics" in result
    assert isinstance(result["issues"], list)
    assert isinstance(result["metrics"], dict)
    assert result["metrics"]["word_count"] > 0
    print("  filter_tells_paragraph_returns_shape: ok")


def test_detect_paragraph_alias():
    assert ds.detect_paragraph is ds.filter_tells_paragraph
    text = "Short text with enough words to pass the minimum threshold here now."
    r1 = ds.filter_tells_paragraph(text)
    r2 = ds.detect_paragraph(text)
    assert r1["metrics"]["word_count"] == r2["metrics"]["word_count"]
    print("  detect_paragraph_alias: ok")


def test_parallelism_detected():
    text = (
        "The system validates the input. "
        "The system processes the request. "
        "The system returns the response. "
        "The system logs the transaction. "
        "Finally it shuts down the connection."
    )
    result = ds.filter_tells_paragraph(text, threshold_name="strict")
    types = [i["type"] for i in result["issues"]]
    assert "parallelism" in types, f"expected parallelism issue, got {types}"
    assert result["metrics"].get("parallelism_runs", 0) > 0
    print("  parallelism_detected: ok")


def test_no_parallelism_on_varied_openers():
    text = (
        "The system validates each incoming request carefully. "
        "After validation the pipeline forwards it downstream. "
        "Each handler processes its own slice of the work. "
        "Finally the response is assembled and returned."
    )
    result = ds.filter_tells_paragraph(text)
    types = [i["type"] for i in result["issues"]]
    assert "parallelism" not in types, f"false positive: {types}"
    print("  no_parallelism_on_varied_openers: ok")


def test_short_paragraph_skipped():
    result = ds.filter_tells_paragraph("Too short.")
    assert result["issues"] == []
    assert result["metrics"]["word_count"] < 10
    print("  short_paragraph_skipped: ok")


def test_dominant_opener_detected():
    sentences = []
    for i in range(6):
        sentences.append(f"The component number {i} handles its own state carefully.")
    sentences.append("Finally the system returns a result to the caller.")
    text = " ".join(sentences)
    result = ds.filter_tells_paragraph(text, threshold_name="strict")
    assert result["metrics"].get("dominant_opener") == "the"
    print("  dominant_opener_detected: ok")


def test_para_index_in_issues():
    text = (
        "The system validates the input. "
        "The system processes the request. "
        "The system returns the response. "
        "The system logs the result carefully."
    )
    result = ds.filter_tells_paragraph(text, para_index=5, threshold_name="strict")
    for issue in result["issues"]:
        if "paragraph" in issue:
            assert issue["paragraph"] == 6
    print("  para_index_in_issues: ok")


def _skip_without_ruamel(name):
    """False (and a legible skip) when ruamel.yaml is unavailable.

    ruamel is a pixi-env dependency — run-tests.sh always has it. Under a bare
    interpreter, pytest gets a real skip and the standalone runner prints one
    and moves on; both beat the JSONDecodeError this replaced (GH-158)."""
    try:
        import ruamel.yaml  # noqa: F401
        return True
    except ImportError:
        msg = (f"{name}: ruamel.yaml not installed — YAML prose-view tests "
               "run under the pixi env (scripts/run-tests.sh)")
        if "pytest" in sys.modules:
            import pytest
            pytest.skip(msg)
        print(f"  SKIP  {msg}")
        return False


def test_yaml_directory_and_file_input():
    """YAML files are collected and analyzed through the aligned prose view
    (GH-345): metrics see prose scalar content only, never keys or comments."""
    # The YAML prose view needs ruamel.yaml, a pixi-env dependency. Outside
    # that env the subprocess dies with a ModuleNotFoundError traceback and
    # exit 1 — the same exit code as "issues found" — so before GH-158 this
    # test accepted the crash and then failed parsing empty stdout as a bare
    # JSONDecodeError that pointed nowhere. Skip legibly instead.
    if not _skip_without_ruamel("yaml_directory_and_file_input"):
        return
    import subprocess
    sample = os.path.normpath(os.path.join(
        HERE, "..", "..", "..", "scripts", "testdata_prose_sample.yaml"))
    script = os.path.join(HERE, "detect-structural.py")
    r = subprocess.run([sys.executable, script, sample, "--json"],
                       capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr
    assert r.stdout.strip(), (
        f"detect-structural.py exited {r.returncode} with no JSON on stdout; "
        f"stderr:\n{r.stderr}")
    import json as _json
    result = _json.loads(r.stdout)
    assert result["file"].endswith("testdata_prose_sample.yaml")
    assert result["metrics"]["word_count"] > 0
    # Directory input picks the yaml file up.
    r2 = subprocess.run([sys.executable, script,
                         os.path.dirname(sample), "--json"],
                        capture_output=True, text=True)
    assert r2.returncode in (0, 1), r2.stderr
    assert "testdata_prose_sample.yaml" in r2.stdout
    print("  yaml_directory_and_file_input: ok")


# --- brief_echo_repetition (GH-30) --------------------------------------- #
# The fixture is the shape of the real evidence: one scope claim restated once
# per file, sharing almost no wording. That is the class — a matcher keyed on
# wording finds none of them.

BRIEF_ECHO_FILES = [
    ("01-intro.md",
     "Autonomic networks close a control loop without a human in it. "
     "This document prescribes no implementation technology. "
     "Operators run different stacks, and the argument holds across them."),
    ("02-functional.md",
     "The functional view decomposes the loop into five capabilities. "
     "It names no products, runtimes, or deployment topologies. "
     "What implements a capability is a per-deployment choice."),
    ("03-information.md",
     "State moves through the loop in three shapes. "
     "The information view says nothing about database schemas, "
     "serialization formats, or storage products. "
     "Retention is where implementations first diverge."),
]


def test_brief_echo_clusters_paraphrases_across_files():
    out = ds.brief_echo_repetition(BRIEF_ECHO_FILES)
    kinds = {b["kind"]: b for b in out}
    assert "scope-negation" in kinds, out
    b = kinds["scope-negation"]
    assert b["files"] == 3, b
    assert b["count"] == 3, b
    # The finding must not depend on shared wording. If this ever rises to a
    # level an overlap threshold could cluster, the fixture has stopped being
    # representative of the class.
    assert b["max_overlap"] < 0.35, b["max_overlap"]
    print("  brief_echo_clusters_paraphrases_across_files: ok")


def test_brief_echo_silent_on_one_occurrence():
    files = [BRIEF_ECHO_FILES[0],
             ("02.md", "The functional view decomposes the loop into five "
                       "capabilities. Each consumes a defined input and emits "
                       "a defined output."),
             ("03.md", "State moves through the loop in three shapes. Each "
                       "shape has an owner and a retention rule.")]
    assert ds.brief_echo_repetition(files) == []
    print("  brief_echo_silent_on_one_occurrence: ok")


def test_brief_echo_ignores_repeated_domain_vocabulary():
    # Heavy shared vocabulary, no claim about the artifact. The trigger is the
    # construction, not the words, so repetition alone must not fire.
    files = [(f"{i}.md",
              "The capability boundary is testable rather than notional. "
              "Each capability consumes a defined input and emits a defined "
              "output. The deployment topology follows from the capability "
              "split, and the capability model is what implementations share.")
             for i in range(4)]
    assert ds.brief_echo_repetition(files) == []
    print("  brief_echo_ignores_repeated_domain_vocabulary: ok")


def test_brief_echo_is_cross_file_only():
    # All three sentences in one file: not a finding. A single file cannot
    # carry the evidence, because the tell is one occurrence per generation
    # unit — and a per-file scan must not start reporting this.
    merged = [("all.md", " ".join(t for _, t in BRIEF_ECHO_FILES))]
    assert ds.brief_echo_repetition(merged) == []
    print("  brief_echo_is_cross_file_only: ok")


def main():
    test_filter_tells_paragraph_returns_shape()
    test_detect_paragraph_alias()
    test_parallelism_detected()
    test_no_parallelism_on_varied_openers()
    test_short_paragraph_skipped()
    test_dominant_opener_detected()
    test_para_index_in_issues()
    test_yaml_directory_and_file_input()
    test_brief_echo_clusters_paraphrases_across_files()
    test_brief_echo_silent_on_one_occurrence()
    test_brief_echo_ignores_repeated_domain_vocabulary()
    test_brief_echo_is_cross_file_only()
    print("test_detect_structural: all assertions passed")


if __name__ == "__main__":
    main()
