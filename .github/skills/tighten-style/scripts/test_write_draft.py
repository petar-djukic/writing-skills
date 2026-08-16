#!/usr/bin/env python3
"""Offline tests for tighten.py's draft write path (GH-358).

YAML drafts go back through ProseDocument (valid YAML out, comments and key
order preserved); markdown keeps bottom-up line splicing. No network, no
model. Run under the agent pixi env (needs ruamel.yaml).
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)
import tighten  # noqa: E402
import prose_document as pd  # noqa: E402

SAMPLE = """\
id: spec-1
# keep this comment
overview:
  summary: |
    The first prose paragraph carries enough words to be extracted here.
  detail: |
    The second prose paragraph also carries enough words to be extracted.
"""


def test_yaml_write_draft():
    from ruamel.yaml import YAML
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "spec.yaml")
        with open(art, "w") as f:
            f.write(SAMPLE)
        out = os.path.join(tmp, "spec.tightyaml")
        doc = pd.ProseDocument.open(art)
        parsed = doc.to_parse_result()
        tightened = [{"n": 1, "lines": list(parsed.paragraphs[0][:2]),
                      "cand": "A tightened paragraph with plenty of words.",
                      "words": 11}]
        stats_lines = tighten.write_draft(doc, ".yaml", list(parsed.lines),
                                          tightened, out)
        with open(out) as f:
            content = f.read()
        data = YAML().load(content)  # parses => valid YAML
        assert "A tightened paragraph" in data["overview"]["summary"]
        assert "second prose paragraph" in data["overview"]["detail"]
        assert "# keep this comment" in content, "comment lost"
        assert stats_lines, "stats lines empty"
        assert all("summary" not in l for l in stats_lines), \
            "stats lines carry yaml keys"
    print("  yaml_write_draft: ok")


def test_md_write_draft():
    md = "First paragraph with enough words here.\n\nSecond paragraph stays.\n"
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        with open(art, "w") as f:
            f.write(md)
        out = os.path.join(tmp, "a.tightmd")
        doc = pd.ProseDocument.open(art)
        parsed = doc.to_parse_result()
        s, e, _ = parsed.paragraphs[0]
        tightened = [{"n": 1, "lines": [s, e], "cand": "Replaced.", "words": 1}]
        stats_lines = tighten.write_draft(doc, ".md", list(parsed.lines),
                                          tightened, out)
        with open(out) as f:
            content = f.read()
        assert content.startswith("Replaced.")
        assert "Second paragraph stays." in content
        assert stats_lines
    print("  md_write_draft: ok")


def main():
    test_yaml_write_draft()
    test_md_write_draft()
    print("test_write_draft: all assertions passed")


if __name__ == "__main__":
    main()
