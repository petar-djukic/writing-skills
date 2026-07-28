#!/usr/bin/env python3
"""Prose document model — extract paragraphs, modify, replace in place.

Opens markdown or YAML files, extracts prose paragraphs with positional
metadata, and supports round-trip replacement: modify a paragraph's text
and write the file back without disturbing anything you did not touch.

    doc = ProseDocument.open("draft.md")
    for p in doc.paragraphs:
        print(p.index, p.context, p.word_count, p.text[:60])
    doc.replace(2, "Rewritten paragraph text here.")
    doc.save()

Markdown backend uses md_paragraphs.py for extraction and line splicing
for replacement. YAML backend uses ruamel.yaml for round-trip preservation
of comments, key order, and scalar style.

CLI:
  prose_document.py <file> [--json]        list paragraphs
  prose_document.py <file> --replace N     read new text from stdin, replace paragraph N
"""

import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MIN_PROSE_WORDS = 5


class Paragraph:
    __slots__ = ("index", "text", "start_line", "end_line",
                 "context", "word_count", "_key_path")

    def __init__(self, index, text, start_line, end_line, context,
                 key_path=None):
        self.index = index
        self.text = text
        self.start_line = start_line
        self.end_line = end_line
        self.context = context
        self.word_count = len(text.split())
        self._key_path = key_path

    def to_dict(self):
        return {
            "index": self.index,
            "text": self.text,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "context": self.context,
            "word_count": self.word_count,
        }


class ProseDocument:
    """Format-dispatching factory. Use ProseDocument.open(path)."""

    @staticmethod
    def open(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".yaml", ".yml"):
            return YamlDocument(path)
        if ext in (".md", ".markdown"):
            return MarkdownDocument(path)
        raise ValueError(f"unsupported format: {ext}")

    @property
    def paragraphs(self):
        raise NotImplementedError

    def replace(self, index, new_text):
        raise NotImplementedError

    def save(self):
        raise NotImplementedError

    def save_as(self, path):
        raise NotImplementedError

    def text(self):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Markdown backend
# ---------------------------------------------------------------------------

class MarkdownDocument(ProseDocument):
    def __init__(self, path):
        self._path = path
        with open(path, encoding="utf-8", errors="replace") as f:
            self._original = f.read()
        self._lines = self._original.split("\n")
        self._parse()

    def _parse(self):
        import md_paragraphs
        r = md_paragraphs.parse(self._content_from_lines())
        self._paras = []
        heading = None
        for ln in range(1, len(self._lines) + 1):
            cat = r.coverage.get(ln)
            if cat == "heading":
                heading = self._lines[ln - 1].lstrip("#").strip()
        heading = None
        for start, end, text in r.paragraphs:
            ctx = self._heading_before(start, r.coverage)
            self._paras.append(Paragraph(
                index=len(self._paras), text=text,
                start_line=start, end_line=end,
                context=ctx,
            ))

    def _heading_before(self, line, coverage):
        for ln in range(line - 1, 0, -1):
            if coverage.get(ln) == "heading":
                return self._lines[ln - 1].lstrip("#").strip()
        return None

    def _content_from_lines(self):
        return "\n".join(self._lines)

    @property
    def paragraphs(self):
        return list(self._paras)

    def replace(self, index, new_text):
        p = self._paras[index]
        new_lines = new_text.split("\n")
        old_count = p.end_line - p.start_line + 1
        new_count = len(new_lines)
        self._lines[p.start_line - 1:p.end_line] = new_lines
        delta = new_count - old_count
        self._parse()

    def save(self):
        self.save_as(self._path)

    def save_as(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._content_from_lines())

    def text(self):
        return self._content_from_lines()


# ---------------------------------------------------------------------------
# YAML backend
# ---------------------------------------------------------------------------

def _is_prose(value):
    if not isinstance(value, str):
        return False
    return len(value.split()) >= MIN_PROSE_WORDS


def _line_span(node, key, parent_line):
    """Best-effort line span for a scalar value in the ruamel tree.

    ruamel.yaml tracks lc (line/column) on mapping keys and sequence items.
    The value's start line is the key's line (for inline) or key's line + 1
    (for block scalars). The end line is estimated from newline count.
    """
    start = parent_line
    if hasattr(node, "lc") and node.lc is not None:
        try:
            start = node.lc.data[key][0] + 1  # 0-indexed -> 1-indexed
        except (KeyError, IndexError, TypeError):
            if isinstance(key, int):
                try:
                    start = node.lc.data[key][0] + 1
                except (KeyError, IndexError, TypeError):
                    pass
    lines_in_value = node[key].count("\n")
    end = start + lines_in_value
    return start, end


class YamlDocument(ProseDocument):
    def __init__(self, path):
        self._path = path
        with open(path, encoding="utf-8") as f:
            self._raw = f.read()
        from ruamel.yaml import YAML
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._detect_indent()
        self._data = self._yaml.load(self._raw)
        self._paras = []
        self._refs = []
        self._extract()

    def _detect_indent(self):
        """Detect indentation from the file so round-trip is byte-identical.

        Tries common indent combinations and picks the one whose dump matches
        the original text. Falls back to (mapping=2, sequence=4, offset=2).
        """
        from ruamel.yaml import YAML
        for mi in (2,):
            for si in (2, 4):
                for off in (0, 2):
                    y = YAML()
                    y.preserve_quotes = True
                    y.indent(mapping=mi, sequence=si, offset=off)
                    data = y.load(self._raw)
                    buf = io.StringIO()
                    y.dump(data, buf)
                    if buf.getvalue() == self._raw:
                        self._yaml.indent(mapping=mi, sequence=si, offset=off)
                        return
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    def _extract(self):
        self._paras = []
        self._refs = []
        self._walk(self._data, [])

    def _walk(self, node, path):
        if isinstance(node, dict):
            for key in node:
                child_path = path + [str(key)]
                val = node[key]
                if _is_prose(val):
                    start, end = self._guess_lines(node, key)
                    ctx = ".".join(child_path)
                    text = val.rstrip("\n")
                    self._paras.append(Paragraph(
                        index=len(self._paras), text=text,
                        start_line=start, end_line=end,
                        context=ctx, key_path=child_path,
                    ))
                    self._refs.append((node, key))
                elif isinstance(val, (dict, list)):
                    self._walk(val, child_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                child_path = path + [str(i)]
                if _is_prose(item):
                    start, end = self._guess_lines_seq(node, i)
                    ctx = ".".join(child_path)
                    text = item.rstrip("\n")
                    self._paras.append(Paragraph(
                        index=len(self._paras), text=text,
                        start_line=start, end_line=end,
                        context=ctx, key_path=child_path,
                    ))
                    self._refs.append((node, i))
                elif isinstance(item, (dict, list)):
                    self._walk(item, child_path)

    def _guess_lines(self, node, key):
        start = 1
        if hasattr(node, "lc") and node.lc is not None:
            try:
                kl = node.lc.key(key)
                start = kl[0] + 1
            except (KeyError, AttributeError):
                pass
        val = node[key]
        if isinstance(val, str):
            n_lines = val.count("\n")
            if val.endswith("\n"):
                n_lines -= 1
            return start, start + max(0, n_lines)
        return start, start

    def _guess_lines_seq(self, node, idx):
        start = 1
        if hasattr(node, "lc") and node.lc is not None:
            try:
                start = node.lc.data[idx][0] + 1
            except (KeyError, IndexError, TypeError):
                pass
        val = node[idx]
        if isinstance(val, str):
            n_lines = val.count("\n")
            if val.endswith("\n"):
                n_lines -= 1
            return start, start + max(0, n_lines)
        return start, start

    @property
    def paragraphs(self):
        return list(self._paras)

    def replace(self, index, new_text):
        node, key = self._refs[index]
        old_val = node[key]
        if isinstance(old_val, str) and old_val.endswith("\n"):
            if not new_text.endswith("\n"):
                new_text = new_text + "\n"
        from ruamel.yaml.scalarstring import LiteralScalarString
        if isinstance(old_val, LiteralScalarString) or (
                isinstance(old_val, str) and "\n" in old_val):
            node[key] = LiteralScalarString(new_text)
        else:
            node[key] = new_text
        self._extract()

    def save(self):
        self.save_as(self._path)

    def save_as(self, path):
        buf = io.StringIO()
        self._yaml.dump(self._data, buf)
        with open(path, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())

    def text(self):
        buf = io.StringIO()
        self._yaml.dump(self._data, buf)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="prose document model — extract and replace paragraphs")
    ap.add_argument("file", help="markdown or yaml file")
    ap.add_argument("--json", action="store_true",
                    help="emit paragraphs as JSON")
    ap.add_argument("--replace", type=int, metavar="N",
                    help="replace paragraph N with text from stdin")
    a = ap.parse_args()

    doc = ProseDocument.open(a.file)

    if a.replace is not None:
        new_text = sys.stdin.read().rstrip("\n")
        doc.replace(a.replace, new_text)
        doc.save()
        print(f"replaced paragraph {a.replace} ({doc.paragraphs[a.replace].word_count} words)")
        return

    if a.json:
        print(json.dumps([p.to_dict() for p in doc.paragraphs], indent=2))
        return

    for p in doc.paragraphs:
        ctx = f"  [{p.context}]" if p.context else ""
        print(f"  {p.index:>3}  L{p.start_line:>4}-{p.end_line:<4} "
              f"{p.word_count:>3}w{ctx}  {p.text[:60]}")


if __name__ == "__main__":
    main()
