#!/usr/bin/env python3
"""Merge N critic reports into one sheet, convergence first (GH-75, GH-97).

Two report kinds, because a persona is either an adder or a diagnostician and
forcing one into the other's shape yields a line edit for a conceptual defect.

    ## Diagnosis          ## Diagnosis
    <prose>               <prose>
    ## Suggestions        ## Findings
    ### 1                 ### 1
    Original: <verbatim>  Passage: <verbatim>
    Replacement: <or CUT> Finding: <what is wrong>
    Buys: <one line>      Fix: <described, never written>
    ## Paragraph move     ## Verdict
    <prose>               <the persona's own verdict format>

    kind = suggest        kind = verdict

Both kinds store their verbatim field under `quote`, which is the only thing
grouping reads. That is what lets two diagnosticians quoting one passage
converge exactly as two adders targeting one sentence do — and lets a
diagnostician and an adder converge on the same passage — without a second
comparison path. Items whose quotes match (difflib ratio >= THRESHOLD after
whitespace/case normalization) are listed first: agreement between critics
who could not see each other is the signal the panel exists to produce.

A suggest-only run renders exactly what it rendered before GH-97, pinned by
scripts/testdata/panel2-golden-sheet.md — the sheet from the real Strategy
Theatre panel, byte for byte.
"""
import argparse
import difflib
import os
import re
import sys

THRESHOLD = 0.8


# The verbatim field each kind quotes, and the pair each renders as
# "what is wrong — what it buys". Adding a third kind means adding a row.
KINDS = {
    "suggest": {"section": "suggestions", "quote": "Original",
                "fields": ("Original", "Replacement", "Buys"),
                "required": ("Original", "Replacement"),
                "body": "Replacement", "why": "Buys"},
    "verdict": {"section": "findings", "quote": "Passage",
                "fields": ("Passage", "Finding", "Fix"),
                "required": ("Passage", "Finding"),
                "body": "Finding", "why": "Fix"},
}


def parse(path):
    """One report into a dict, kind detected from which section it carries.

    `## Findings` means a diagnostician wrote it, `## Suggestions` an adder.
    Both land in `items`, each item carrying `quote` — the verbatim text the
    critic is pointing at — so nothing downstream branches on kind to find
    what to group on.
    """
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    sect = {}
    for title, body in re.findall(r"^## +([^\n]+)\n(.*?)(?=^## |\Z)", text,
                                  re.S | re.M):
        sect[title.strip().lower()] = body.strip()

    kind = "verdict" if "findings" in sect else "suggest"
    spec = KINDS[kind]
    pattern = r"^(" + "|".join(spec["fields"]) + r"):\s*(.+?)\s*$"
    blocks = re.split(r"^### +\S+\s*$", sect.get(spec["section"], ""),
                      flags=re.M)[1:]
    items = []
    for block in blocks:
        fields = dict(re.findall(pattern, block, re.M))
        if all(f in fields for f in spec["required"]):
            items.append({"critic": name, "kind": kind,
                          "quote": fields[spec["quote"]], **fields})
    return {"critic": name, "kind": kind, "path": path,
            # What the file actually carried, so a refusal can name it rather
            # than guess. `kind` alone cannot: absent both headings it reads
            # "suggest" by default, which is the wrong thing to report.
            "sections": sorted(sect),
            "has_section": spec["section"] in sect,
            "blocks": len(blocks),
            "diagnosis": sect.get("diagnosis", ""),
            "move": sect.get("paragraph move", ""),
            "verdict": sect.get("verdict", ""),
            "items": items,
            # `suggestions` kept as the suggest-kind view; main() counts it
            # and callers predating GH-97 read it.
            "suggestions": [i for i in items if i["kind"] == "suggest"]}


def norm(s):
    return " ".join(s.lower().split())


def group(items_or_reports):
    """Items pointing at the same passage, across critics and across kinds."""
    groups = []
    for r in items_or_reports:
        for s in r["items"]:
            for g in groups:
                if difflib.SequenceMatcher(
                        None, norm(g[0]["quote"]),
                        norm(s["quote"])).ratio() >= THRESHOLD:
                    g.append(s)
                    break
            else:
                groups.append([s])
    return groups


def order(reports, roster):
    """Reports in roster order; anything unnamed keeps file order, last.

    Roster order is sheet order. The book roster's six critics were run in
    sequence before GH-97, to get clarity and honesty ahead of hook and story;
    ordering the rendering buys that reading without giving up the parallel
    fresh contexts that make convergence mean anything.
    """
    if not roster:
        return list(reports)
    rank = {n.strip().lower(): i for i, n in enumerate(roster) if n.strip()}
    return sorted(reports,
                  key=lambda r: (rank.get(r["critic"].lower(), len(rank)),))


def _body(s):
    """`what is wrong — why it matters`, in the item's own kind's words."""
    spec = KINDS[s["kind"]]
    return f"{s[spec['body']]} — *{s.get(spec['why'], '')}*"


def render(reports, groups):
    """The sheet.

    A suggest-only run renders exactly what it rendered before GH-97 — same
    headings, same wording, same order — because the golden fixture pins it.
    The verdict sections and the Summary appear only when a diagnostician is
    in the run, and the two headings that say "sentences" say "passages"
    instead, since a verdict critic quotes a passage rather than a line.
    """
    verdicts = [r for r in reports if r["kind"] == "verdict"]
    out = ["# Critic panel sheet", "",
           "Read-only. Nothing applied. Pick by critic and number.", ""]
    out += ["## Diagnoses", ""]
    for r in reports:
        out += [f"**{r['critic']}:** {r['diagnosis']}", ""]

    conv = [g for g in groups if len({s['critic'] for s in g}) > 1]
    solo = [g for g in groups if len({s['critic'] for s in g}) == 1]
    conv.sort(key=lambda g: -len(g))
    unit = "passage" if verdicts else "sentence"
    out += [f"## Convergent ({len(conv)} {unit}"
            f"{'' if len(conv) == 1 else 's'} targeted by 2+ critics)", ""]
    for g in conv:
        out += [f"### \"{g[0]['quote']}\"", ""]
        for s in g:
            out += [f"- **{s['critic']}:** {_body(s)}"]
        out += [""]

    heading = "findings" if verdicts else "suggestions"
    out += [f"## Single-critic {heading}", ""]
    for r in reports:
        mine = [g[0] for g in solo if g[0]["critic"] == r["critic"]]
        if not mine:
            continue
        out += [f"### {r['critic']}", ""]
        for i, s in enumerate(mine, 1):
            out += [f"{i}. \"{s['quote']}\" → {_body(s)}"]
        out += [""]

    moves = [r for r in reports if r["move"]]
    if moves:
        out += ["## Paragraph-level moves", ""]
        for r in moves:
            out += [f"**{r['critic']}:** {r['move']}", ""]

    if not verdicts:
        return "\n".join(out)

    out += ["## Verdicts", ""]
    for r in verdicts:
        out += [f"**{r['critic']}:** {r['verdict']}", ""]

    passed = [r["critic"] for r in verdicts if not r["items"]]
    failed = [r["critic"] for r in verdicts if r["items"]]
    out += ["## Summary", "",
            "**Pass**: " + (", ".join(passed) or "none"), "",
            "**Needs work**: " + (", ".join(failed) or "none"), ""]
    # Top fixes caps the rendered list, never the findings — everything above
    # is still in the sheet. Ranked by how many critics landed on the passage,
    # then by roster order, which `reports` already carries.
    rank = {r["critic"]: i for i, r in enumerate(reports)}
    top = sorted(conv, key=lambda g: (-len({s['critic'] for s in g}),
                                      min(rank.get(s["critic"], len(rank))
                                          for s in g)))
    if top:
        n = min(3, len(top))
        out += [f"**Top {n} fix{'' if n == 1 else 'es'}** "
                f"(in priority order):", ""]
        for i, g in enumerate(top[:3], 1):
            who = ", ".join(sorted({s["critic"] for s in g}, key=lambda c: rank.get(c, 0)))
            spec = KINDS[g[0]["kind"]]
            out += [f"{i}. \"{g[0]['quote']}\" — {g[0].get(spec['why'], '')} "
                    f"({who})"]
        out += [""]
    return "\n".join(out)


def unparseable(report):
    """Why this report yields nothing usable, or None when it is fine.

    Zero items is NOT the test, and getting that wrong would break the thing
    the book roster exists to report: `Pass` in the Summary block is precisely
    a verdict critic with no findings, so a report carrying `## Findings` with
    nothing under it is a clean result, not a fault (GH-97).

    What distinguishes a fault is the heading. The panel's first real run
    (GH-107) wrote `## Ten line-level suggestions` and `1. **Original:**`,
    matched nothing, and `converge.py` wrote a sheet anyway — three critics, 0
    suggestions, no complaint. The sheet a human actually used from that run
    was written by hand, and nothing recorded that the tool had contributed
    nothing.
    """
    if not report["has_section"]:
        seen = ", ".join(report["sections"]) or "no `## ` headings at all"
        return (f"no `## Suggestions` or `## Findings` section — found: {seen}. "
                f"The report format is fixed and machine-read; see the "
                f"critic-panel SKILL.md")
    if report["blocks"] and not report["items"]:
        spec = KINDS[report["kind"]]
        return (f"`## {spec['section'].title()}` has {report['blocks']} "
                f"`### n` block(s) but no parseable entry — each needs "
                f"{' and '.join(spec['required'])} on their own lines")
    return None


def refuse(reports):
    """Exit naming every unparseable report, not just the first.

    Refusing rather than warning: a sheet assembled from reports that parsed
    to nothing is worthless, and a warning on stderr is what nobody read the
    first time. Nothing is written — a partial sheet is the silent wrong
    answer wearing a different hat.
    """
    bad = [(r, why) for r in reports for why in [unparseable(r)] if why]
    if not bad:
        return
    lines = [f"converge: {len(bad)} of {len(reports)} report(s) parsed to "
             f"nothing; no sheet written"]
    for r, why in bad:
        lines.append(f"  {r['path']}")
        lines.append(f"    {why}")
    sys.exit("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--roster", help="comma-separated critic names; sets "
                                     "sheet order (default: file order)")
    a = ap.parse_args()
    reports = order([parse(p) for p in a.reports],
                    a.roster.split(",") if a.roster else None)
    refuse(reports)
    sheet = render(reports, group(reports))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(sheet)
    n = sum(len(r["items"]) for r in reports)
    kinds = {r["kind"] for r in reports}
    print(f"{a.out}: {len(reports)} critics, {n} "
          f"{'findings' if kinds == {'verdict'} else 'suggestions'}")


if __name__ == "__main__":
    main()
