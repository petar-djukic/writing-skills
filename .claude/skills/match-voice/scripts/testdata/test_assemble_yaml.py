#!/usr/bin/env python3
"""Offline tests for YAML draft assembly (GH-358).

Raw line splicing dropped bare prose over keys and block markers, so a YAML
draft with any accepted rewrite was an invalid document. These pin the
ProseDocument write path: valid YAML out, comments and key order preserved,
untouched scalars byte-identical.

No network, no model. Run under the agent pixi env (needs ruamel.yaml).
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402

SAMPLE = """\
id: spec-1
# keep this comment
overview:
  summary: |
    The first prose paragraph carries enough words to be extracted here.
  detail: |
    The second prose paragraph also carries enough words to be extracted.
meta:
  note: not prose
"""


def _skip_without_ruamel(name):
    """False (and a legible skip) when ruamel.yaml is unavailable — it is a
    pixi-env dependency, and the docstring above says so; this makes the
    interpreter say it too instead of a bare ModuleNotFoundError (GH-158)."""
    try:
        import ruamel.yaml  # noqa: F401
        return True
    except ImportError:
        msg = (f"{name}: ruamel.yaml not installed — run under the pixi env "
               "(scripts/run-tests.sh)")
        if "pytest" in sys.modules:
            import pytest
            pytest.skip(msg)
        print(f"  SKIP  {msg}")
        return False


def test_yaml_assemble_round_trip():
    if not _skip_without_ruamel("yaml_assemble_round_trip"):
        return
    from ruamel.yaml import YAML
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "spec.yaml")
        with open(art, "w") as f:
            f.write(SAMPLE)
        out = os.path.join(tmp, "spec.vr-draft.yaml")
        lines, _, paras, _, _, _ = drive.parse_paragraphs(art, 0)
        assert len(paras) == 2, f"expected 2 prose paragraphs, got {len(paras)}"
        accept = {1: "A replacement paragraph with plenty of words in it."}
        rng = {n: (s, e) for n, (s, e, _) in enumerate(paras, 1)}
        drive.assemble_draft(art, lines, accept, rng, out)

        with open(out) as f:
            content = f.read()
        data = YAML().load(content)  # parses => valid YAML
        assert "A replacement paragraph" in data["overview"]["summary"]
        assert "second prose paragraph" in data["overview"]["detail"], \
            "untouched scalar changed"
        assert "# keep this comment" in content, "comment lost"
        assert content.index("id:") < content.index("overview:") \
            < content.index("meta:"), "key order lost"
    print("  yaml_assemble_round_trip: ok")


def test_md_assemble_unchanged():
    md = "First paragraph with enough words here.\n\nSecond paragraph stays.\n"
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        with open(art, "w") as f:
            f.write(md)
        out = os.path.join(tmp, "a.vr-draft.md")
        lines, _, paras, _, _, _ = drive.parse_paragraphs(art, 0)
        accept = {1: "Replaced first paragraph."}
        rng = {n: (s, e) for n, (s, e, _) in enumerate(paras, 1)}
        drive.assemble_draft(art, lines, accept, rng, out)
        with open(out) as f:
            content = f.read()
    assert content.startswith("Replaced first paragraph.")
    assert "Second paragraph stays." in content
    print("  md_assemble_unchanged: ok")


def main():
    test_yaml_assemble_round_trip()
    test_md_assemble_unchanged()
    print("test_assemble_yaml: all assertions passed")


if __name__ == "__main__":
    main()
