#!/usr/bin/env python3
"""The deletion sheet for reverse-outline (GH-88).

Deterministic from the markers alone — no model call. `annotate` decides what
each paragraph does; this only orders what is already written down, which is
why the same document always produces the same sheet and why the author can
argue with it.

Four sections, in the order an author reads them:

  1. the reverse outline   the one-liners in document order, which read
                           together should tell the article's story
  2. deletion candidates   depth descending, then cut order, `joint` first
  3. repetition pairs      same relation, same target, near-duplicate glosses
  4. split paragraphs      the monster-paragraph list, rewrite candidates

Nothing is deleted and nothing is rewritten. The author picks by paragraph
number and the picks go in as an author-directed cycle.

CLI:
  rank.py <file.md> [--out <sheet.md>] [--json]
"""

import argparse
import difflib
import json
import os
import re
import sys

SK = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
for _d in (SHARED, SK):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import rst_markers as rm                                    # noqa: E402

# The cut order from references/relations.md, which is where it is derived and
# where the judgment call is flagged. Rank 1 goes first; a relation absent
# here is multinuclear or the nucleus, and is not a satellite to be cut.
CUT_ORDER = {
    "joint": 1,
    "restatement": 2, "summary": 2,
    "elaboration": 3,
    "evaluation": 4, "interpretation": 4,
    "background": 5, "preparation": 5, "circumstance": 5,
    "purpose": 6, "solutionhood": 6,
    "motivation": 7, "justify": 7,
    "evidence": 8, "concession": 8, "antithesis": 8,
}
# Each span of a multinuclear relation carries content of its own, so they are
# not ranked as satellites; `nucleus` is the section, and `split` is a rewrite.
NOT_CANDIDATES = frozenset(("nucleus", "split", "contrast", "sequence", "list"))

# Near-duplicate glosses. The same ratio critic-panel's converge.py uses for
# the same job — deciding whether two one-liners say the same thing.
SIMILARITY = 0.72


def _norm(s):
    return " ".join((s or "").lower().split())


def candidates(outline):
    """Deletion candidates, worst first.

    Sort key: depth descending (furthest from the point goes first), then cut
    rank ascending, then document order. Document order last so the sheet is
    reproducible — two paragraphs identical on the first two keys must not
    swap between runs.

    `joint` outranks depth. Everything else is a satellite that supports
    something, and depth says how far that support sits from the point;
    `joint` says no relation holds at all, so the argument never reaches the
    paragraph. That is a stronger signal than distance, and GH-88 lists it
    ahead of the depth ordering rather than inside it.

    A paragraph whose depth cannot be computed — a cycle, a dangling target —
    sorts above even that rather than being dropped. `check` has already told
    the author the tree is broken; the ranking should not also hide the
    paragraph that broke it.
    """
    out = []
    for u in outline.paragraphs:
        if not u.labelled or u.relation in NOT_CANDIDATES:
            continue
        rank = CUT_ORDER.get(u.relation)
        if rank is None:
            continue
        depth = outline.depth(u)
        out.append({
            "position": u.position, "line": u.line, "section": u.section,
            "relation": u.relation, "target": u.target, "gloss": u.gloss,
            "depth": depth, "cut_rank": rank,
            "broken": depth is None,
        })
    out.sort(key=lambda c: (0 if c["broken"] else 1,
                            0 if c["relation"] == "joint" else 1,
                            -(c["depth"] or 0), c["cut_rank"], c["line"]))
    return out


def sections(outline):
    """Sections ranked against the thesis, by their heading's own marker."""
    out = []
    for u in outline.units:
        if u.kind != "heading" or not u.labelled:
            continue
        rank = CUT_ORDER.get(u.relation)
        if u.relation in NOT_CANDIDATES or rank is None:
            continue
        out.append({"line": u.line, "section": u.section,
                    "relation": u.relation, "gloss": u.gloss,
                    "cut_rank": rank,
                    "paragraphs": len([p for p in outline.paragraphs
                                       if p.section == u.section])})
    out.sort(key=lambda s: (s["cut_rank"], s["line"]))
    return out


def repetitions(outline, threshold=SIMILARITY):
    """Pairs saying the same thing about the same target.

    Same section, same relation, same target, and glosses that a sequence
    matcher cannot tell apart. Two paragraphs doing one job is the finding;
    which of them to keep is the author's.
    """
    pairs = []
    paras = [u for u in outline.paragraphs if u.labelled]
    for i, a in enumerate(paras):
        for b in paras[i + 1:]:
            if (a.section, a.relation, a.target) != (b.section, b.relation, b.target):
                continue
            ratio = difflib.SequenceMatcher(
                None, _norm(a.gloss), _norm(b.gloss)).ratio()
            if ratio >= threshold:
                pairs.append({"a": a.position, "b": b.position,
                              "a_line": a.line, "b_line": b.line,
                              "section": a.section, "relation": a.relation,
                              "ratio": round(ratio, 3),
                              "a_gloss": a.gloss, "b_gloss": b.gloss})
    pairs.sort(key=lambda p: (-p["ratio"], p["a_line"]))
    return pairs


def splits(outline):
    return [{"position": u.position, "line": u.line, "section": u.section,
             "gloss": u.gloss}
            for u in outline.paragraphs if u.relation == "split"]


def thesis_of(outline):
    """The front-matter `thesis:` line, or None."""
    for raw in outline.lines[:40]:
        m = re.match(r"^thesis:\s*(.+?)\s*$", raw)
        if m:
            return m.group(1)
    return None


def build(outline):
    return {
        "file": outline.path,
        "thesis": thesis_of(outline),
        "outline": [{"kind": u.kind, "position": u.position, "line": u.line,
                     "section": u.section, "relation": u.relation,
                     "target": u.target, "gloss": u.gloss,
                     "depth": outline.depth(u)}
                    for u in outline.units],
        "candidates": candidates(outline),
        "sections": sections(outline),
        "repetitions": repetitions(outline),
        "splits": splits(outline),
    }


def render(sheet):
    o = ["# Reverse outline: " + os.path.basename(sheet["file"]), ""]
    o += ["Read-only. Nothing here has been cut. Pick by paragraph number; the",
          "picks go in as an author-directed cycle.", ""]
    if sheet["thesis"]:
        o += ["**Thesis.** " + sheet["thesis"], ""]
    else:
        o += ["**No `thesis:` line.** Section ranking is against nothing, so "
              "read part 2's section table with that in mind.", ""]

    o += ["## 1. The outline", "",
          "The one-liners in order. Read together they should tell the "
          "article's story; where they do not, the article does not either.", ""]
    for u in sheet["outline"]:
        if u["kind"] == "heading":
            o += ["", f"### {u['section']}  ·  _{u['relation']}_ — {u['gloss']}", ""]
            continue
        d = "" if u["depth"] is None else f"d{u['depth']}"
        arrow = f" -> {u['target']}" if u["target"] else ""
        o.append(f"{u['position']:>3}. `{u['relation']}{arrow}` {d:>3}  {u['gloss']}")

    o += ["", "## 2. Deletion candidates", "",
          "Furthest from the point first, then by what the relation costs to "
          "lose. Cutting stops being cheap around rank 6.", "",
          "| # | line | depth | relation | section | what it does |",
          "|---|---|---|---|---|---|"]
    for c in sheet["candidates"]:
        d = "—" if c["broken"] else c["depth"]
        o.append(f"| {c['position']} | {c['line']} | {d} | `{c['relation']}` | "
                 f"{c['section'] or '—'} | {c['gloss']} |")
    if not sheet["candidates"]:
        o.append("| — | — | — | — | — | nothing is a satellite; every "
                 "paragraph carries its own content |")

    if sheet["sections"]:
        o += ["", "### Sections, against the thesis", "",
              "| section | relation | paragraphs | what it does |",
              "|---|---|---|---|"]
        for s in sheet["sections"]:
            o.append(f"| {s['section']} | `{s['relation']}` | "
                     f"{s['paragraphs']} | {s['gloss']} |")

    o += ["", "## 3. Repetition pairs", ""]
    if sheet["repetitions"]:
        o += ["Same relation, same target, and the one-liners cannot be told "
              "apart. Two paragraphs doing one job; which one stays is yours.", "",
              "| a | b | similarity | relation | what they both say |",
              "|---|---|---|---|---|"]
        for p in sheet["repetitions"]:
            o.append(f"| {p['a']} (L{p['a_line']}) | {p['b']} (L{p['b_line']}) | "
                     f"{p['ratio']} | `{p['relation']}` | {p['a_gloss']} |")
    else:
        o.append("None.")

    o += ["", "## 4. Paragraphs to split", ""]
    if sheet["splits"]:
        o += ["The labeller could not state one function for these, which "
              "means they do more than one thing. Rewrite candidates, not "
              "deletions.", ""]
        for s in sheet["splits"]:
            o.append(f"- **{s['position']}** (L{s['line']}) — {s['gloss']}")
    else:
        o.append("None.")
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="rank paragraphs and sections by what deletion would cost")
    ap.add_argument("file")
    ap.add_argument("--out", help="sheet path (default: <stem>.outline.md)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    outline = rm.parse(a.file)
    problems = rm.check(outline)
    if problems:
        print(f"{a.file}: {len(problems)} marker problem(s); the ranking below "
              f"is only as good as the tree", file=sys.stderr)
        for p in problems:
            print(f"  L{p.line:<5} {p.kind}: {p.detail}", file=sys.stderr)

    sheet = build(outline)
    if a.json:
        print(json.dumps(sheet, indent=2))
        sys.exit(0)

    out = a.out or (os.path.splitext(a.file)[0] + ".outline.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(sheet))
    print(f"sheet: {out}")
    print(f"  {len(sheet['candidates'])} deletion candidate(s), "
          f"{len(sheet['repetitions'])} repetition pair(s), "
          f"{len(sheet['splits'])} to split")
    sys.exit(0)


if __name__ == "__main__":
    main()
