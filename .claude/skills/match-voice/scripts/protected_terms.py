#!/usr/bin/env python3
"""Protected terms and canonical blocks for match-voice (GH-77, sub-issue A).

Two article-level guards the per-paragraph pipeline could not express:

Protected terms. The largest failure class in the GH-189 measured run was a
term-of-art swap that broke a referent chain running across paragraphs
(exposure -> justification, decision plane -> decision, detector -> tool).
Each swap passed the mechanical gate, because the gate judges one paragraph
against its own original and a referent chain is a property of the article.
A word or phrase that recurs in three or more paragraphs IS the chain, so it
is derived once per article, written beside it as a hand-editable list, sent
to the rewrite model as a hard rule, and checked by verify.py as a fatal
finding when lost. A sentence repeated verbatim across paragraphs (a refrain)
is protected whole, for the same reason.

Canonical blocks. Some paragraphs are pasted, not written — an AI-disclosure
line, a subscribe line, a "Start Here" pointer — and must never reach the
model. They are not span-locked because they are inserted at paste time, so
the registry lives beside the voice corpus (writing-voice/canonical-blocks.txt)
or is passed explicitly. One pattern per line: a plain case-insensitive
substring, or `re:<regex>`.

Library:
  derive(texts)                       -> sorted protected terms (stdlib, deterministic)
  path_for(article)                   -> <stem>.protected-terms.txt beside the article
  read_terms(path) / write_terms(path, terms)
  load_or_derive(article, texts, path=None) -> (terms, path, derived)
  terms_in(text, terms)               -> the subset present in one paragraph
  present(term, text)                 -> whole-word/phrase, case-insensitive
  load_canonical(explicit=None, article=None) -> (patterns, path)
  is_canonical(text, patterns)
  canonical_indices(paragraph_texts, patterns) -> 1-based indices

CLI:
  protected_terms.py <article.md|yaml> [--write] [--json]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

MIN_PARAGRAPHS = 3       # a term in fewer paragraphs is not a chain
MIN_TERM_LEN = 4
REFRAIN_MIN_WORDS = 6
REFRAIN_MIN_PARAGRAPHS = 2
CANONICAL_FILE = "canonical-blocks.txt"

# GH-239. Recurrence alone cannot tell a term of art from a common verb: on a
# 48-paragraph article the old rule derived 142 terms, 128 of them ordinary
# words (means, read, record, name, leave, look, wrong), and since a lost
# protected term is a fatal finding, paraphrase could not pass the gate at all.
# Distinctiveness can tell them apart. A term earns protection when this
# article leans on it harder than ordinary prose does, measured against the
# voice corpus the caller already has open: keep it when its paragraph share
# here is at least MIN_OVERREP times its document share there. Terms absent
# from the background are kept outright. Measured on that article, 142 -> 44,
# every common-word false positive gone and no real term of art lost
# (touchpoint 17.5x, constitution 13.1x, validator 13.1x, against find 0.1x,
# look 0.1x, means 0.0x). Without a background the rule cannot run, and
# derive() falls back to recurrence alone.
MIN_OVERREP = 0.7

# Spelled numbers are never terms of art, and verify.py already runs a
# dedicated `numbers` check over them — protecting them too meant a rewrite
# that rendered a count differently took a protected-term fatal on top of the
# check that exists for it.
NUMBER_WORDS = set("""
one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty
fifty sixty seventy eighty ninety hundred thousand million billion trillion
dozen half quarter third fourth fifth sixth seventh eighth ninth tenth
first second once twice
""".split())

STOPWORDS = set("""
a about above after again against all almost along already also although
always among an and another any anyone anything are around as at away back
be became because become becomes been before being below between both but by
came can cannot could did do does doing done down during each either else
enough even ever every everyone everything few first for from further get
gets give given goes going got had has have having he her here hers herself
him himself his how however i if in into is it its itself just keep kept
last least less let like little made make makes many may maybe me might more
most much must my myself near need never next no nor not nothing now of off
often on once one only onto or other others our ours ourselves out over own
part perhaps put quite rather really said same say says see seem seemed
seems seen several shall she should since so some something still such take
taken than that the their theirs them themselves then there these they thing
things think this those though three through thus time to together too took
toward two under until up upon us use used uses using very was way we well
were what when where whether which while who whom whose why will with within
without would yes yet you your yours yourself
actually really simply basically know knows knew known keep keeps kept lose
loses lost moment moments people person thing things work works worked
working year years today want wants wanted need needs needed
""".split())
# The second block is generic verbs and adverbs that recur in any essay
# without being anyone's term of art; measured on a published post, they
# were the bulk of the noise in a 63-term derivation (GH-77).

_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w.-]+\.(?:com|org|net|io|dev|md|ai)\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*[A-Za-z]|[A-Za-z]")
_SENTENCE = re.compile(r"[^.!?]+[.!?]+")


_LOCK_TOKEN = re.compile(r"\[\[LOCK-\d+\]\]")


def _tokens(text):
    # Inline lock anchors reach derive() as [[LOCK-n]] (GH-82); "lock" in
    # three such paragraphs is not a term of art.
    text = _URL.sub(" ", _LOCK_TOKEN.sub(" ", text.replace("\u2019", "'")))
    out = []
    for w in _WORD.findall(text):
        w = w.lower().strip("'-")
        if "'" in w:      # a contraction is never a term of art
            continue
        out.append(w)
    return out


def _merge_plurals(occurrences):
    """Fold a plural's paragraph set into its singular's BEFORE the
    threshold: 'developer' in two paragraphs and 'developers' in two more is
    one chain of four, and the match is plural-tolerant anyway."""
    for t in sorted(occurrences, key=len, reverse=True):
        for suffix in ("es", "s"):
            stem = t[:-len(suffix)]
            if t.endswith(suffix) and stem in occurrences and stem != t:
                occurrences[stem] |= occurrences.pop(t)
                break
    return occurrences


def _content(tok):
    return len(tok) >= MIN_TERM_LEN and tok not in STOPWORDS


def is_number_term(term):
    """A term made only of spelled numbers ('five', 'twenty-five')."""
    words = [w for chunk in term.lower().split() for w in chunk.split("-")]
    return bool(words) and all(w in NUMBER_WORDS for w in words)


def _document_share(term, background):
    """Fraction of background documents the term appears in."""
    if not background:
        return None
    pat = _pattern(term)
    return sum(1 for d in background if pat.search(d)) / len(background)


def _distinctive(term, paragraph_share, background, min_overrep):
    """Does this article lean on the term harder than ordinary prose does?

    A term the background never uses is distinctive by definition. Otherwise
    compare shares: paragraph share here against document share there.
    """
    share = _document_share(term, background)
    if share is None:          # no background: the test cannot run
        return True
    if share == 0.0:
        return True
    return paragraph_share / share >= min_overrep


def derive(texts, background=None, min_overrep=MIN_OVERREP):
    """Protected terms for an article given its paragraph texts.

    Unigrams and bigrams of content words that occur in MIN_PARAGRAPHS or
    more distinct paragraphs, plus any sentence of REFRAIN_MIN_WORDS or more
    words repeated verbatim in REFRAIN_MIN_PARAGRAPHS or more paragraphs.
    Sorted, lowercase for terms, original casing for refrains.

    Spelled numbers are dropped (verify.py checks numbers separately). Given
    `background` — the voice corpus documents — a term also has to be
    distinctive: its paragraph share here at least `min_overrep` times its
    document share there. Refrains skip the test; a sentence repeated verbatim
    is a chain whatever its words are.
    """
    uni, bi = defaultdict(set), defaultdict(set)
    refrains = defaultdict(set)
    for i, text in enumerate(texts):
        toks = _tokens(text)
        for t in toks:
            if _content(t):
                uni[t].add(i)
        for a, b in zip(toks, toks[1:]):
            if _content(a) and _content(b):
                bi[f"{a} {b}"].add(i)
        for m in _SENTENCE.finditer(text):
            s = " ".join(m.group(0).split())
            if len(s.split()) >= REFRAIN_MIN_WORDS:
                refrains[s].add(i)
    uni, bi = _merge_plurals(uni), _merge_plurals(bi)
    n = len(texts) or 1
    candidates = {t: ps for t, ps in uni.items() if len(ps) >= MIN_PARAGRAPHS}
    candidates.update({t: ps for t, ps in bi.items() if len(ps) >= MIN_PARAGRAPHS})
    terms = {t for t, ps in candidates.items()
             if not is_number_term(t)
             and _distinctive(t, len(ps) / n, background, min_overrep)}
    terms |= {s for s, ps in refrains.items() if len(ps) >= REFRAIN_MIN_PARAGRAPHS}
    return sorted(terms, key=lambda s: (s.lower(), s))


def path_for(article):
    return os.path.splitext(os.path.abspath(article))[0] + ".protected-terms.txt"


def read_terms(path):
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                terms.append(s)
    return terms


def write_terms(path, terms, article=None):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Protected terms for " + (os.path.basename(article) if article else "this article") + "\n")
        f.write("# Derived by match-voice/scripts/protected_terms.py: words and phrases in "
                f"{MIN_PARAGRAPHS}+ paragraphs that this article leans on at least "
                f"{MIN_OVERREP}x harder than the voice corpus does, refrains in "
                f"{REFRAIN_MIN_PARAGRAPHS}+. Spelled numbers excluded (verify.py checks "
                "numbers separately).\n")
        f.write("# Hand-editable: one term per line; this file is never overwritten once "
                "it exists.\n")
        for t in terms:
            f.write(t + "\n")


def load_or_derive(article, texts, path=None, background=None):
    """(terms, path, derived). An existing file is read and never overwritten —
    it is the hand-edited list. Absent, derive from the texts and write it."""
    path = path or path_for(article)
    if os.path.exists(path):
        return read_terms(path), path, False
    terms = derive(texts, background=background)
    write_terms(path, terms, article)
    return terms, path, True


def _pattern(term):
    # Whole word or phrase; a plural suffix on the last word still counts as
    # the same term (specimen/specimens is one chain, not a swap).
    return re.compile(r"(?<![\w-])" + re.escape(" ".join(term.split()))
                      .replace(r"\ ", r"\s+") + r"(?:es|s)?(?![\w-])", re.I)


def present(term, text):
    return bool(_pattern(term).search(text))


def terms_in(text, terms):
    """The protected terms this paragraph carries, in list order."""
    return [t for t in terms if present(t, text)]


def lost(original, rewritten, terms):
    """Terms present in the original and missing from the rewrite."""
    return [t for t in terms_in(original, terms) if not present(t, rewritten)]


# --- canonical blocks --------------------------------------------------------

def discover_canonical(article):
    """writing-voice/canonical-blocks.txt, walking up from the article."""
    d = os.path.dirname(os.path.abspath(article))
    while True:
        cand = os.path.join(d, "writing-voice", CANONICAL_FILE)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def read_canonical(path):
    """[(kind, pattern)] — kind is 'substring' or 'regex'."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("re:"):
                out.append(("regex", re.compile(s[3:], re.I)))
            else:
                out.append(("substring", s.lower()))
    return out


def load_canonical(explicit=None, article=None):
    """(patterns, path). No registry anywhere is a normal state: ([], None)."""
    path = explicit or (discover_canonical(article) if article else None)
    if not path:
        return [], None
    return read_canonical(path), path


def is_canonical(text, patterns):
    flat = " ".join(text.split())
    low = flat.lower()
    for kind, pat in patterns:
        if kind == "substring" and pat in low:
            return True
        if kind == "regex" and pat.search(flat):
            return True
    return False


def canonical_indices(texts, patterns):
    """1-based indices of canonical paragraphs — the driver's numbering."""
    return {i + 1 for i, t in enumerate(texts) if is_canonical(t, patterns)}


# --- CLI ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="derive an article's protected terms")
    ap.add_argument("article")
    ap.add_argument("--write", action="store_true",
                    help="write <stem>.protected-terms.txt if absent")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    shared = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                           "..", "..", "..", "scripts"))
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import prose_document
    texts = [p.text for p in prose_document.ProseDocument.open(a.article).paragraphs]
    if a.write:
        terms, path, derived = load_or_derive(a.article, texts)
    else:
        terms, path, derived = derive(texts), path_for(a.article), None
    if a.json:
        print(json.dumps({"path": path, "derived": derived, "terms": terms}, indent=2))
    else:
        print(f"{len(terms)} protected term(s) "
              f"({'written to' if derived else 'loaded from' if derived is False else 'would write'} {path})")
        for t in terms:
            print("  " + t)


if __name__ == "__main__":
    main()
