#!/usr/bin/env python3
"""Offline tests for prose_document.py.
Run: python3 <surface>/scripts/test_prose_document.py

Tests both the markdown and YAML backends against their respective fixtures.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prose_document as pd  # noqa: E402

MD_SAMPLE = os.path.join(HERE, "testdata_pangram_sample.md")
YAML_SAMPLE = os.path.join(HERE, "testdata_prose_sample.yaml")


def test_md_extraction():
    doc = pd.ProseDocument.open(MD_SAMPLE)
    assert isinstance(doc, pd.MarkdownDocument)
    paras = doc.paragraphs
    assert len(paras) == 3, f"expected 3 prose paragraphs, got {len(paras)}"
    assert paras[0].context == "Scheduling"
    assert paras[0].start_line < paras[1].start_line
    assert paras[0].word_count > 0
    assert "scheduler" in paras[0].text.lower()
    print("  md_extraction: ok")


def test_md_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.md")
        shutil.copy2(MD_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.save()
        with open(copy, encoding="utf-8") as f:
            after = f.read()
        with open(MD_SAMPLE, encoding="utf-8") as f:
            before = f.read()
        assert after == before, "round-trip changed the file"
    print("  md_round_trip: ok")


def test_md_replace_single():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.md")
        shutil.copy2(MD_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        old_text = doc.paragraphs[1].text
        doc.replace(1, "Replaced paragraph here.")
        assert doc.paragraphs[1].text == "Replaced paragraph here."
        doc.save()
        doc2 = pd.ProseDocument.open(copy)
        assert doc2.paragraphs[1].text == "Replaced paragraph here."
        assert "Replaced paragraph here." in doc2.text()
        assert old_text not in doc2.text()
    print("  md_replace_single: ok")


def test_md_replace_multiple():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.md")
        shutil.copy2(MD_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.replace(0, "First replacement.")
        doc.replace(1, "Second replacement.")
        doc.save()
        doc2 = pd.ProseDocument.open(copy)
        assert doc2.paragraphs[0].text == "First replacement."
        assert doc2.paragraphs[1].text == "Second replacement."
        assert len(doc2.paragraphs) == 3
    print("  md_replace_multiple: ok")


def test_md_replace_multiline():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.md")
        shutil.copy2(MD_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.replace(0, "Line one of the replacement.\nLine two continues here.")
        doc.save()
        doc2 = pd.ProseDocument.open(copy)
        assert "Line one" in doc2.paragraphs[0].text
        assert "Line two" in doc2.paragraphs[0].text
    print("  md_replace_multiline: ok")


def test_md_structure_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.md")
        shutil.copy2(MD_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.replace(0, "New first paragraph.")
        doc.save()
        with open(copy, encoding="utf-8") as f:
            content = f.read()
        assert "# Scheduling" in content, "heading lost"
        assert "```python" in content, "code fence lost"
        assert "| Run |" in content, "table lost"
    print("  md_structure_preserved: ok")


def test_md_paragraph_dict():
    doc = pd.ProseDocument.open(MD_SAMPLE)
    d = doc.paragraphs[0].to_dict()
    assert d["index"] == 0
    assert "text" in d and "start_line" in d and "context" in d
    assert d["word_count"] == len(d["text"].split())
    print("  md_paragraph_dict: ok")


def test_yaml_extraction():
    doc = pd.ProseDocument.open(YAML_SAMPLE)
    assert isinstance(doc, pd.YamlDocument)
    paras = doc.paragraphs
    assert len(paras) >= 3, f"expected at least 3 prose paragraphs, got {len(paras)}"
    contexts = [p.context for p in paras]
    assert any("summary" in c for c in contexts), f"missing summary context: {contexts}"
    assert any("lifecycle" in c for c in contexts), f"missing lifecycle context: {contexts}"
    assert any("responsibility" in c for c in contexts), \
        f"missing responsibility context: {contexts}"
    for p in paras:
        assert p.word_count >= pd.MIN_PROSE_WORDS
    print("  yaml_extraction: ok")


def test_yaml_short_values_excluded():
    doc = pd.ProseDocument.open(YAML_SAMPLE)
    texts = [p.text for p in doc.paragraphs]
    assert not any("short value not prose" in t for t in texts), \
        "short scalar should not be extracted as prose"
    print("  yaml_short_values_excluded: ok")


def test_yaml_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.yaml")
        shutil.copy2(YAML_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.save()
        with open(copy, encoding="utf-8") as f:
            after = f.read()
        with open(YAML_SAMPLE, encoding="utf-8") as f:
            before = f.read()
        assert after == before, (
            f"round-trip changed the file.\n"
            f"BEFORE ({len(before)} chars):\n{before[:500]}\n"
            f"AFTER ({len(after)} chars):\n{after[:500]}")
    print("  yaml_round_trip: ok")


def test_yaml_replace():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.yaml")
        shutil.copy2(YAML_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        summary_idx = next(i for i, p in enumerate(doc.paragraphs)
                          if "summary" in p.context)
        doc.replace(summary_idx, "Replaced summary paragraph.\nSecond line.")
        doc.save()
        doc2 = pd.ProseDocument.open(copy)
        replaced = doc2.paragraphs[summary_idx]
        assert "Replaced summary" in replaced.text
        assert "Second line" in replaced.text
    print("  yaml_replace: ok")


def test_yaml_comment_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.yaml")
        shutil.copy2(YAML_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        summary_idx = next(i for i, p in enumerate(doc.paragraphs)
                          if "summary" in p.context)
        doc.replace(summary_idx, "New summary text goes here.\n")
        doc.save()
        with open(copy, encoding="utf-8") as f:
            content = f.read()
        assert "# This comment must survive" in content, \
            "YAML comment was lost during replace"
    print("  yaml_comment_preserved: ok")


def test_yaml_key_order_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.yaml")
        shutil.copy2(YAML_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.replace(0, "Modified first paragraph.\n")
        doc.save()
        with open(copy, encoding="utf-8") as f:
            content = f.read()
        id_pos = content.index("id:")
        title_pos = content.index("title:")
        overview_pos = content.index("overview:")
        components_pos = content.index("components:")
        assert id_pos < title_pos < overview_pos < components_pos, \
            "key order was not preserved"
    print("  yaml_key_order_preserved: ok")


def test_yaml_replace_multiple():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.yaml")
        shutil.copy2(YAML_SAMPLE, copy)
        doc = pd.ProseDocument.open(copy)
        doc.replace(0, "First replacement paragraph with enough words to qualify.\n")
        doc.replace(1, "Second replacement paragraph also with enough words here.\n")
        doc.save()
        doc2 = pd.ProseDocument.open(copy)
        assert "First replacement" in doc2.paragraphs[0].text
        assert "Second replacement" in doc2.paragraphs[1].text
    print("  yaml_replace_multiple: ok")


def test_save_as():
    with tempfile.TemporaryDirectory() as tmp:
        out_md = os.path.join(tmp, "out.md")
        doc = pd.ProseDocument.open(MD_SAMPLE)
        doc.save_as(out_md)
        assert os.path.exists(out_md)
        doc2 = pd.ProseDocument.open(out_md)
        assert len(doc2.paragraphs) == len(doc.paragraphs)

        out_yaml = os.path.join(tmp, "out.yaml")
        doc3 = pd.ProseDocument.open(YAML_SAMPLE)
        doc3.save_as(out_yaml)
        assert os.path.exists(out_yaml)
    print("  save_as: ok")


def test_unsupported_format():
    try:
        pd.ProseDocument.open("file.txt")
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert ".txt" in str(e)
    print("  unsupported_format: ok")


def main():
    test_md_extraction()
    test_md_round_trip()
    test_md_replace_single()
    test_md_replace_multiple()
    test_md_replace_multiline()
    test_md_structure_preserved()
    test_md_paragraph_dict()
    test_yaml_extraction()
    test_yaml_short_values_excluded()
    test_yaml_round_trip()
    test_yaml_replace()
    test_yaml_comment_preserved()
    test_yaml_key_order_preserved()
    test_yaml_replace_multiple()
    test_save_as()
    test_unsupported_format()
    print("test_prose_document: all assertions passed")


if __name__ == "__main__":
    main()
