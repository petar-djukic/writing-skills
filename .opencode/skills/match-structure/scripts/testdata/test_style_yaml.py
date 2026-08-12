#!/usr/bin/env python3
"""Tests for GH-347: style.py profiles YAML documents over prose fields only.

Run: python3 testdata/test_style_yaml.py  (needs ruamel.yaml, run under pixi)
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import style  # noqa: E402

SAMPLE_YAML = """\
id: sample-spec
title: "Short Title"

# structural comment
overview:
  summary: |
    The system provides a pipeline from specifications to verified binaries.
    Each utility follows the same flow through extraction and synthesis.
goals:
- id: G1
  goal: The article establishes the question as open and states its answer.
"""


def _write_sample(tmp):
    path = os.path.join(tmp, "sample.yaml")
    with open(path, "w") as f:
        f.write(SAMPLE_YAML)
    return path


def test_read_prose_extracts_fields_only():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_sample(tmp)
        text = style.read_prose(path)
    assert "pipeline from specifications" in text
    assert "states its answer" in text
    assert "summary:" not in text, "yaml key leaked into prose view"
    assert "overview:" not in text, "yaml key leaked into prose view"
    assert "# structural comment" not in text, "comment leaked into prose view"
    assert "sample-spec" not in text, "non-prose scalar leaked into prose view"


def test_profile_metrics_over_prose():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_sample(tmp)
        prof = style.profile_file(path)
    m = prof["overall"]
    assert m["words"] > 0
    # Word count covers the two prose fields only, well under the raw file.
    assert m["words"] < len(SAMPLE_YAML.split()), \
        f"profile measured raw YAML ({m['words']} words)"
    assert "summary" not in prof["frequency"]["words"]
    assert "goal" not in prof["frequency"]["words"]


def main():
    test_read_prose_extracts_fields_only()
    test_profile_metrics_over_prose()
    print("test_style_yaml: all assertions passed")


if __name__ == "__main__":
    main()
