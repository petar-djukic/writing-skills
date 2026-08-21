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

Span locks (GH-57): block locks (`<!-- lock -->` alone on a line) never
become paragraphs at all — md_paragraphs classifies the region ``locked``
and line splicing cannot touch it. Inline locks inside a paragraph or YAML
prose scalar are excised on extraction: the ``text`` handed to callers
carries an opaque ``[[LOCK-n]]`` anchor token, the locked bytes stay in a
per-paragraph manifest, and replace() splices them back byte-identical.
Replacement text that drops, duplicates, or invents an anchor raises
span_locks.LockError — refused, not repaired. The aligned view is the
file's own lines and may show locked text; the model-facing surface is
``paragraphs``/``replace``, which never does.

CLI:
  prose_document.py <file> [--json]        list paragraphs
  prose_document.py <file> --replace N     read new text from stdin, replace paragraph N
  prose_document.py <file> --aligned       print the line-aligned prose view
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

YAML_EXCLUDE_KEYS_DEFAULT = [
    "section_goal", "goals.*.goal", "acceptance.*", "meta.*",
]


def _match_key_glob(key_path, pattern):
    """Match a dot-joined key path against a glob pattern.

    Segments are matched literally except ``*`` which matches exactly one
    segment.  A trailing ``.*`` matches anything rooted at the prefix.
    """
    if key_path is None:
        return False
    parts = ".".join(key_path) if isinstance(key_path, list) else key_path
    pp = pattern.split(".")
    kp = parts.split(".")
    if pp[-1] == "*" and len(pp) >= 2:
        prefix = pp[:-1]
        if len(kp) < len(prefix):
            return False
        return all(a == b or a == "*" for a, b in zip(prefix, kp[:len(prefix)]))
    if len(pp) != len(kp):
        return False
    return all(a == b or a == "*" for a, b in zip(pp, kp))


def excluded_indices(paragraphs, patterns):
    """Return set of 1-based paragraph indices whose key_path matches any pattern."""
    out = set()
    for p in paragraphs:
        kp = p._key_path if hasattr(p, "_key_path") else getattr(p, "key_path", None)
        if kp is None:
            continue
        for pat in patterns:
            if _match_key_glob(kp, pat):
                out.add(p.index + 1)
                break
    return out


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

    @property
    def key_path(self):
        return list(self._key_path) if self._key_path else None

    def to_dict(self):
        d = {
            "index": self.index,
            "text": self.text,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "context": self.context,
            "word_count": self.word_count,
        }
        if self._key_path is not None:
            d["key_path"] = self.key_path
        return d


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

    def to_parse_result(self):
        """Backward-compat adapter returning a namedtuple matching
        md_paragraphs.Result(lines, fm_close, paragraphs, coverage, unaccounted).

        Orchestrators that currently call md_paragraphs.parse_file() can switch
        to ProseDocument.open(path).to_parse_result() with no other change.
        """
        raise NotImplementedError

    @property
    def raw(self):
        """The source text exactly as read — for writers that want to emit
        an untouched copy without a round-trip re-emission (GH-360)."""
        raise NotImplementedError

    def aligned_lines(self):
        """Line-aligned prose view: one entry per source line, prose kept on
        its source line, scaffolding blanked. Line-numbered findings against
        this view refer to the real file (same contract as detex --aligned).
        """
        raise NotImplementedError

    def lock_report(self):
        """Locked-span audit: {"block_ranges": [(start, end), ...],
        "inline": [{paragraph, start_line, end_line, tokens}, ...]}.
        """
        raise NotImplementedError


def prose_view_aligned(path):
    """Aligned prose view of any supported file, as a list of lines.

    Markdown is its own prose view (consumers already know its scaffolding),
    so it returns the file's lines unchanged; YAML returns prose scalar
    content on its source lines with keys, comments, and structure blanked.
    """
    return ProseDocument.open(path).aligned_lines()


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
        import span_locks
        self._md_result = md_paragraphs.parse(self._content_from_lines())
        self._paras = []
        self._manifests = []
        next_token = 1
        for start, end, text in self._md_result.paragraphs:
            clean, manifest = span_locks.excise(
                text, start=next_token, base_line=start)
            next_token += len(manifest)
            ctx = self._heading_before(start, self._md_result.coverage)
            self._paras.append(Paragraph(
                index=len(self._paras), text=clean,
                start_line=start, end_line=end,
                context=ctx,
            ))
            self._manifests.append(manifest)

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
        import span_locks
        manifest = self._manifests[index]
        if manifest:
            new_text = span_locks.splice(new_text, manifest)
        p = self._paras[index]
        new_lines = new_text.split("\n")
        self._lines[p.start_line - 1:p.end_line] = new_lines
        self._parse()

    def save(self):
        self.save_as(self._path)

    def save_as(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._content_from_lines())

    def text(self):
        return self._content_from_lines()

    def to_parse_result(self):
        import md_paragraphs
        return md_paragraphs.parse(self._content_from_lines())

    @property
    def raw(self):
        return self._original

    def aligned_lines(self):
        return list(self._lines)

    def lock_report(self):
        cov = self._md_result.coverage
        ranges, cur = [], None
        for ln in sorted(k for k, v in cov.items() if v == "locked"):
            if cur is not None and ln == cur[1] + 1:
                cur[1] = ln
            else:
                cur = [ln, ln]
                ranges.append(cur)
        inline = [{"paragraph": p.index, "start_line": p.start_line,
                   "end_line": p.end_line, "tokens": len(m)}
                  for p, m in zip(self._paras, self._manifests) if m]
        return {"block_ranges": [tuple(r) for r in ranges], "inline": inline}


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
        # Never introduce line wraps the source did not have (GH-360): the
        # default emitter width (80) re-flows every long scalar on save, so
        # replacing one paragraph rewrapped untouched prose across the file.
        self._yaml.width = 2 ** 16
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
                    y.width = 2 ** 16  # same emitter as _yaml (GH-360)
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
        self._manifests = []
        self._next_token = 1
        self._walk(self._data, [])

    def _add_paragraph(self, text, start, end, ctx, key_path):
        import span_locks
        clean, manifest = span_locks.excise(
            text, start=self._next_token, base_line=start)
        self._next_token += len(manifest)
        self._paras.append(Paragraph(
            index=len(self._paras), text=clean,
            start_line=start, end_line=end,
            context=ctx, key_path=key_path,
        ))
        self._manifests.append(manifest)

    def _walk(self, node, path):
        if isinstance(node, dict):
            for key in node:
                child_path = path + [str(key)]
                val = node[key]
                if _is_prose(val):
                    start, end = self._guess_lines(node, key)
                    self._add_paragraph(val.rstrip("\n"), start, end,
                                        ".".join(child_path), child_path)
                    self._refs.append((node, key))
                elif isinstance(val, (dict, list)):
                    self._walk(val, child_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                child_path = path + [str(i)]
                if _is_prose(item):
                    start, end = self._guess_lines_seq(node, i)
                    self._add_paragraph(item.rstrip("\n"), start, end,
                                        ".".join(child_path), child_path)
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
        import span_locks
        manifest = self._manifests[index]
        if manifest:
            new_text = span_locks.splice(new_text, manifest)
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

    def to_parse_result(self):
        from collections import namedtuple
        Result = namedtuple("Result",
                            "lines fm_close paragraphs coverage unaccounted")
        lines = self._raw.split("\n")
        paras = [(p.start_line, p.end_line, p.text) for p in self._paras]
        coverage = {}
        for p in self._paras:
            for ln in range(p.start_line, p.end_line + 1):
                coverage[ln] = "prose"
        return Result(lines=lines, fm_close=-1, paragraphs=paras,
                      coverage=coverage, unaccounted=[])

    @property
    def raw(self):
        return self._raw

    def lock_report(self):
        inline = [{"paragraph": p.index, "start_line": p.start_line,
                   "end_line": p.end_line, "tokens": len(m)}
                  for p, m in zip(self._paras, self._manifests) if m]
        return {"block_ranges": [], "inline": inline}

    # Block-scalar header: optional "- " item marker, optional "key:", then
    # a literal/folded indicator. The prose lives on the following lines.
    _BLOCK_HEADER = re.compile(
        r"^(\s*)(?:-\s+)?(?:[^:#\s][^:]*:)?\s*[>|][+-]?[0-9]*\s*(?:#.*)?$")
    # Inline scalar prefix: "- " item marker and/or "key: " before the value.
    _INLINE_PREFIX = re.compile(r"^\s*(?:-\s+)?(?:[^:#\s][^:]*:\s+)?")

    def _indent(self, line):
        return len(line) - len(line.lstrip())

    def aligned_lines(self):
        raw = self._raw.split("\n")
        out = [""] * len(raw)
        for p in self._paras:
            start = p.start_line
            if not (1 <= start <= len(raw)):
                continue
            header = raw[start - 1]
            m = self._BLOCK_HEADER.match(header)
            if m:
                # Literal/folded scalar: consume the indented block under the
                # header. Blank lines belong to the block only while a deeper-
                # indented line still follows.
                indent = self._indent(header)
                ln = start + 1
                while ln <= len(raw):
                    line = raw[ln - 1]
                    if not line.strip():
                        rest = (raw[j] for j in range(ln, len(raw)))
                        nxt = next((l for l in rest if l.strip()), None)
                        if nxt is not None and self._indent(nxt) > indent:
                            ln += 1
                            continue
                        break
                    if self._indent(line) <= indent:
                        break
                    out[ln - 1] = line.strip()
                    ln += 1
            else:
                # Inline scalar: value starts on the key line; plain-scalar
                # continuations are the deeper-indented lines that follow.
                # A single-line value is taken from the parsed paragraph text,
                # which ruamel has already unquoted and unescaped.
                if "\n" not in p.text and not (
                        start < len(raw)
                        and raw[start].strip()
                        and self._indent(raw[start]) > self._indent(header)):
                    out[start - 1] = p.text
                    continue
                value = self._INLINE_PREFIX.sub("", header).strip()
                qc = value[0] if value[:1] in ("'", '"') else ""
                if qc:
                    value = value[1:]
                    if value.endswith(qc):
                        value = value[:-1]
                    if qc == "'":
                        value = value.replace("''", "'")
                out[start - 1] = value
                indent = self._indent(header)
                ln = start + 1
                while ln <= len(raw):
                    line = raw[ln - 1]
                    if not line.strip() or self._indent(line) <= indent:
                        break
                    cont = line.strip()
                    if qc:
                        if cont.endswith(qc):
                            cont = cont[:-1]
                        if qc == "'":
                            cont = cont.replace("''", "'")
                    out[ln - 1] = cont
                    ln += 1
        return out


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
    ap.add_argument("--aligned", action="store_true",
                    help="print the line-aligned prose view (one line per "
                         "source line, scaffolding blanked)")
    a = ap.parse_args()

    doc = ProseDocument.open(a.file)

    if a.aligned:
        print("\n".join(doc.aligned_lines()))
        return

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
