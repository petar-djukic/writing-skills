#!/usr/bin/env python3
"""cold-review — fresh-context entailment check with a fixed contract
(GH-207): the mechanical half.

The review itself is a model in a fresh context (the prompt template in
references/review-prompt.md); this script is everything around it that
must be deterministic:

  screen   align baseline and candidate paragraph-by-paragraph and flag
           mechanical entailment drift — number multiset changes,
           citation changes, altered double-quoted spans — as revert
           candidates. The screen is a recall aid for the reviewer's
           high-value targets, not the review: an inverted claim with
           the same numbers passes it and only the model catches it.
  apply    apply an accepted revert list: each named candidate paragraph
           is swapped back to the baseline span VERBATIM. Every accepted
           fix is a revert — kept-original at paragraph level, no
           authored prose — and the invariants (locked spans, paragraph
           count) are re-checked on the written file.

The chain is paragraph-aligned by design (every driver rewrites 1:1), so
both subcommands require equal prose paragraph counts and refuse
otherwise — a count mismatch means a stage merged or split paragraphs
and index-based reverts would land on the wrong text.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
sys.path.insert(0, SHARED)
import md_paragraphs  # noqa: E402
import span_locks  # noqa: E402

NUM = re.compile(r"\d[\d,\.]*")
CITE = re.compile(r"\[@[^\]\s]+\]|\[\d{1,3}\]")
QUOTED = re.compile(r'"([^"]{4,})"')
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _number_contexts(text):
    """{(three preceding words, number)} — the association a swap breaks
    while leaving the multiset intact."""
    out = set()
    for m in NUM.finditer(text):
        words = WORD.findall(text[:m.start()])[-3:]
        out.add((" ".join(w.lower() for w in words), m.group(0)))
    return out


def _paras(path):
    text = open(path, encoding="utf-8").read()
    return text, md_paragraphs.parse(text).paragraphs


def _aligned(baseline, candidate):
    btext, bp = _paras(baseline)
    ctext, cp = _paras(candidate)
    if len(bp) != len(cp):
        sys.exit(f"paragraph counts differ: baseline {len(bp)}, candidate "
                 f"{len(cp)} — a stage merged or split paragraphs; align "
                 f"by hand before screening or reverting")
    return btext, bp, ctext, cp


def screen(baseline, candidate):
    """Revert candidates from mechanical drift, per aligned paragraph."""
    _bt, bp, _ct, cp = _aligned(baseline, candidate)
    findings = []
    for n, ((bs, be, b), (cs, ce, c)) in enumerate(zip(bp, cp), 1):
        drift = []
        b_masked, c_masked = CITE.sub(" ", b), CITE.sub(" ", c)
        bn, cn = sorted(NUM.findall(b_masked)), sorted(NUM.findall(c_masked))
        if bn != cn:
            gone = [x for x in bn if x not in cn]
            new = [x for x in cn if x not in bn]
            drift.append("numbers changed: "
                         f"lost {gone or 'none'}, gained {new or 'none'}")
        elif bn and _number_contexts(b_masked) != _number_contexts(c_masked):
            # Same digits, different claims — the planted-swap class the
            # 2026-09-01 run caught by hand (0.768/0.867 arm numbers).
            moved = sorted(x[1] for x in
                           _number_contexts(b_masked) ^
                           _number_contexts(c_masked))
            drift.append("numbers reattached to different claims: "
                         f"{sorted(set(moved))}")
        if sorted(CITE.findall(b)) != sorted(CITE.findall(c)):
            drift.append("citations changed")
        bq, cq = sorted(QUOTED.findall(b)), sorted(QUOTED.findall(c))
        if bq != cq:
            drift.append("double-quoted span altered")
        if drift:
            findings.append({"paragraph": n, "candidate_lines": [cs, ce],
                             "drift": drift, "baseline_excerpt": b[:80],
                             "candidate_excerpt": c[:80]})
    return findings


def apply_reverts(baseline, candidate, reverts, out):
    """Swap the named candidate paragraphs back to baseline text,
    verbatim, bottom-up; re-check invariants on the written bytes."""
    btext, bp, ctext, cp = _aligned(baseline, candidate)
    lines = ctext.split("\n")
    for n in sorted(reverts, reverse=True):
        if n < 1 or n > len(cp):
            sys.exit(f"revert paragraph {n} out of range (1..{len(cp)})")
        cs, ce, _c = cp[n - 1]
        _bs, _be, b = bp[n - 1]
        lines[cs - 1:ce] = b.split("\n")
    new_text = "\n".join(lines)
    open(out, "w", encoding="utf-8").write(new_text)

    # Invariants on what was written, not on the path that wrote it.
    _clean, manifest = span_locks.excise(btext)
    problems = [f"locked span lost: {span[:60]!r}"
                for span in span_locks.verify_preserved(
                    list(manifest.values()), new_text)]
    np = md_paragraphs.parse(new_text).paragraphs
    if len(np) != len(cp):
        problems.append(f"paragraph count changed: {len(cp)} -> {len(np)}")
    for n in reverts:
        if md_paragraphs.parse(new_text).paragraphs[n - 1][2] != bp[n - 1][2]:
            problems.append(f"paragraph {n} is not byte-identical to the "
                            f"baseline after revert")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("screen", help="mechanical drift -> revert candidates")
    sc.add_argument("--baseline", required=True)
    sc.add_argument("--candidate", required=True)
    sc.add_argument("--json", action="store_true")

    apl = sub.add_parser("apply", help="verbatim reverts by paragraph number")
    apl.add_argument("--baseline", required=True)
    apl.add_argument("--candidate", required=True)
    apl.add_argument("--revert", required=True,
                     help="1-based paragraph numbers, e.g. '3,7'")
    apl.add_argument("--out", required=True)

    a = ap.parse_args()
    if a.cmd == "screen":
        findings = screen(a.baseline, a.candidate)
        if a.json:
            print(json.dumps(findings, indent=2))
        else:
            if not findings:
                print("screen: no mechanical drift. The model review still "
                      "runs — an inverted claim carries the same numbers.")
            for f in findings:
                print(f"p{f['paragraph']:02d} "
                      f"L{f['candidate_lines'][0]}-{f['candidate_lines'][1]}:"
                      f" {'; '.join(f['drift'])}")
                print(f"    baseline : {f['baseline_excerpt']}")
                print(f"    candidate: {f['candidate_excerpt']}")
        return 1 if findings else 0

    reverts = {int(x) for x in a.revert.split(",") if x.strip()}
    problems = apply_reverts(a.baseline, a.candidate, reverts, a.out)
    print(f"reverted {len(reverts)} paragraph(s) -> {a.out}")
    if problems:
        for p in problems:
            print(f"INVARIANT: {p}", file=sys.stderr)
        return 3
    print("invariants: locked spans preserved, paragraph count stable, "
          "reverts byte-identical to baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
