#!/usr/bin/env python3
"""RST marker parsing, validation, and repair for reverse-outline (GH-88).

A marker is one HTML comment line immediately above a heading or a prose
paragraph:

    <!-- rst: <relation>[ -> <n>] | <one line: what it does for its target> -->

The relation set is closed and lives in ../references/relations.md; this module
holds the same names and nothing else may be used. `-> n` is the 1-indexed
paragraph WITHIN the section that a satellite attaches to; omitted, the target
is the section nucleus. Depth is the number of hops to that nucleus, computed
here and never written into the file — a stored depth is a second source of
truth that `renumber` would have to keep honest after every edit.

Markers are comments because comments already survive the pipeline. Locked
spans have travelled it since GH-57; md_paragraphs classifies comment lines as
non-prose, by content and state since GH-86; the replacement drivers splice
prose line ranges only. Nothing new was needed to make the structure persist.

Library:
  parse(path)               -> Outline(units, markers, errors)
  check(outline)            -> [Problem, ...]   structural violations
  renumber(path)            -> (text, [Problem, ...]) targets repaired
  strip(text)               -> text with every rst marker line removed
  insert(path, by_index)    -> text with markers written above their units

CLI:
  rst_markers.py parse   <file.md> [--json]
  rst_markers.py check   <file.md> [--renumber] [--json]
  rst_markers.py strip   <file.md> [--in-place]
  exit 1 on any structural violation, 2 on usage.
"""

import argparse
import json
import os
import re
import sys

SK = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
for _d in (SHARED, SK):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import md_paragraphs                                        # noqa: E402
import prose_document                                       # noqa: E402
import span_locks                                           # noqa: E402

# The closed set, mirroring references/relations.md. A label outside it is a
# structural error, not a warning: an unknown relation has no cut rank, so
# rank.py could not place the paragraph even if it wanted to.
PRESENTATIONAL = ("evidence", "justify", "concession", "antithesis",
                  "motivation", "preparation", "background", "restatement",
                  "summary")
SUBJECT_MATTER = ("elaboration", "interpretation", "evaluation",
                  "circumstance", "purpose", "solutionhood")
MULTINUCLEAR = ("contrast", "sequence", "list", "joint")
SPECIAL = ("nucleus", "split")
RELATIONS = frozenset(PRESENTATIONAL + SUBJECT_MATTER + MULTINUCLEAR + SPECIAL)

# Both bang spellings, as span_locks and md_paragraphs both tolerate.
MARKER = re.compile(
    r"^\s*<\\?!--\s*rst:\s*"
    r"(?P<relation>[a-z-]+)"
    r"(?:\s*->\s*(?P<target>\d+))?"
    r"\s*\|\s*(?P<gloss>.*?)\s*-->\s*$")

MARKER_FMT = "<!-- rst: {relation}{arrow} | {gloss} -->"


class RstError(ValueError):
    """A malformed marker or an unwritable insertion."""


class Problem:
    """One structural violation, with the line it is on."""

    __slots__ = ("kind", "line", "detail")

    def __init__(self, kind, line, detail):
        self.kind, self.line, self.detail = kind, line, detail

    def to_dict(self):
        return {"kind": self.kind, "line": self.line, "detail": self.detail}

    def __repr__(self):
        return f"L{self.line} {self.kind}: {self.detail}"


class Unit:
    """A heading or prose paragraph, with the marker above it if any.

    `position` is the 1-indexed paragraph number within the section, which is
    what a `-> n` target names. Headings carry position 0: a heading's own
    marker points at the article thesis, never at a paragraph.
    """

    __slots__ = ("kind", "line", "end_line", "text", "section", "position",
                 "relation", "target", "gloss", "marker_line")

    def __init__(self, kind, line, end_line, text, section, position):
        self.kind, self.line, self.end_line = kind, line, end_line
        self.text, self.section, self.position = text, section, position
        self.relation = self.target = self.gloss = self.marker_line = None

    @property
    def labelled(self):
        return self.relation is not None

    def to_dict(self):
        return {"kind": self.kind, "line": self.line, "section": self.section,
                "position": self.position, "relation": self.relation,
                "target": self.target, "gloss": self.gloss,
                "marker_line": self.marker_line}


class Outline:
    """Every unit of a document, its markers, and any malformed marker lines."""

    def __init__(self, path, lines, units, errors):
        self.path, self.lines, self.units, self.errors = path, lines, units, errors

    @property
    def paragraphs(self):
        return [u for u in self.units if u.kind == "paragraph"]

    @property
    def sections(self):
        out = {}
        for u in self.units:
            out.setdefault(u.section, []).append(u)
        return out

    def nucleus_of(self, section):
        for u in self.sections.get(section, []):
            if u.kind == "paragraph" and u.relation == "nucleus":
                return u
        return None

    def depth(self, unit):
        """Hops from `unit` to its section nucleus.

        0 for the nucleus itself. None when the chain does not reach one —
        a cycle or a dangling target, both of which `check` reports, so
        rank.py can sort them to the top rather than crash on them.
        """
        if unit.kind != "paragraph" or not unit.labelled:
            return None
        if unit.relation == "nucleus":
            return 0
        by_pos = {u.position: u for u in self.sections.get(unit.section, [])
                  if u.kind == "paragraph"}
        seen, cur, hops = set(), unit, 0
        while True:
            if cur.position in seen:
                return None                     # cycle
            seen.add(cur.position)
            if cur.target is None:
                return hops + 1 if self.nucleus_of(unit.section) else None
            nxt = by_pos.get(cur.target)
            if nxt is None:
                return None                     # dangling
            hops += 1
            if nxt.relation == "nucleus":
                return hops
            cur = nxt
            if hops > len(by_pos):
                return None                     # belt and braces


def _section_titles(lines, coverage):
    """Map every body line to the heading that governs it."""
    out, current = {}, None
    for ln in sorted(coverage):
        if coverage[ln] == "heading":
            current = lines[ln - 1].lstrip("#").strip()
        out[ln] = current
    return out


def parse(path):
    """Read a document into an Outline.

    Units come from the shared extractor, so what counts as a paragraph here
    is what counts as one everywhere else in the pipeline. A marker is bound
    to a unit when it sits on the nearest non-blank line above it.
    """
    doc = prose_document.ProseDocument.open(path)
    result = doc.to_parse_result()
    lines = result.lines
    sections = _section_titles(lines, result.coverage)

    units, errors = [], []
    per_section = {}
    for ln in sorted(result.coverage):
        if result.coverage[ln] != "heading":
            continue
        title = lines[ln - 1].lstrip("#").strip()
        units.append(Unit("heading", ln, ln, title, title, 0))
    for start, end, text in result.paragraphs:
        section = sections.get(start)
        per_section[section] = per_section.get(section, 0) + 1
        units.append(Unit("paragraph", start, end, text, section,
                          per_section[section]))
    units.sort(key=lambda u: u.line)

    # Bind markers. A paragraph's marker is the nearest non-blank line above
    # it; a heading's is the nearest non-blank line BELOW it. That asymmetry
    # is how the markers read on the page: a marker above a heading sits at
    # the end of the previous section and looks like it belongs there.
    claimed = set()
    for u in units:
        if u.kind == "heading":
            ln = u.line + 1
            while ln <= len(lines) and lines[ln - 1].strip() == "":
                ln += 1
            if ln > len(lines):
                continue
        else:
            ln = u.line - 1
            while ln >= 1 and lines[ln - 1].strip() == "":
                ln -= 1
            if ln < 1:
                continue
        if ln in claimed:
            continue
        m = MARKER.match(lines[ln - 1])
        if not m:
            continue
        u.relation = m.group("relation")
        u.target = int(m.group("target")) if m.group("target") else None
        u.gloss = m.group("gloss")
        u.marker_line = ln
        claimed.add(ln)

    # Any rst-shaped line not bound to a unit is a marker in the wrong place,
    # which is a silent no-op unless it is reported.
    for ln, raw in enumerate(lines, 1):
        if ln in claimed:
            continue
        if re.match(r"^\s*<\\?!--\s*rst:", raw):
            errors.append(Problem(
                "orphan-marker", ln,
                "marker is not immediately above a heading or prose paragraph"))
    return Outline(path, lines, units, errors)


def check(outline):
    """Every structural violation, in line order.

    Fails closed the way span_locks does: a document whose argument map is
    broken must not rank quietly, because the ranking is what an author cuts
    from.
    """
    problems = list(outline.errors)

    for u in outline.units:
        if not u.labelled:
            problems.append(Problem(
                "unlabelled", u.line,
                f"{u.kind} has no rst marker"))
            continue
        if u.relation not in RELATIONS:
            problems.append(Problem(
                "unknown-relation", u.marker_line,
                f"'{u.relation}' is not in the relation set"))
        if not (u.gloss or "").strip():
            problems.append(Problem(
                "empty-gloss", u.marker_line,
                "marker has no one-line description"))
        if u.kind == "heading" and u.target is not None:
            problems.append(Problem(
                "heading-target", u.marker_line,
                "a heading's marker relates the section to the thesis and "
                "takes no -> target"))
        if u.kind == "paragraph" and u.relation == "nucleus" and u.target is not None:
            problems.append(Problem(
                "nucleus-target", u.marker_line,
                "the nucleus is what the section depends on and takes no "
                "-> target"))

    for section, members in outline.sections.items():
        paras = [u for u in members if u.kind == "paragraph"]
        if not paras:
            continue
        nuclei = [u for u in paras if u.relation == "nucleus"]
        where = paras[0].line
        if not nuclei:
            problems.append(Problem(
                "no-nucleus", where,
                f"section {section!r} has no nucleus"))
        elif len(nuclei) > 1:
            for extra in nuclei[1:]:
                problems.append(Problem(
                    "two-nuclei", extra.marker_line or extra.line,
                    f"section {section!r} already has a nucleus at line "
                    f"{nuclei[0].line}; a section depends on one paragraph"))
        positions = {u.position for u in paras}
        for u in paras:
            if u.target is None:
                continue
            if u.target not in positions:
                problems.append(Problem(
                    "dangling-target", u.marker_line,
                    f"-> {u.target} does not exist in section {section!r}"))
            elif u.target == u.position:
                problems.append(Problem(
                    "self-target", u.marker_line,
                    f"-> {u.target} points at itself"))
        for u in paras:
            if u.labelled and u.relation != "nucleus" and outline.depth(u) is None:
                if not any(p.line == u.marker_line for p in problems):
                    problems.append(Problem(
                        "cycle", u.marker_line,
                        f"the -> chain from paragraph {u.position} never "
                        f"reaches the nucleus of section {section!r}"))

    problems.sort(key=lambda p: (p.line, p.kind))
    return problems


def strip(text):
    """Remove every rst marker line, and nothing else.

    Other comments — locks, subscribe blocks — are somebody else's and stay.
    """
    keep = [l for l in text.split("\n")
            if not re.match(r"^\s*<\\?!--\s*rst:.*-->\s*$", l)]
    return "\n".join(keep)


def _render(relation, target, gloss):
    arrow = f" -> {target}" if target else ""
    return MARKER_FMT.format(relation=relation, arrow=arrow, gloss=gloss)


def insert(path, by_line):
    """Write markers above their units. `by_line` maps a unit's start line to
    (relation, target, gloss). Returns the new text; does not save.

    Refuses to write inside a locked span: the lock's bytes are the author's,
    and a marker pushed between its markers would change them.
    """
    doc = prose_document.ProseDocument.open(path)
    lines = list(doc.to_parse_result().lines)
    locked = set()
    for start, end in doc.lock_report()["block_ranges"]:
        locked.update(range(start, end + 1))
    for ln in sorted(by_line, reverse=True):
        if ln in locked:
            raise RstError(f"refusing to write a marker inside the locked "
                           f"span at line {ln}")
        relation, target, gloss = by_line[ln]
        if relation not in RELATIONS:
            raise RstError(f"'{relation}' is not in the relation set")
        indent = re.match(r"^\s*", lines[ln - 1]).group(0)
        at = ln if lines[ln - 1].lstrip().startswith("#") else ln - 1
        lines.insert(at, indent + _render(relation, target, gloss))
    return "\n".join(lines)


def renumber(path, against=None):
    """Repair `-> n` targets after the author added or removed paragraphs.

    With `against` — the pre-edit version of the same document — targets are
    repaired by a real diff: paragraphs are matched between the two versions
    by their marker gloss, which the author does not edit when adding or
    deleting a neighbour, and each target is rewritten to wherever its
    referent now sits. A referent that is gone cannot be inferred, so it is
    reported for the author to answer rather than guessed at.

    Without `against`, position arithmetic is all there is, and it can only
    catch a target that now points outside its section. A target that is
    merely pointing at the WRONG paragraph still looks valid, which is why
    the reference version is the supported path; `check` reports the
    self-target case that a shift most often produces.
    """
    outline = parse(path)
    lines = list(outline.lines)
    problems = []

    if against is not None:
        old_outline = parse(against)
        for section, members in old_outline.sections.items():
            old_paras = [u for u in members if u.kind == "paragraph"]
            new_paras = [u for u in outline.sections.get(section, [])
                         if u.kind == "paragraph"]
            # gloss -> position, in each version. The gloss is the identity a
            # position is not.
            old_at = {u.position: (u.gloss or "") for u in old_paras}
            new_pos = {(u.gloss or ""): u.position for u in new_paras}
            current = {u.position: u for u in new_paras}
            for u in old_paras:
                if u.target is None:
                    continue
                here = new_pos.get(u.gloss or "")
                if here is None:
                    continue                      # this paragraph itself went
                live = current.get(here)
                if live is None or live.marker_line is None:
                    continue
                wanted_gloss = old_at.get(u.target)
                moved_to = new_pos.get(wanted_gloss or "")
                if moved_to is None:
                    problems.append(Problem(
                        "target-deleted", live.marker_line,
                        f"-> {u.target} referred to a paragraph that is no "
                        f"longer in section {section!r}; the author has to "
                        f"say what it should attach to"))
                    continue
                if moved_to != live.target:
                    problems.append(Problem(
                        "renumbered", live.marker_line,
                        f"-> {live.target} repaired to -> {moved_to}"))
                    lines[live.marker_line - 1] = re.sub(
                        r"->\s*\d+", f"-> {moved_to}",
                        lines[live.marker_line - 1], count=1)
        problems.sort(key=lambda p: (p.line, p.kind))
        return "\n".join(lines), problems

    for section, members in outline.sections.items():
        paras = [u for u in members if u.kind == "paragraph"]
        live = {u.position for u in paras}
        for u in paras:
            if u.target is None or u.marker_line is None or u.target in live:
                continue
            shifted = u.target - 1
            while shifted > 0 and shifted not in live:
                shifted -= 1
            if shifted <= 0:
                problems.append(Problem(
                    "target-deleted", u.marker_line,
                    f"-> {u.target} points outside section {section!r} and "
                    f"no earlier paragraph is available to fall back to"))
                continue
            problems.append(Problem(
                "renumbered", u.marker_line,
                f"-> {u.target} repaired to -> {shifted}"))
            lines[u.marker_line - 1] = re.sub(
                r"->\s*\d+", f"-> {shifted}", lines[u.marker_line - 1], count=1)
    problems.sort(key=lambda p: (p.line, p.kind))
    return "\n".join(lines), problems


def _report(problems, as_json):
    if as_json:
        print(json.dumps([p.to_dict() for p in problems], indent=2))
    else:
        for p in problems:
            print(f"  L{p.line:<5} {p.kind}: {p.detail}")


def main():
    ap = argparse.ArgumentParser(
        description="parse, validate, and repair reverse-outline rst markers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="list units and their markers")
    p_parse.add_argument("file")
    p_parse.add_argument("--json", action="store_true")

    p_check = sub.add_parser("check", help="validate the marker tree")
    p_check.add_argument("file")
    p_check.add_argument("--renumber", action="store_true",
                         help="repair -> targets after paragraphs moved")
    p_check.add_argument("--against", metavar="FILE",
                         help="the pre-edit version, for an exact renumber "
                              "diff; without it only out-of-range targets "
                              "can be repaired")
    p_check.add_argument("--in-place", action="store_true",
                         help="with --renumber, write the repair back")
    p_check.add_argument("--json", action="store_true")

    p_strip = sub.add_parser("strip", help="remove every rst marker")
    p_strip.add_argument("file")
    p_strip.add_argument("--in-place", action="store_true")

    a = ap.parse_args()

    if a.cmd == "parse":
        o = parse(a.file)
        if a.json:
            print(json.dumps({"file": a.file,
                              "units": [u.to_dict() for u in o.units],
                              "errors": [p.to_dict() for p in o.errors]},
                             indent=2))
        else:
            for u in o.units:
                d = o.depth(u)
                tag = u.relation or "UNLABELLED"
                arrow = f" -> {u.target}" if u.target else ""
                depth = "" if d is None else f" d{d}"
                print(f"  L{u.line:<5} {u.kind:<9} p{u.position:<3} "
                      f"{tag}{arrow}{depth}  {u.gloss or ''}")
        sys.exit(1 if o.errors else 0)

    if a.cmd == "check":
        if a.renumber:
            text, problems = renumber(a.file, a.against)
            if a.in_place:
                with open(a.file, "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                sys.stdout.write(text)
            _report(problems, a.json)
            sys.exit(1 if any(p.kind == "target-deleted" for p in problems) else 0)
        problems = check(parse(a.file))
        if not problems:
            print(f"{a.file}: marker tree valid")
            sys.exit(0)
        print(f"{a.file}: {len(problems)} problem(s)", file=sys.stderr)
        _report(problems, a.json)
        sys.exit(1)

    if a.cmd == "strip":
        with open(a.file, encoding="utf-8") as f:
            out = strip(f.read())
        if a.in_place:
            with open(a.file, "w", encoding="utf-8") as f:
                f.write(out)
        else:
            sys.stdout.write(out)
        sys.exit(0)


if __name__ == "__main__":
    main()
