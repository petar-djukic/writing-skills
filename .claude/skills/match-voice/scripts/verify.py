#!/usr/bin/env python3
"""Verification gate for match-voice. Fails closed.

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
  markup     inline emphasis, code spans, and markdown links must survive in
             the same count, and a leading emphasis span must still lead
             (GH-232). The model reads "**The context stays clean.** An
             autonomous loop..." as prose and returns a plain declarative
             sentence: every number and citation survives, and the section's
             visual structure does not. Drift runs both ways (GH-83): of 34
             paragraphs a cold review reverted, 7 were the model adding bold
             or italic the original never had, and one turned "[text](url)"
             into a bare parenthetical URL. Any count that moves is fatal.
  dashes     the rewrite may not add em-dashes the original lacked — the
             cheapest way for a model to fake punch (GH-243)
  similarity n-gram overlap against the anchor passages, so the model does not
             simply copy the exemplars (reuses match-structure's shingle guard).
             Advisory (warn) — logged, never blocks acceptance.
  must-preserve  exact phrases that must survive rewriting unchanged (GH-362);
             loss is fatal. For spec YAML: claims-integrity markers whose
             presence the repo's audit greps for.
  protected-term  the article's referent chain (GH-77): a term from the
             protected list present in the original and missing from the
             rewrite is fatal. Whole-word, case-insensitive, plural-tolerant.
  ascii      typographic unicode (curly quotes, non-breaking hyphens/spaces) is
             normalized to ASCII before any check runs (GH-362), so the gate
             diffs like-for-like and a rewrite that reintroduces them is caught.

Findings are the verdict: each carries {"check", "severity", "detail"}, and
a check name means "this failed" only there. The top-level "markup",
"dashes", and "similarity" keys are measurements, present whether or not
anything failed — callers classify with checks_in(), never by searching the
JSON text (GH-84).

Exit: 0 clean, 1 violations (the loop retries or keeps the original), 2 usage.

Usage:
  verify.py --original <file> --rewrite <file> [--anchors-json <file>]
            [--max-shared-run 8] [--must-preserve <phrase>...]
            [--protected-terms <file>] [--json]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import protected_terms as _pt  # noqa: E402

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

# Typographic unicode that models reintroduce even after cleanup (GH-360).
# Maps each to its ASCII equivalent for pre-gate normalization.
_TYPO_MAP = str.maketrans({
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',   # curly double quotes
    "‐": "-", "‑": "-",   # hyphens (non-breaking, figure)
    "‒": "-", "–": "-",   # figure dash, en-dash
    "­": "",                    # soft hyphen
    " ": " ",                   # non-breaking space
    " ": " ",                   # narrow non-breaking space
    " ": " ",                   # thin space
})


def normalize_ascii(text):
    """Replace typographic unicode with ASCII equivalents."""
    return text.translate(_TYPO_MAP)

# Inline markup, stripped in this order so a span is counted once: code spans
# first (their contents are literal and may hold asterisks), then bold, then
# italic on what is left. Underscore italic requires non-word neighbours, or
# every snake_case identifier reads as emphasis.
CODE_SPAN = re.compile(r"`+[^`\n]+`+")
BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
ITALIC_STAR = re.compile(r"(?<!\*)\*(?=\S)([^*\n]+)(?<=\S)\*(?!\*)")
ITALIC_USCORE = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+)(?<=\S)_(?![\w_])")
# A leading span is emphasis that opens the paragraph — the bold lead-in whose
# loss GH-232 measured. Matched on the stripped paragraph, so leading
# whitespace does not decide it.
LEADING_EMPHASIS = re.compile(r"^\s*(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
# A markdown link, counted after code spans and before emphasis: the link is
# replaced by its text so emphasis inside "[**x**](u)" still counts once, and
# the URL's underscores and asterisks never read as italic. A pandoc citation
# "[@key]" has no "(...)" after it and does not match.
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")

MARKUP_KINDS = (("code", "inline code"), ("bold", "bold"),
                ("italic", "italic"), ("link", "markdown link"))


def _markup_spans(text):
    """Counts of inline code, link, bold, and italic spans, counted once each."""
    without_code, n_code = CODE_SPAN.subn(" ", text)
    without_link, n_link = LINK.subn(r"\1", without_code)
    without_bold, n_bold = BOLD.subn(" ", without_link)
    n_italic = (len(ITALIC_STAR.findall(without_bold))
                + len(ITALIC_USCORE.findall(without_bold)))
    return {"code": n_code, "bold": n_bold, "italic": n_italic, "link": n_link}


# Em-dash and its spaced-hyphen equivalent. A dash the original did not have is
# manufactured punch (GH-243): measured at 7 -> 10 and 7 -> 15 across two
# articles, against a house limit of 2.0 per 500 words. Counted outside code
# spans, where a double hyphen is a CLI flag rather than punctuation.
EM_DASH = re.compile(r"—|(?<=\s)--?(?=\s)")


def _dashes(text):
    return len(EM_DASH.findall(CODE_SPAN.sub(" ", text)))


def _citation_keys(text):
    """Counter of keys, ignoring which syntax carried them."""
    return Counter(k for k, _fam in _citation_pairs(text))


def _citation_pairs(text):
    r"""[(key, family)] where family is 'pandoc' or 'natbib'.

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


# GH-221: first-person pronouns, capitalized variants included, but never
# the country ("US" stays uppercase and the pattern requires a lowercase
# 's'). "I" matches only as the capital pronoun.
_FIRST_PERSON = re.compile(
    r"\bI\b|\b(?:[Mm]e|[Mm]y|[Mm]ine|[Mm]yself|[Ww]e|[Oo]ur(?:s|selves)?"
    r"|[Uu]s|[Oo]urselves)\b")
_URL = re.compile(r"https?://\S+")


def _first_person(text):
    return _FIRST_PERSON.search(_URL.sub(" ", _strip_citations(text)))


def _acronyms(text):
    return Counter(ACRONYM.findall(text))


def _similarity(rewrite_text, anchors_json, max_shared_run):
    """Longest verbatim run shared with any anchor (reuses match-structure)."""
    if not anchors_json or not os.path.exists(anchors_json):
        return None
    data = json.load(open(anchors_json))
    # retrieve.py --json emits a bare list; --no-anchors writes []. The dict
    # form {"anchors": [...]} is the other producer. Both are valid input.
    anchors = data if isinstance(data, list) else (data.get("anchors") or [])
    if not anchors:
        return None
    sibling = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "match-structure", "scripts"))
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


def checks_in(verdict, severity=None):
    """The set of check names a verdict's FINDINGS carry (GH-84).

    Accepts the dict verify() returns or the JSON text the CLI prints; an
    unparseable verdict yields an empty set, so a caller reading a crashed
    gate classifies nothing rather than everything.

    This exists because both drivers read the verdict by hand and both got
    it wrong in opposite directions. match_voice.py keyed findings on
    "type", which no finding has, so no specific retry note ever fired.
    drive.py substring-matched the raw JSON for '"markup"' and '"dashes"',
    which are TOP-LEVEL keys present in every verdict — so both notes fired
    on every retry regardless of cause, diluting the one note that was
    actually earned. Findings are the only place a check name means "this
    failed"; read them through here, never off the blob.

    severity=None counts every finding; pass "fatal" for the ones that
    block acceptance, "warn" for the advisory ones.
    """
    if isinstance(verdict, (str, bytes)):
        try:
            verdict = json.loads(verdict)
        except (json.JSONDecodeError, TypeError, ValueError):
            return set()
    if not isinstance(verdict, dict):
        return set()
    return {f.get("check", "") for f in verdict.get("findings", [])
            if isinstance(f, dict)
            and (severity is None or f.get("severity") == severity)} - {""}


def verify(original, rewritten, anchors_json=None, max_shared_run=8,
           must_preserve=None, protected_terms=None):
    rewritten = normalize_ascii(rewritten)
    findings = []

    # The referent chain is an article property the per-paragraph checks
    # below cannot see; the list carries it in (GH-77).
    for term in _pt.lost(original, rewritten, protected_terms or []):
        findings.append({"check": "protected-term", "severity": "fatal",
                         "detail": f"protected term lost: {term!r}"})

    if must_preserve:
        for phrase in must_preserve:
            if phrase in original and phrase not in rewritten:
                findings.append({"check": "must-preserve", "severity": "fatal",
                                 "detail": f"guard phrase lost: {phrase!r}"})

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

    # Markup is a contract like citation syntax: the content survives and the
    # rendering does not, so nothing else here notices. Both directions are
    # fatal. GH-240 let added emphasis through as a style question for the
    # reviewer; the GH-77 harness then measured that reviewer reverting 7 of
    # 34 paragraphs for exactly that, with nothing else wrong in several of
    # them. A count that moves either way goes back to the model with
    # MARKUP_NOTE instead of to a person.
    o_m, r_m = _markup_spans(original), _markup_spans(rewritten)
    for kind, label in MARKUP_KINDS:
        if r_m[kind] != o_m[kind]:
            verb = "lost" if r_m[kind] < o_m[kind] else "added"
            findings.append({"check": "markup", "severity": "fatal",
                             "detail": f"{label} span(s) {verb} "
                                       f"({o_m[kind]} in original, {r_m[kind]} "
                                       f"in rewrite)"})
    if LEADING_EMPHASIS.match(original) and not LEADING_EMPHASIS.match(rewritten):
        findings.append({"check": "markup", "severity": "fatal",
                         "detail": "the paragraph's leading emphasis span is "
                                   "gone; a bold lead-in carries the section's "
                                   "visual structure"})

    # An added em-dash is the most legible signal of "punch" a model has, and it
    # reaches for it when told to match a punchy register. Fatal rather than
    # advisory because the rewrite prompt now forbids it, so a dash here means a
    # stated constraint was ignored and one retry is cheap. Removing dashes is
    # fine — that direction is not the failure.
    o_d, r_d = _dashes(original), _dashes(rewritten)
    if r_d > o_d:
        findings.append({"check": "dashes", "severity": "fatal",
                         "detail": f"em-dash count rose {o_d} -> {r_d}; the "
                                   "rewrite manufactured punctuation the "
                                   "original did not have"})

    # A rewrite must not put claims in the author's mouth: an anchored seed
    # imports the anchor author's register, and first-person fabrication is
    # that import's worst case — measured live on the-qwerty-endpoint
    # (2026-09-01), where a Krugman-anchored pass invented "I might not
    # understand, being too thick-skulled..." in a paragraph whose original
    # had no first person at all, and the gate passed it. Original carrying
    # any first person keeps the check silent; rewrites reshuffle it
    # legitimately.
    if not _first_person(original):
        hit = _first_person(rewritten)
        if hit:
            findings.append({"check": "first-person-introduced",
                             "severity": "fatal",
                             "detail": f"first person ({hit.group(0)!r}) "
                                       "introduced into a paragraph whose "
                                       "original has none; the rewrite put "
                                       "words in the author's mouth"})

    o_a, r_a = _acronyms(original), _acronyms(rewritten)
    for term, n in o_a.items():
        if r_a.get(term, 0) < n:
            findings.append({"check": "terms", "severity": "warn",
                             "detail": f"technical term '{term}' dropped"})

    sim = _similarity(rewritten, anchors_json, max_shared_run)
    if sim and sim.get("violation"):
        findings.append({"check": "similarity", "severity": "warn",
                         "detail": f"{sim['longest_shared_run_words']}-word run copied "
                                   f"from an anchor (threshold {max_shared_run})"})

    return {
        "clean": not any(f["severity"] == "fatal" for f in findings),
        "findings": findings,
        "similarity": sim,
        "markup": {"original": o_m, "rewrite": r_m},
        "dashes": {"original": o_d, "rewrite": r_d},
        "note": "mechanical gate only — Claude must still judge bidirectional "
                "entailment and run the filter-tells lexical scan before splicing",
    }


def main():
    p = argparse.ArgumentParser(description="match-voice verification gate")
    p.add_argument("--original", required=True)
    p.add_argument("--rewrite", required=True)
    p.add_argument("--anchors-json", help="retrieve.py --json output, for the copy guard")
    p.add_argument("--max-shared-run", type=int, default=8,
                   help="longest verbatim run allowed against an anchor (words)")
    p.add_argument("--must-preserve", nargs="*", default=None,
                   help="exact phrases that must survive rewriting; loss is fatal")
    p.add_argument("--protected-terms", metavar="FILE",
                   help="protected-term list (protected_terms.py); a term "
                        "present in the original and lost in the rewrite is fatal")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    terms = _pt.read_terms(args.protected_terms) if args.protected_terms else None
    result = verify(open(args.original).read(), open(args.rewrite).read(),
                    args.anchors_json, args.max_shared_run,
                    must_preserve=args.must_preserve, protected_terms=terms)
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
