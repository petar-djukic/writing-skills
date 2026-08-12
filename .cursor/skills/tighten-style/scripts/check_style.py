#!/usr/bin/env python3
"""Check prose against the style rules. Findings cite rule IDs.

Covers the layers a script can honestly carry — deterministic transforms,
lexical lists, and measured densities. The judgment rules (TS-06, TS-07,
TS-09, TS-11) are listed in references/style-rules.md and belong to the
reading pass; this script does not pretend to see them.

What it emits is a finding list, not an edit. Rewriting is the skill's job
under the density floor and the verify gate, because "shorter" is not the
target — the author's own measured density is, and a script cutting toward
maximal terseness manufactures the clipped register filter-tells exists to
catch.

Usage:
  check_style.py <file.md|file.tex> [--json] [--rule TS-01,TS-05]

Exit 0 clean, 1 findings, 2 usage error. Stdlib only.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _shared():
    d = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


def _stylometry():
    d = os.path.normpath(os.path.join(HERE, "..", "..", "match-structure", "scripts"))
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


# TS-01: phrases that announce rather than say. Value is the contraction.
NEEDLESS = {
    r"\bthe fact that\b": "usually deletable — 'the fact that he failed' → 'his failure'",
    r"\bin order to\b": "'to'",
    r"\bit should be noted that\b": "delete; note it by saying it",
    r"\bit is important to note that\b": "delete",
    r"\bthere (?:is|are|was|were)\s+\w+\s+(?:that|which)\b": "recast without the expletive",
    r"\bowing to the fact that\b": "'because'",
    r"\bdue to the fact that\b": "'because'",
    r"\bthe question as to whether\b": "'whether'",
    r"\bfor the purpose of\b": "'to'",
    r"\bin the event that\b": "'if'",
    r"\bat this point in time\b": "'now'",
    r"\bis able to\b": "'can'",
    r"\bhas the ability to\b": "'can'",
    r"\ba (?:number|variety) of\b": "say how many, or 'several'",
}

# TS-03: negation the reader must compute a complement for.
NEGATIVE_FORM = {
    r"\bdid not remember\b": "'forgot'",
    r"\bdid not (?:pay attention to|notice)\b": "'ignored'",
    r"\bnot (?:honest|truthful)\b": "'dishonest'",
    r"\bnot important\b": "'trifling' / 'minor'",
    r"\bnot able to\b": "'cannot'",
    r"\bnot (?:the same|identical)\b": "'differs'",
    r"\bnot un(?!do|der|dergo|pack|til|less|ion)\w+\b": "state it positively",
}

# TS-05: intensifiers that measure nothing.
# 'rather' is an intensifier in "rather large" but a contrast in "rather
# than" — and "rather than" is what TS-01 recommends as a replacement, so
# flagging it would have the catalog contradict itself.
INTENSIFIERS = r"\b(very|really|quite|extremely|incredibly|truly|highly|vastly|utterly|considerably|rather(?!\s+than))\b"
DEMONSTRATIVE_VERY = re.compile(r"\b(?:these|this|those|that)\s+very\b")

# TS-08: hedges. A stack of them in one sentence is the finding, not one.
HEDGES = r"\b(may|might|could|perhaps|possibly|arguably|somewhat|fairly|seems? to|appears? to|suggests? that|tends? to|relatively|generally|typically|often)\b"
HEDGE_STACK = 3

# Venue hedge policies (GH-338): the stack threshold is venue-keyed. The book
# voice removes every hedge (rule 10: no hedging on things you know), academic
# prose keeps single calibrated hedges on empirical claims and only flags
# stacks. Callers map a venue profile's hedge_policy to a threshold; absent a
# policy, HEDGE_STACK applies unchanged.
HEDGE_POLICY_STACK = {"zero": 1, "minimal": 2, "calibrated": HEDGE_STACK}

# TS-15: words that assert importance instead of demonstrating it. The
# term-of-art exception is load-bearing — see the rule.
IMPORTANCE = r"\b(critical|critically|key|fundamental|strategic|breakthrough|principled|deliberate|grounded|standards-aligned|robust|seamless|delve|delves|delving|ripple|at the heart of|leverage|leverages|leveraging)\b"
TERM_OF_ART_HINTS = (
    "critical section", "critical path", "critical point", "key exchange",
    "public key", "private key", "key management", "primary key", "foreign key",
    "robust statistics", "robust control", "robust estimator", "key performance",
    "api key", "a key", "no key", "the key", "key is", "keys", "key file",
    "whose key", "key does not", "key/value", "by key", "sort key",
    "root key", "missing key", "-<key>", "key of", "keyed", "per key",
    "citation key", "key (used", "key,", "<key>",
)

# TS-14: abbreviation defined on first use in a section.
ABBREV = re.compile(r"\b([A-Z]{2,6})\b")
# An all-caps English word is emphasis, not an abbreviation. Writers capitalize
# for stress ("do NOT commit", "the TOP of the file") and flagging those buries
# the real jargon — eight findings on one SKILL.md were all emphasis.
EMPHASIS_WORDS = {
    "THE", "AND", "OR", "NOT", "ONLY", "MORE", "LESS", "ALL", "ANY", "TOP",
    "BOTTOM", "TO", "IS", "ARE", "DO", "DONT", "NEVER", "ALWAYS", "MUST",
    "SHALL", "BEFORE", "AFTER", "FIRST", "LAST", "ONE", "TWO", "NEW", "OLD",
    "YES", "NO", "RUN", "DRAFT", "STOP", "THIS", "THAT", "WHY", "HOW", "WHAT",
    "EVERY", "EACH", "BOTH", "SAME", "REAL", "OWN", "WITH", "FROM", "INTO",
    "RULE", "STEP", "NOTE", "ONE-", "FIX", "ADD", "CUT", "USE",
}
ABBREV_SKIP = {"AI", "API", "CPU", "GPU", "RAM", "URL", "HTTP", "HTTPS", "JSON",
               "YAML", "XML", "HTML", "CSV", "PDF", "SQL", "TCP", "UDP", "IP",
               "OK", "ID", "IDS", "US", "UK", "EU", "GH", "TS", "MIT", "IEEE",
               # Repo vocabulary: universal here, so flagging it measures house
               # style rather than undefined jargon.
               "PR", "PRD", "PRDS", "LOC", "README", "VISION", "WT", "CI", "CLI",
               "SDK", "MCP", "OS", "UI", "UX", "TODO", "NDA", "OCR", "PDFS",
               # Filename placeholders and language keywords are not
               # abbreviations: prd[NNN], SELECT ALL, git HEAD.
               "NN", "NNN", "N", "XX", "YYYY", "ALL", "HEAD", "MAIN", "EOF",
               "GET", "POST", "PUT", "JSON5", "UTC",
               "GB", "MB", "KB", "TB", "MS", "GHZ", "RAM"}


def _markers():
    """The shared register-marker module (GH-222) — one passive grammar, not two."""
    _shared()
    import register_markers
    return register_markers


def load_prose(path):
    """Prose view of the file, plus the shared paragraph extractor's blocks."""
    _shared()
    if path.endswith((".yaml", ".yml")):
        # YAML input (GH-348): same aligned-view contract as detex below —
        # prose scalar content on its source lines, structure blanked — so
        # every finding's line number refers to the real file.
        import prose_document
        text = "\n".join(prose_document.prose_view_aligned(path))
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if path.endswith(".tex"):
            import detex
            text = "\n".join(detex.detex_aligned(text))
    import md_paragraphs
    return text, md_paragraphs.parse(text)


def split_sentences(text):
    text = re.sub(r"\b(e\.g|i\.e|etc|vs|Dr|Mr|Mrs|Ms|Fig|Eq|cf|al)\.", r"\1<D>", text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.replace("<D>", ".").strip() for p in parts if p.strip()]


def find(rule, line, detail, text, fix=None):
    return {"rule": rule, "line": line, "detail": detail,
            "text": text[:120], "fix": fix}


def tighten_style_check(text, rules=None, base_line=1, hedge_stack=None):
    """Paragraph-scoped style check on a raw text string.

    Runs TS-01, TS-02, TS-03, TS-04, TS-05, TS-08, TS-15 on the text.
    TS-14 (abbreviation before definition) needs cross-section state and
    stays in check(path). Returns list of finding dicts.

    If rules is a set of rule IDs, only those are checked.
    base_line offsets reported line numbers (for embedding in a larger file).
    hedge_stack overrides the TS-08 threshold (venue hedge policy, GH-338);
    None keeps HEDGE_STACK.
    """
    _shared()
    rm = _markers()
    findings = []
    lines = text.split("\n")
    flat_text = re.sub(r"[`*_]", "", " ".join(text.split()).lower())

    want = rules if rules else None

    for idx, raw in enumerate(lines, base_line):
        nxt = lines[idx - base_line + 1] if (idx - base_line + 1) < len(lines) else ""
        low = (raw + " " + nxt).lower()
        own = len(raw)

        if not want or "TS-01" in want:
            for pat, fix in NEEDLESS.items():
                for m in re.finditer(pat, low):
                    if m.start() < own:
                        findings.append(find("TS-01", idx,
                                             f"needless words: '{m.group(0)}'",
                                             raw.strip(), fix))
        if not want or "TS-03" in want:
            for pat, fix in NEGATIVE_FORM.items():
                for m in re.finditer(pat, low):
                    if m.start() < own:
                        findings.append(find("TS-03", idx,
                                             f"negative form: '{m.group(0)}'",
                                             raw.strip(), fix))
        if not want or "TS-05" in want:
            for m in re.finditer(INTENSIFIERS, low):
                if m.group(0) == "very" and DEMONSTRATIVE_VERY.search(
                        low[max(0, m.start() - 12):m.end()]):
                    continue
                if m.start() < own:
                    findings.append(find("TS-05", idx,
                                         f"empty intensifier: '{m.group(0)}'",
                                         raw.strip(),
                                         "delete, or strengthen the word it props up"))
        if not want or "TS-15" in want:
            for m in re.finditer(IMPORTANCE, low):
                if m.start() >= own:
                    continue
                if any(h in flat_text for h in TERM_OF_ART_HINTS):
                    continue
                findings.append(find("TS-15", idx,
                                     f"asserts importance: '{m.group(0)}'",
                                     raw.strip(),
                                     "state what makes it matter, or cut it "
                                     "(check the term-of-art exception first)"))

    for sent in split_sentences(text):
        low = sent.lower()

        if not want or "TS-08" in want:
            n = len(re.findall(HEDGES, low))
            if n >= (hedge_stack or HEDGE_STACK):
                findings.append(find("TS-08", base_line,
                                     f"{n} hedges in one sentence", sent,
                                     "keep the one carrying real uncertainty"))

        if not want or "TS-02" in want:
            agentive = rm.AGENTIVE.findall(sent)
            passives = max(0, len(rm.PASSIVE.findall(sent))
                           - len(rm._ADJECTIVAL.findall(sent)))
            if agentive:
                findings.append(find("TS-02", base_line,
                                     f"agentive passive: '{agentive[0].strip()}...'",
                                     sent, "name the actor as the subject"))
            elif passives >= 3:
                findings.append(find("TS-02", base_line,
                                     f"{passives} passives in one sentence",
                                     sent, "recast at least one as active"))

        if not want or "TS-04" in want:
            noms = rm.NOMINALIZATION.findall(sent)
            of_chain = re.search(
                r"\w+(?:tion|ment|ance|ence|ity|ness|ism|al)s?\s+of\s+"
                r"(?:the|a|an|each|every|this|that|its|their)\b", low)
            if len(set(n_.lower() for n_ in noms)) >= 3 and of_chain:
                findings.append(find("TS-04", base_line,
                                     f"{len(noms)} nominalizations in one "
                                     f"sentence ({', '.join(noms[:3])})",
                                     sent, "restore the buried verbs"))

    return findings


check_paragraph = tighten_style_check


def check(path, hedge_stack=None):
    text, parsed = load_prose(path)
    findings = []
    prose_lines = {ln for ln, cat in parsed.coverage.items() if cat == "prose"}
    lines = text.split("\n")

    para_of = {}
    for start, end, body in parsed.paragraphs:
        flat = re.sub(r"[`*_]", "", " ".join(body.split()).lower())
        for ln in range(start, end + 1):
            para_of[ln] = flat

    for idx, raw in enumerate(lines, 1):
        if idx not in prose_lines:
            continue
        nxt = lines[idx] if idx < len(lines) and (idx + 1) in prose_lines else ""
        low = (raw + " " + nxt).lower()
        own = len(raw)

        for pat, fix in NEEDLESS.items():
            for m in re.finditer(pat, low):
                if m.start() < own:
                    findings.append(find("TS-01", idx, f"needless words: '{m.group(0)}'",
                                         raw.strip(), fix))
        for pat, fix in NEGATIVE_FORM.items():
            for m in re.finditer(pat, low):
                if m.start() < own:
                    findings.append(find("TS-03", idx, f"negative form: '{m.group(0)}'",
                                         raw.strip(), fix))
        for m in re.finditer(INTENSIFIERS, low):
            if m.group(0) == "very" and DEMONSTRATIVE_VERY.search(
                    low[max(0, m.start() - 12):m.end()]):
                continue
            if m.start() < own:
                findings.append(find("TS-05", idx, f"empty intensifier: '{m.group(0)}'",
                                     raw.strip(), "delete, or strengthen the word it props up"))
        for m in re.finditer(IMPORTANCE, low):
            if m.start() >= own:
                continue
            span = para_of.get(idx, re.sub(r"[`*_]", "", low))
            if any(h in span for h in TERM_OF_ART_HINTS):
                continue
            findings.append(find("TS-15", idx, f"asserts importance: '{m.group(0)}'",
                                 raw.strip(),
                                 "state what makes it matter, or cut it "
                                 "(check the term-of-art exception first)"))

    rm = _markers()
    for para in parsed.paragraphs:
        for sent in split_sentences(para[2]):
            low = sent.lower()

            n = len(re.findall(HEDGES, low))
            if n >= (hedge_stack or HEDGE_STACK):
                findings.append(find("TS-08", para[0],
                                     f"{n} hedges in one sentence", sent,
                                     "keep the one carrying real uncertainty"))

            agentive = rm.AGENTIVE.findall(sent)
            passives = max(0, len(rm.PASSIVE.findall(sent))
                           - len(rm._ADJECTIVAL.findall(sent)))
            if agentive:
                findings.append(find("TS-02", para[0],
                                     f"agentive passive: '{agentive[0].strip()}...'",
                                     sent, "name the actor as the subject"))
            elif passives >= 3:
                findings.append(find("TS-02", para[0],
                                     f"{passives} passives in one sentence",
                                     sent, "recast at least one as active"))

            noms = rm.NOMINALIZATION.findall(sent)
            of_chain = re.search(
                r"\w+(?:tion|ment|ance|ence|ity|ness|ism|al)s?\s+of\s+"
                r"(?:the|a|an|each|every|this|that|its|their)\b", low)
            if len(set(n.lower() for n in noms)) >= 3 and of_chain:
                findings.append(find("TS-04", para[0],
                                     f"{len(noms)} nominalizations in one "
                                     f"sentence ({', '.join(noms[:3])})",
                                     sent, "restore the buried verbs"))

    # TS-14: abbreviation used before definition.
    defined, seen_heading = set(), 0
    for idx, raw in enumerate(lines, 1):
        if raw.strip().startswith("#"):
            defined.clear()
            seen_heading = idx
            continue
        if idx not in prose_lines:
            continue
        # Both orders define an abbreviation: "Citation Style Language (CSL)"
        # and "CSL (Citation Style Language)". Only the first was recognised,
        # so the reverse form still reported the term as undefined.
        for m in re.finditer(r"\b([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){0,4})\s+\(([A-Z]{2,6})\)", raw):
            defined.add(m.group(2))
        for m in re.finditer(r"\b([A-Z]{2,6})\s+\([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){1,4}\)", raw):
            defined.add(m.group(1))
        for m in ABBREV.finditer(raw):
            a = m.group(1)
            if a in ABBREV_SKIP or a in EMPHASIS_WORDS or a in defined:
                continue
            defined.add(a)        # report once per section
            findings.append(find("TS-14", idx, f"'{a}' used without expansion"
                                 + (f" since the heading at line {seen_heading}" if seen_heading else ""),
                                 raw.strip(), "spell it out on first use in the section"))

    # Metric rules: delegate, do not reimplement.
    try:
        _stylometry()
        import style
        prose_only = "\n\n".join(p[2] for p in parsed.paragraphs)
        sents = split_sentences(prose_only)
        if sents:
            nom = sum(len(re.findall(
                r"\b\w+(?:tion|ment|ance|ence|ity|ness|ism)\b", s.lower())) for s in sents)
            per_1000 = nom / max(1, len(prose_only.split())) * 1000
            # 70 marks a genuine outlier. The author's own papers measure 22
            # to 66 per 1000, so a tighter absolute gate would flag their
            # natural register — the density-floor mistake in rule form. Where
            # a writing-voice/ corpus exists, that baseline replaces this
            # number; this is the no-corpus fallback.
            # A rate needs a denominator: 2 nominalizations in 17 words
            # extrapolates to 118/1000, which is arithmetic, not evidence.
            # Short documents are fully covered by the per-sentence check.
            if per_1000 > 70 and len(prose_only.split()) >= 300:
                findings.append(find("TS-04", parsed.paragraphs[0][0] if parsed.paragraphs else 1,
                                     f"{per_1000:.0f} nominalizations per 1000 words",
                                     "(document-level)", "restore the buried verbs"))
    except ImportError:
        pass

    return findings


def main():
    ap = argparse.ArgumentParser(description="check prose against the style rules")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rule", help="comma-separated rule IDs to limit to")
    ap.add_argument("--hedge-policy", choices=sorted(HEDGE_POLICY_STACK),
                    help="venue hedge policy for TS-08 (GH-338): zero flags "
                         "every hedge, minimal flags pairs, calibrated flags "
                         "stacks (the default threshold)")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        sys.exit(f"no such file: {a.file}")
    findings = check(a.file,
                     hedge_stack=HEDGE_POLICY_STACK.get(a.hedge_policy))
    if a.rule:
        want = {r.strip().upper() for r in a.rule.split(",")}
        findings = [f for f in findings if f["rule"] in want]

    if a.json:
        print(json.dumps(findings, indent=2))
    else:
        if not findings:
            print(f"{a.file}: no rule findings (judgment rules still need a read)")
        for f in sorted(findings, key=lambda x: (x["rule"], x["line"])):
            print(f"  {f['rule']}  L{f['line']:<5} {f['detail']}")
            if f["fix"]:
                print(f"            -> {f['fix']}")
        by_rule = {}
        for f in findings:
            by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
        if by_rule:
            print(f"\n{len(findings)} findings: " +
                  ", ".join(f"{k} x{v}" for k, v in sorted(by_rule.items())))
            print("A finding is a prompt to look, not a verdict. Check each "
                  "rule's exception before changing anything, and tighten "
                  "toward the author's density, never past it.")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
