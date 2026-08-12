#!/usr/bin/env python3
"""Tests for filter_tells_paragraph and detect_paragraph backward compat."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
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


def test_yaml_directory_and_file_input():
    """YAML files are collected and analyzed through the aligned prose view
    (GH-345): metrics see prose scalar content only, never keys or comments."""
    import subprocess
    sample = os.path.normpath(os.path.join(
        HERE, "..", "..", "..", "scripts", "testdata_prose_sample.yaml"))
    script = os.path.join(HERE, "detect-structural.py")
    r = subprocess.run([sys.executable, script, sample, "--json"],
                       capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr
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


def main():
    test_filter_tells_paragraph_returns_shape()
    test_detect_paragraph_alias()
    test_parallelism_detected()
    test_no_parallelism_on_varied_openers()
    test_short_paragraph_skipped()
    test_dominant_opener_detected()
    test_para_index_in_issues()
    test_yaml_directory_and_file_input()
    print("test_detect_structural: all assertions passed")


if __name__ == "__main__":
    main()
