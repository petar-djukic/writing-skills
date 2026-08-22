#!/usr/bin/env python3
"""Merge N critic reports into one sheet, convergence first (GH-75).

Each report is markdown in the fixed format the SKILL.md prescribes:

    ## Diagnosis
    <prose>
    ## Suggestions
    ### 1
    Original: <verbatim sentence>
    Replacement: <proposed sentence, or CUT>
    Buys: <one line>
    ...
    ## Paragraph move
    <prose>

Suggestions whose Original sentences match across critics (difflib ratio
>= THRESHOLD after whitespace/case normalization) are grouped as convergent
and listed first — agreement between independent critics is the signal.
"""
import argparse
import difflib
import os
import re

THRESHOLD = 0.8


def parse(path):
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    sect = {}
    for title, body in re.findall(r"^## +([^\n]+)\n(.*?)(?=^## |\Z)", text,
                                  re.S | re.M):
        sect[title.strip().lower()] = body.strip()
    sugg = []
    for block in re.split(r"^### +\S+\s*$", sect.get("suggestions", ""),
                          flags=re.M)[1:]:
        fields = dict(re.findall(r"^(Original|Replacement|Buys):\s*(.+?)\s*$",
                                 block, re.M))
        if "Original" in fields and "Replacement" in fields:
            sugg.append({"critic": name, **fields})
    return {"critic": name, "diagnosis": sect.get("diagnosis", ""),
            "move": sect.get("paragraph move", ""), "suggestions": sugg}


def norm(s):
    return " ".join(s.lower().split())


def group(reports):
    groups = []
    for r in reports:
        for s in r["suggestions"]:
            for g in groups:
                if difflib.SequenceMatcher(
                        None, norm(g[0]["Original"]),
                        norm(s["Original"])).ratio() >= THRESHOLD:
                    g.append(s)
                    break
            else:
                groups.append([s])
    return groups


def render(reports, groups):
    out = ["# Critic panel sheet", "",
           "Read-only. Nothing applied. Pick by critic and number.", ""]
    out += ["## Diagnoses", ""]
    for r in reports:
        out += [f"**{r['critic']}:** {r['diagnosis']}", ""]
    conv = [g for g in groups if len({s['critic'] for s in g}) > 1]
    solo = [g for g in groups if len({s['critic'] for s in g}) == 1]
    out += [f"## Convergent ({len(conv)} sentences targeted by 2+ critics)",
            ""]
    for g in sorted(conv, key=lambda g: -len(g)):
        out += [f"### \"{g[0]['Original']}\"", ""]
        for s in g:
            out += [f"- **{s['critic']}:** {s['Replacement']} — "
                    f"*{s.get('Buys', '')}*"]
        out += [""]
    out += ["## Single-critic suggestions", ""]
    for r in reports:
        mine = [g[0] for g in solo if g[0]["critic"] == r["critic"]]
        if not mine:
            continue
        out += [f"### {r['critic']}", ""]
        for i, s in enumerate(mine, 1):
            out += [f"{i}. \"{s['Original']}\" → {s['Replacement']} — "
                    f"*{s.get('Buys', '')}*"]
        out += [""]
    out += ["## Paragraph-level moves", ""]
    for r in reports:
        if r["move"]:
            out += [f"**{r['critic']}:** {r['move']}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    reports = [parse(p) for p in a.reports]
    sheet = render(reports, group(reports))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(sheet)
    n = sum(len(r["suggestions"]) for r in reports)
    print(f"{a.out}: {len(reports)} critics, {n} suggestions")


if __name__ == "__main__":
    main()
