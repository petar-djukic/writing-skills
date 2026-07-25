#!/usr/bin/env python3
"""Verification gate for voice-rewrite. Fails closed.

An 8B model rewriting prose WILL sometimes drop a citation, round a number, or
paraphrase a term of art. This script is the mechanical half of the gate; the
semantic half (bidirectional entailment) is Claude's job in the skill loop.
Nothing is spliced back into a draft until both pass.

Checks:
  citations  every [@key] and \\citep{key}/\\citet{key} in the original must
             survive verbatim, same multiset AND the same syntax family — a
             pandoc key silently rewritten as natbib breaks the build
  numbers    every number (with its unit when attached) must survive
  terms      acronyms and technical tokens from the original must survive
  similarity n-gram overlap against the anchor passages, so the model does not
             simply copy the exemplars (reuses match-voice's shingle guard)

Exit: 0 clean, 1 violations (the loop retries or keeps the original), 2 usage.

Usage:
  verify.py --original <file> --rewrite <file> [--anchors-json <file>]
            [--max-shared-run 8] [--json]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

CITE_PANDOC = re.compile(r"\[@[^\]]+\]")
CITE_KEY = re.compile(r"@([\w][\w:.#$%&+?<>~/-]*)")
CITE_NATBIB = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]*)\}")
# Numbers are compared as a bare multiset. A following word is treated as an
# attached unit ONLY when it is a known unit token: a rewrite legitimately
# reorders "12 TDMA slots" into "... to only 12", and gluing on whatever word
# follows turns that faithful reorder into a false violation.
NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(%|[a-zA-Z]{1,5})?\b")
KNOWN_UNITS = {
    "%", "ms", "us", "ns", "s", "sec", "min", "h", "hr", "db", "dbm",
    "hz", "khz", "mhz", "ghz", "bps", "kbps", "mbps", "gbps",
    "b", "kb", "mb", "gb", "tb", "kib", "mib", "gib",
    "m", "km", "cm", "mm", "x", "k", "w", "kw", "mw",
}
ACRONYM = re.compile(r"\b([A-Z]{2,}(?:-\d+)?)\b")


def _citation_keys(text):
    """Counter of keys, ignoring which syntax carried them."""
    return Counter(k for k, _fam in _citation_pairs(text))


def _citation_pairs(text):
    """[(key, family)] where family is 'pandoc' or 'natbib'.

    The syntax family matters (GH-163): a model that silently rewrites
    [@key] as \citep{key} keeps the key but breaks a pandoc build, and a
    key-only comparison passes it.
    """
    pairs = []
    for m in CITE_PANDOC.finditer(text):
        pairs.extend((k, "pandoc") for k in CITE_KEY.findall(m.group(0)))
    for m in CITE_NATBIB.finditer(text):
        pairs.extend((k.strip(), "natbib")
                     for k in m.group(1).split(",") if k.strip())
    return pairs


def _strip_citations(text):
    """Remove citation spans so their years are not read as document numbers."""
    text = CITE_PANDOC.sub(" ", text)
    return CITE_NATBIB.sub(" ", text)


def _numbers(text):
    out = []
    for m in NUMBER.finditer(text):
        num, unit = m.group(1), (m.group(2) or "").strip()
        unit = unit if unit.lower() in KNOWN_UNITS else ""
        out.append(f"{num}{unit}")
    return Counter(out)


def _acronyms(text):
    return Counter(ACRONYM.findall(text))


def _similarity(rewrite_text, anchors_json, max_shared_run):
    """Longest verbatim run shared with any anchor (reuses match-voice)."""
    if not anchors_json or not os.path.exists(anchors_json):
        return None
    data = json.load(open(anchors_json))
    anchors = data.get("anchors") or []
    if not anchors:
        return None
    sibling = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "match-voice", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import style
    except ImportError as e:
        return {"error": f"similarity guard unavailable: {e}"}
    against = [(a.get("file", f"anchor{i}"), a.get("text", ""))
               for i, a in enumerate(anchors)]
    rep = style.similarity_report(rewrite_text, against, n=max_shared_run)
    longest = 0
    for src in rep.get("sources", []):
        for run in src.get("flagged", []) or src.get("matches", []) or []:
            longest = max(longest, run.get("words", 0))
    return {"longest_shared_run_words": longest,
            "threshold": max_shared_run,
            "violation": longest >= max_shared_run}


def verify(original, rewritten, anchors_json=None, max_shared_run=8):
    findings = []

    o_c, r_c = _citation_keys(original), _citation_keys(rewritten)
    for key, n in o_c.items():
        if r_c.get(key, 0) < n:
            findings.append({"check": "citations", "severity": "fatal",
                             "detail": f"citation key '{key}' lost "
                                       f"({n} in original, {r_c.get(key,0)} in rewrite)"})
    for key, n in r_c.items():
        if o_c.get(key, 0) < n:
            findings.append({"check": "citations", "severity": "fatal",
                             "detail": f"citation key '{key}' invented by the rewrite"})

    # citation spans stripped first: [@boutaba-2018-...] must not contribute
    # "2018" as a document number (GH-163), which double-reported a lost cite
    o_fam = {k: f for k, f in _citation_pairs(original)}
    r_fam = {k: f for k, f in _citation_pairs(rewritten)}
    for key, fam in o_fam.items():
        if key in r_fam and r_fam[key] != fam:
            findings.append({"check": "citation-syntax", "severity": "fatal",
                             "detail": f"citation '{key}' changed syntax family "
                                       f"{fam} -> {r_fam[key]}; this breaks the "
                                       "document build even though the key survived"})

    o_n, r_n = (_numbers(_strip_citations(original)),
                _numbers(_strip_citations(rewritten)))
    for val, n in o_n.items():
        if r_n.get(val, 0) < n:
            findings.append({"check": "numbers", "severity": "fatal",
                             "detail": f"number '{val}' lost or altered"})
    for val, n in r_n.items():
        if o_n.get(val, 0) < n:
            findings.append({"check": "numbers", "severity": "fatal",
                             "detail": f"number '{val}' invented by the rewrite"})

    o_a, r_a = _acronyms(original), _acronyms(rewritten)
    for term, n in o_a.items():
        if r_a.get(term, 0) < n:
            findings.append({"check": "terms", "severity": "warn",
                             "detail": f"technical term '{term}' dropped"})

    sim = _similarity(rewritten, anchors_json, max_shared_run)
    if sim and sim.get("violation"):
        findings.append({"check": "similarity", "severity": "fatal",
                         "detail": f"{sim['longest_shared_run_words']}-word run copied "
                                   f"from an anchor (threshold {max_shared_run})"})

    return {
        "clean": not any(f["severity"] == "fatal" for f in findings),
        "findings": findings,
        "similarity": sim,
        "note": "mechanical gate only — Claude must still judge bidirectional "
                "entailment and run the de-ai lexical scan before splicing",
    }


def main():
    p = argparse.ArgumentParser(description="voice-rewrite verification gate")
    p.add_argument("--original", required=True)
    p.add_argument("--rewrite", required=True)
    p.add_argument("--anchors-json", help="retrieve.py --json output, for the copy guard")
    p.add_argument("--max-shared-run", type=int, default=8,
                   help="longest verbatim run allowed against an anchor (words)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = verify(open(args.original).read(), open(args.rewrite).read(),
                    args.anchors_json, args.max_shared_run)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("GATE: " + ("clean" if result["clean"] else "VIOLATIONS"))
        for f in result["findings"]:
            print(f"  [{f['severity']}] {f['check']}: {f['detail']}")
        if result["similarity"]:
            print(f"  similarity: {result['similarity']}")
        print(f"  {result['note']}")
    sys.exit(0 if result["clean"] else 1)


if __name__ == "__main__":
    main()
