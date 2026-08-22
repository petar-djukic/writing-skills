#!/usr/bin/env python3
"""Offline tests for tighten.py's draft write path (GH-358, GH-82).

Both formats go back through ProseDocument: YAML for valid output with
comments and key order preserved, markdown so that inline lock anchors are
spliced back to their bytes instead of landing in the draft as text. No
network, no model. Run under the agent pixi env (needs ruamel.yaml).
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


LOCKED = ("<!-- lock --><!-- snark:L1-F2 -->That is the profession he is "
          "imitating.<!-- /lock -->")
MD_LOCKED = (f"Lead paragraph with enough words. {LOCKED} And a tail with "
             "enough words to be prose.\n\nSecond paragraph stays put.\n")


def test_md_write_draft_keeps_inline_lock():
    """The GH-82 case: the candidate carries the token, the draft carries
    the locked bytes, and the advisory lines are the file's own."""
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        with open(art, "w") as f:
            f.write(MD_LOCKED)
        out = os.path.join(tmp, "a.tightmd")
        doc = pd.ProseDocument.open(art)
        parsed = doc.to_parse_result()
        s, e, txt = parsed.paragraphs[0]
        assert "[[LOCK-1]]" in txt and "<!-- lock" not in txt, txt
        tightened = [{"n": 1, "lines": [s, e], "words": 3,
                      "cand": "Tight lead. [[LOCK-1]] Tight tail."}]
        stats_lines = tighten.write_draft(doc, ".md", list(parsed.lines),
                                          tightened, out)
        with open(out) as f:
            content = f.read()
        assert f"Tight lead. {LOCKED} Tight tail." in content, content
        assert "[[LOCK-" not in content
        assert "Second paragraph stays put." in content
        assert tightened[0].get("status") != "lock-refused", tightened[0]
        assert any("Tight lead." in l for l in stats_lines)
    print("  md_write_draft_keeps_inline_lock: ok")


def test_md_write_draft_refuses_candidate_without_token():
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        with open(art, "w") as f:
            f.write(MD_LOCKED)
        out = os.path.join(tmp, "a.tightmd")
        doc = pd.ProseDocument.open(art)
        parsed = doc.to_parse_result()
        s, e, _ = parsed.paragraphs[0]
        rec = {"n": 1, "lines": [s, e], "words": 3, "status": "tightened",
               "cand": "A rewrite that ate the anchor and the locked sentence."}
        tighten.write_draft(doc, ".md", list(parsed.lines), [rec], out)
        with open(out) as f:
            content = f.read()
        assert rec["status"] == "lock-refused" and "cand" not in rec, rec
        assert LOCKED in content and "ate the anchor" not in content
        assert content == MD_LOCKED, "refused draft must equal the source"
    print("  md_write_draft_refuses_candidate_without_token: ok")


def main():
    test_yaml_write_draft()
    test_md_write_draft()
    test_md_write_draft_keeps_inline_lock()
    test_md_write_draft_refuses_candidate_without_token()
    print("test_write_draft: all assertions passed")


if __name__ == "__main__":
    main()
