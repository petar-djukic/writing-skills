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


# --- detect_meta_narration (GH-244) ---------------------------------------- #

def test_meta_narration_positive_article_introduces():
    """Evidence sentence from GH-244 L181: 'and this article introduces it'."""
    sents = ds.split_sentences_all(
        "The spec-structure format is new, and this article introduces it. "
        "The format solves the alignment problem between documents.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    assert issues[0]["type"] == "meta-narration"
    assert issues[0]["severity"] == "high"
    print("  meta_narration_positive_article_introduces: ok")


def test_meta_narration_positive_sections_below():
    """Evidence sentence from GH-244 L247."""
    sents = ds.split_sentences_all(
        "The sections below walk the document kinds. "
        "The arrows are what the validator checks.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    assert "sections below" in issues[0]["detail"].lower()
    print("  meta_narration_positive_sections_below: ok")


def test_meta_narration_positive_presented_here():
    """Evidence sentence from GH-244 L269."""
    sents = ds.split_sentences_all(
        "The dependency graph is presented here as a stripped-down skeleton. "
        "Nodes are document types and edges are symbol references.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    assert issues[0]["type"] == "meta-narration"
    print("  meta_narration_positive_presented_here: ok")


def test_meta_narration_positive_as_discussed():
    sents = ds.split_sentences_all(
        "As discussed earlier, the validator rejects cycles. "
        "Cycles introduce ambiguity that no ordering can resolve.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    print("  meta_narration_positive_as_discussed: ok")


def test_meta_narration_positive_in_this_section_we():
    sents = ds.split_sentences_all(
        "In this section, we describe the measurement setup. "
        "The testbed consists of twelve commodity nodes.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    print("  meta_narration_positive_in_this_section_we: ok")


def test_meta_narration_positive_which_we_will():
    sents = ds.split_sentences_all(
        "The scheduler introduces a priority queue, which we will discuss "
        "in the next iteration. "
        "Priority inversion is the failure mode.")
    issues = ds.detect_meta_narration(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    print("  meta_narration_positive_which_we_will: ok")


def test_meta_narration_negative_ordinary_prose():
    """Ordinary sentences about subjects should not fire."""
    sents = ds.split_sentences_all(
        "The system validates each incoming request carefully. "
        "After validation the pipeline forwards it downstream. "
        "Each handler processes its own slice of the work. "
        "Finally the response is assembled and returned.")
    issues = ds.detect_meta_narration(sents)
    assert issues == [], f"false positive: {issues}"
    print("  meta_narration_negative_ordinary_prose: ok")


def test_meta_narration_negative_physical_section():
    """'Section' in a non-document sense should not fire."""
    sents = ds.split_sentences_all(
        "This section of the beam carries the lateral load. "
        "The cross-section is designed for combined bending and shear.")
    issues = ds.detect_meta_narration(sents)
    assert issues == [], f"false positive: {issues}"
    print("  meta_narration_negative_physical_section: ok")


def test_meta_narration_wired_into_paragraph():
    """The detector should fire through filter_tells_paragraph."""
    text = (
        "The spec-structure format is new, and this article introduces it. "
        "Nodes are document types and edges are symbol references. "
        "The validator rejects cycles that no ordering can resolve. "
        "Each document type carries a front-matter schema.")
    result = ds.filter_tells_paragraph(text)
    types = [i["type"] for i in result["issues"]]
    assert "meta-narration" in types, f"expected meta-narration, got {types}"
    assert result["metrics"].get("meta_narration_count", 0) >= 1
    print("  meta_narration_wired_into_paragraph: ok")


def test_meta_narration_wired_into_analyze():
    """The detector should fire through analyze."""
    # Need enough prose to pass the 50-word minimum for analyze()
    text = (
        "The spec-structure format is new, and this article introduces it. "
        "Nodes are document types and edges are symbol references. "
        "The validator rejects cycles that no ordering can resolve. "
        "Each document type carries a front-matter schema that the loader "
        "parses on import. The loader runs a topological sort over the "
        "dependency graph and aborts on the first cycle it finds. "
        "Cycles introduce ambiguity that no ordering can resolve cleanly. "
        "The format solves the alignment problem between architecture "
        "documents and the code that implements them.")
    result = ds.analyze(text)
    types = [i["type"] for i in result["issues"]]
    assert "meta-narration" in types, f"expected meta-narration, got {types}"
    assert result["metrics"].get("meta_narration_count", 0) >= 1
    print("  meta_narration_wired_into_analyze: ok")


# --- detect_consequence_echo (GH-244) -------------------------------------- #

def test_consequence_echo_positive_so_judges():
    """Evidence from GH-244: 'so a criterion can explicitly name what it judges'.

    Overlap coefficient = 1/4 = 0.25 (shared: {judge}). Right at threshold —
    the calibration target for the weakest case that should still fire.
    """
    sents = ds.split_sentences_all(
        "The SRS enumerates numbered items and the acceptance criteria that "
        "judge them, so a criterion can explicitly name what it judges.")
    issues = ds.detect_consequence_echo(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    assert issues[0]["type"] == "consequence-echo"
    assert "judge" in str(issues[0]["detail"]).lower()
    print("  consequence_echo_positive_so_judges: ok")


def test_consequence_echo_positive_clear_echo():
    """Clear echo: the consequence restates the premise with heavy overlap."""
    sents = ds.split_sentences_all(
        "The validator checks the schema and rejects invalid constraints, "
        "so the schema constraints are checked and validated before deployment.")
    issues = ds.detect_consequence_echo(sents)
    assert len(issues) == 1, f"expected 1, got {issues}"
    assert issues[0]["type"] == "consequence-echo"
    print("  consequence_echo_positive_clear_echo: ok")


def test_consequence_echo_conceptual_only():
    """Evidence #2 from GH-244: purely conceptual overlap, no shared words.

    'coupling' and 'component' are related concepts but different stems.
    This class needs the Ross critic, not the lexical detector.
    """
    sents = ds.split_sentences_all(
        "The imports field lists symbols from another component, turning "
        "hidden coupling into a searchable line in the dependency graph.")
    issues = ds.detect_consequence_echo(sents)
    assert issues == [], (
        f"conceptual-only echo should not fire on lexical overlap: {issues}")
    print("  consequence_echo_conceptual_only: ok")


def test_consequence_echo_negative_genuine_consequence():
    """Genuine consequence with distinct vocabulary should not fire."""
    sents = ds.split_sentences_all(
        "The scheduler assigns each job to the least-loaded worker, so "
        "latency stays below the SLA threshold during peak hours.")
    issues = ds.detect_consequence_echo(sents)
    assert issues == [], f"false positive: {issues}"
    print("  consequence_echo_negative_genuine_consequence: ok")


def test_consequence_echo_negative_short_clause():
    """Clauses too short for meaningful overlap should not fire."""
    sents = ds.split_sentences_all(
        "The test passed, so we shipped it.")
    issues = ds.detect_consequence_echo(sents)
    assert issues == [], f"false positive on short clause: {issues}"
    print("  consequence_echo_negative_short_clause: ok")


def test_consequence_echo_negative_low_overlap():
    """Low overlap from shared domain noun should not fire."""
    sents = ds.split_sentences_all(
        "The orchestrator batches incoming requests by region and priority, "
        "which lets the downstream handler apply rate limiting per tenant.")
    issues = ds.detect_consequence_echo(sents)
    assert issues == [], f"false positive below threshold: {issues}"
    print("  consequence_echo_negative_low_overlap: ok")


def test_consequence_echo_wired_into_paragraph():
    """Consequence-echo should appear in paragraph metrics."""
    text = (
        "The SRS enumerates numbered items and the acceptance criteria that "
        "judge them, so a criterion can explicitly name what it judges. "
        "Each criterion traces back to a requirement through its identifier. "
        "The traceability matrix is the artifact that captures the mapping. "
        "Validators check the matrix for completeness on every build.")
    result = ds.filter_tells_paragraph(text)
    assert result["metrics"].get("consequence_echo_count", 0) >= 1
    print("  consequence_echo_wired_into_paragraph: ok")


def test_consequence_echo_advisory_in_analyze():
    """Consequence-echo should be advisory, not a hard issue, in analyze."""
    text = (
        "The validator checks the schema and rejects invalid constraints, "
        "so the schema constraints are checked and validated before deployment. "
        "Each criterion traces back to a requirement through its identifier. "
        "The traceability matrix is the artifact that captures the mapping. "
        "Validators check the matrix for completeness on every build. "
        "The build fails if any requirement lacks a corresponding criterion. "
        "Teams that skip this step discover gaps in acceptance testing. "
        "The cost of late discovery exceeds the cost of early validation.")
    result = ds.analyze(text)
    assert result["metrics"].get("consequence_echo_count", 0) >= 1
    # Should be advisory, not in the hard issues list
    hard_types = [i["type"] for i in result["issues"]]
    advisory_types = [a["type"] for a in result.get("advisory", [])]
    assert "consequence-echo" not in hard_types, (
        f"consequence-echo should be advisory, not hard issue: {hard_types}")
    assert "consequence-echo" in advisory_types, (
        f"expected consequence-echo in advisory, got {advisory_types}")
    print("  consequence_echo_advisory_in_analyze: ok")


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
    test_meta_narration_positive_article_introduces()
    test_meta_narration_positive_sections_below()
    test_meta_narration_positive_presented_here()
    test_meta_narration_positive_as_discussed()
    test_meta_narration_positive_in_this_section_we()
    test_meta_narration_positive_which_we_will()
    test_meta_narration_negative_ordinary_prose()
    test_meta_narration_negative_physical_section()
    test_meta_narration_wired_into_paragraph()
    test_meta_narration_wired_into_analyze()
    test_consequence_echo_positive_so_judges()
    test_consequence_echo_positive_clear_echo()
    test_consequence_echo_conceptual_only()
    test_consequence_echo_negative_genuine_consequence()
    test_consequence_echo_negative_short_clause()
    test_consequence_echo_negative_low_overlap()
    test_consequence_echo_wired_into_paragraph()
    test_consequence_echo_advisory_in_analyze()
    print("test_detect_structural: all assertions passed")


if __name__ == "__main__":
    main()
