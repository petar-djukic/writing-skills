#!/usr/bin/env python3
"""Quantitative style analyzer for the match-structure skill.

Computes measurable style metrics over markdown papers: sentence and
paragraph distributions, passive voice, hedging, frequency tables of words
and phrases, citation density, and section structure. No model calls — this
is the deterministic half of the skill; the qualitative half is done by the
model reading the corpus.

Subcommands:
  profile  Analyze one or more markdown files. Prints a JSON profile with
           whole-paper metrics, per-section metrics, and frequency tables.
  corpus   Aggregate profiles for all selected corpus papers from the
           references.yaml database. Writes voice-profile.json next to the db.
  compare  Diff a draft's profile against voice-profile.json. Prints JSON
           deltas: metric deltas, frequency over/under-use, per-section deltas.
  freq     Standalone ranked word / phrase / idiom frequency table.
  similarity  Plagiarism guard: flag shared word sequences (n-gram shingling,
           default 8 words) between a file and one or more --against files.
           --baseline excludes phrasing that already existed in the original
           draft, so only rewrite-introduced overlap is flagged.

Corpus selection defaults to entries with status: summarized (papers the
user actually engaged with). --all widens to every entry with an md_path.

Stdlib only except PyYAML.
"""

import argparse
import difflib
import json
import math
import os
import re
import sys
from collections import Counter

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with: python3 -m pip install --user pyyaml")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SECTION_PATTERNS = [
    ("intro", r"introduction|overview|motivation"),
    ("related", r"related\s+work|background|prior\s+work|literature"),
    ("methodology", r"method(?:s|ology)?|approach|model|architecture|design|framework"),
    ("results", r"results?|experiments?|evaluation|empirical|findings|analysis"),
    ("conclusion", r"conclusion|discussion|future\s+work|summary"),
    ("references", r"references?|bibliography|works\s+cited"),
]

STOCK_PHRASES = [
    "to this end", "it is worth noting", "we posit", "in this paper",
    "state of the art", "state-of-the-art", "to the best of our knowledge",
    "in this work", "we propose", "we present", "we introduce", "we show that",
    "we demonstrate", "note that", "in particular", "in other words",
    "on the other hand", "in contrast", "in addition", "as a result",
    "in order to", "due to the fact", "it should be noted", "we observe that",
    "we find that", "as shown in", "as illustrated in", "compared to",
    "with respect to", "in terms of", "a wide range of", "plays a crucial role",
    "has attracted", "significant attention", "extensive experiments",
    "remains an open", "we leave", "for future work", "our contributions",
    "the rest of this paper", "is organized as follows",
]

HEDGE_WORDS = {
    "may", "might", "could", "possibly", "perhaps", "likely", "unlikely",
    "suggests", "suggest", "seems", "seem", "appears", "appear", "arguably",
    "somewhat", "relatively", "potentially", "presumably", "tends", "tend",
    "generally", "typically", "often", "usually", "roughly", "approximately",
}

# Common English words to exclude from jargon extraction (a compact stoplist
# standing in for a general-English reference corpus).
STOPWORDS = set("""
a about above after again all also an and any are as at be because been
before being below between both but by can did do does doing down during
each few for from further had has have having he her here hers him his how
i if in into is it its itself just me more most my no nor not now of off on
once only or other our out over own same she should so some such than that
the their them then there these they this those through to too under until
up very was we were what when where which while who whom why will with you
your however thus hence therefore moreover furthermore although though since
while whereas via using used use based given following section figure table
equation paper work method model results data set one two three first second
new non pre well within without across along among et al ie eg
""".split())

FUNCTION_WORDS = set("""
a an the this that these those my your his her its our their
i me we us you he him she they them it
who whom whose which what
am is are was were be been being
have has had do does did will would shall should
can could may might must
and but or nor for yet so
in on at to by from with of into through during before after
above below between among against about across along around
if then than when where how because although though while unless
not no neither either both each every all any few more most
some such
""".split())

PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"\[@[^\]]+\]|\[\d+(?:\s*,\s*\d+)*\]|\(\w+(?:\s+et\s+al\.?)?,?\s+\d{4}[a-z]?\)")
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]+")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Text utilities
# --------------------------------------------------------------------------- #

def strip_markdown(text):
    """Remove code blocks, tables, images, and inline formatting noise."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"^\|.*\|$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\$\$.*?\$\$", " EQUATION ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$\n]+\$", " MATH ", text)
    return text


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)
    return [s.strip() for s in parts if len(s.strip()) > 2]


def split_paragraphs(text):
    """Paragraph chunks for style measurement and anchor retrieval.

    Deliberately not filter-tells's md_paragraphs.py, the canonical extractor for
    "which lines of this document are prose" (GH-167). The jobs differ: that
    one maps paragraphs back to source line ranges so a rewrite can be spliced
    in, while this one whitespace-flattens exemplar text into comparable
    chunks and never needs to write anything back. Line fidelity is the whole
    point there and irrelevant here.
    """
    parts = re.split(r"\n\s*\n", text)
    out = []
    for p in parts:
        p = " ".join(p.split())
        if len(p) > 40 and not p.startswith("#"):
            out.append(p)
    return out


def words_of(text):
    return [w.lower() for w in WORD_RE.findall(text)]


def detect_sections(text):
    """Split a markdown paper into named sections via heading heuristics.

    Returns a dict section-name -> text. Unmatched headings go to 'other'.
    Text before the first heading goes to 'front'.
    """
    matches = list(HEADING_RE.finditer(text))
    sections = {}
    if not matches:
        sections["other"] = text
        return sections

    def classify(title):
        t = title.lower()
        for name, pat in SECTION_PATTERNS:
            if re.search(pat, t):
                return name
        return "other"

    if matches[0].start() > 0:
        sections["front"] = text[:matches[0].start()]

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        name = classify(m.group(2))
        sections[name] = sections.get(name, "") + "\n" + text[start:end]
    return sections


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

_VOWELS = re.compile(r"[aeiouy]+", re.IGNORECASE)
_SILENT_E = re.compile(r"[^aeiouy]e$", re.IGNORECASE)


def _syllable_count(word):
    """Estimate syllables via vowel-cluster heuristic."""
    w = word.lower().strip()
    if len(w) <= 2:
        return 1
    count = len(_VOWELS.findall(w))
    if _SILENT_E.search(w) and count > 1:
        count -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in "aeiouy":
        count += 1
    return max(count, 1)


def _clause_lengths(sentences):
    """Approximate clause lengths by splitting on commas/semicolons."""
    lengths = []
    for s in sentences:
        clauses = re.split(r"[;,]", s)
        for c in clauses:
            wds = words_of(c)
            if wds:
                lengths.append(len(wds))
    return lengths


def text_metrics(text):
    """Compute style metrics for a block of text."""
    clean = strip_markdown(text)
    sentences = split_sentences(clean)
    paragraphs = split_paragraphs(clean)
    tokens = words_of(clean)
    n_sent = len(sentences)
    n_words = len(tokens)
    if n_sent == 0 or n_words == 0:
        return None

    sent_lengths = [len(words_of(s)) for s in sentences]
    mean_sl = sum(sent_lengths) / n_sent
    var_sl = sum((x - mean_sl) ** 2 for x in sent_lengths) / n_sent

    para_lengths = [len(split_sentences(p)) for p in paragraphs]
    mean_pl = (sum(para_lengths) / len(para_lengths)) if para_lengths else 0

    openers = Counter()
    for s in sentences:
        ws = words_of(s)
        if ws:
            openers[ws[0]] += 1

    passive = len(PASSIVE_RE.findall(clean))
    citations = len(CITATION_RE.findall(text))
    hedges = sum(1 for w in tokens if w in HEDGE_WORDS)

    # Readability
    syllables = [_syllable_count(w) for w in WORD_RE.findall(clean)]
    total_syllables = sum(syllables)
    avg_syl = total_syllables / n_words
    complex_words = sum(1 for s in syllables if s >= 3)
    polysyllables = complex_words

    flesch_re = 206.835 - 1.015 * mean_sl - 84.6 * avg_syl
    fk_grade = 0.39 * mean_sl + 11.8 * avg_syl - 15.59
    gunning_fog = 0.4 * (mean_sl + 100 * complex_words / n_words)
    smog = 3 + math.sqrt(polysyllables * 30 / n_sent) if n_sent > 0 else 0

    # Lexical diversity
    unique_words = len(set(tokens))
    ttr = unique_words / n_words
    corrected_ttr = unique_words / math.sqrt(n_words)
    freq_dist = Counter(tokens)
    hapax = sum(1 for w, c in freq_dist.items() if c == 1)
    hapax_ratio = hapax / n_words

    freq_of_freq = Counter(freq_dist.values())
    m2 = sum(i * i * fi for i, fi in freq_of_freq.items())
    yules_k = 10000 * (m2 - n_words) / (n_words * n_words) if n_words > 1 else 0

    # Syntactic
    stdev_sl = math.sqrt(var_sl)
    sent_cv = stdev_sl / mean_sl if mean_sl > 0 else 0
    clause_lens = _clause_lengths(sentences)
    mean_clause = (sum(clause_lens) / len(clause_lens)) if clause_lens else 0

    # Stylometrics
    func_count = sum(1 for w in tokens if w in FUNCTION_WORDS)
    func_ratio = func_count / n_words

    punct_counts = {
        "commas": clean.count(","),
        "semicolons": clean.count(";"),
        "em_dashes": clean.count("—") + clean.count("---") + clean.count(" -- "),
        "colons": clean.count(":"),
    }
    punct_per_1000 = {k: round(1000 * v / n_words, 2) for k, v in punct_counts.items()}

    # Paragraph cohesion (tf-idf cosine between consecutive paragraphs)
    cohesion = None
    if len(paragraphs) >= 2:
        para_tokens = [Counter(words_of(p)) for p in paragraphs]
        df = Counter()
        for pt in para_tokens:
            df.update(pt.keys())
        n_para = len(paragraphs)
        para_vecs = []
        for pt in para_tokens:
            total = sum(pt.values()) or 1
            para_vecs.append({w: (c / total) * math.log((1 + n_para) / (1 + df[w]) + 1)
                              for w, c in pt.items()})
        sims = []
        for i in range(len(para_vecs) - 1):
            a, b = para_vecs[i], para_vecs[i + 1]
            common = set(a) & set(b)
            if not common:
                sims.append(0.0)
                continue
            num = sum(a[w] * b[w] for w in common)
            da = math.sqrt(sum(v * v for v in a.values()))
            db = math.sqrt(sum(v * v for v in b.values()))
            sims.append(num / (da * db) if da and db else 0.0)
        cohesion = round(sum(sims) / len(sims), 4)

    return {
        "sentences": n_sent,
        "words": n_words,
        "sentence_length_mean": round(mean_sl, 2),
        "sentence_length_stdev": round(stdev_sl, 2),
        "paragraph_length_mean_sentences": round(mean_pl, 2),
        "paragraphs": len(paragraphs),
        "passive_per_100_sentences": round(100 * passive / n_sent, 2),
        "hedges_per_1000_words": round(1000 * hedges / n_words, 2),
        "citations_per_paragraph": round(citations / len(paragraphs), 2) if paragraphs else 0,
        "top_sentence_openers": dict(openers.most_common(10)),
        # Readability
        "flesch_reading_ease": round(flesch_re, 2),
        "flesch_kincaid_grade": round(fk_grade, 2),
        "gunning_fog": round(gunning_fog, 2),
        "smog_index": round(smog, 2),
        # Lexical diversity
        "type_token_ratio": round(ttr, 4),
        "corrected_ttr": round(corrected_ttr, 4),
        "hapax_ratio": round(hapax_ratio, 4),
        "yules_k": round(yules_k, 2),
        # Syntactic
        "sentence_length_cv": round(sent_cv, 4),
        "mean_clause_length": round(mean_clause, 2),
        # Stylometrics
        "function_word_ratio": round(func_ratio, 4),
        "punctuation_per_1000w": punct_per_1000,
        # Computational
        "paragraph_cohesion": cohesion,
    }


def frequency_tables(text, top=50):
    """Ranked word, phrase (2-4 gram), and stock-idiom frequency tables."""
    clean = strip_markdown(text).lower()
    tokens = words_of(clean)
    n = max(len(tokens), 1)

    word_freq = Counter(t for t in tokens if t not in STOPWORDS and len(t) > 2)

    ngrams = Counter()
    for size in (2, 3, 4):
        for i in range(len(tokens) - size + 1):
            gram = tokens[i:i + size]
            if gram[0] in STOPWORDS and gram[-1] in STOPWORDS:
                continue
            ngrams[" ".join(gram)] += 1
    ngrams = Counter({g: c for g, c in ngrams.items() if c >= 3})

    idioms = {}
    for phrase in STOCK_PHRASES:
        count = clean.count(phrase)
        if count:
            idioms[phrase] = count

    return {
        "total_words": n,
        "words": dict(word_freq.most_common(top)),
        "phrases": dict(ngrams.most_common(top)),
        "idioms": dict(sorted(idioms.items(), key=lambda kv: -kv[1])),
    }


def _strip_front_matter(text):
    """Remove YAML front matter (--- delimited block at file start)."""
    if not text.startswith("---"):
        return text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _shared_scripts():
    _shared = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
    if _shared not in sys.path:
        sys.path.insert(0, _shared)


def read_prose(path, raw=False):
    """Read a file, returning its prose view.

    Strips YAML front matter by default so metrics are comparable with the rest
    of the prose stack (md_paragraphs, pangram_report, tighten). Pass raw=True
    to include front matter (whole-file stats). YAML documents (GH-347) yield
    their prose scalar paragraphs joined by blank lines — keys, comments, and
    structure never enter the metrics; raw=True has no effect for them.
    """
    if path.endswith((".yaml", ".yml")):
        _shared_scripts()
        from prose_document import ProseDocument
        return "\n\n".join(
            p.text for p in ProseDocument.open(path).paragraphs)
    with open(path) as f:
        text = f.read()
    if path.endswith(".tex"):
        _shared_scripts()
        import detex
        text = detex.detex(text)[0]
    elif not raw:
        text = _strip_front_matter(text)
    return text


def profile_file(path, raw=False):
    text = read_prose(path, raw=raw)
    sections = detect_sections(text)
    per_section = {}
    for name, sec_text in sections.items():
        m = text_metrics(sec_text)
        if m:
            per_section[name] = m
    return {
        "file": path,
        "overall": text_metrics(text),
        "sections": per_section,
        "section_word_share": {
            name: m["words"] for name, m in per_section.items()
        },
        "frequency": frequency_tables(text),
    }


# --------------------------------------------------------------------------- #
# Corpus aggregation
# --------------------------------------------------------------------------- #

def load_db(path):
    if not os.path.exists(path):
        sys.exit(f"Database not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "papers" in data:
        return data["papers"]
    return []


def select_corpus(db_path, include_all=False):
    """Return list of (entry, absolute md path) for corpus papers."""
    entries = load_db(db_path)
    db_dir = os.path.dirname(os.path.abspath(db_path))
    out = []
    for e in entries:
        md_rel = e.get("md_path") or e.get("text_path")
        if not md_rel:
            continue
        if not include_all and e.get("status") != "summarized":
            continue
        md_abs = os.path.join(db_dir, md_rel)
        if os.path.exists(md_abs):
            out.append((e, md_abs))
    return out


def select_voice_corpus(voice_dir, role=None, tags=None, pre_ai=None):
    """Return list of (entry, absolute md path) from a writing-voice manifest.

    Same return shape as select_corpus so callers can dispatch on either source.
    """
    import voice_anchors as va
    exemplars = va.load_manifest(voice_dir)
    want = {t.strip().lower() for t in (tags or []) if t.strip()}
    out = []
    for ex in exemplars:
        if role and ex.get("role") != role:
            continue
        if pre_ai is not None and va.is_pre_ai(ex) != pre_ai:
            continue
        if want:
            have = {str(x).lower() for x in (ex.get("tags") or [])}
            if not (want & have):
                continue
        p = os.path.join(voice_dir, ex.get("file", ""))
        if os.path.exists(p):
            out.append((ex, p))
    return out


def mean_of(dicts, key):
    # A metric can be present but None (e.g. paragraph_cohesion on a
    # single-paragraph sample); one thin exemplar must not crash the corpus
    # aggregate (GH-339).
    vals = [d[key] for d in dicts if d and d.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def std_of(dicts, key):
    """Population std across papers, so consumers (filter-tells voice-distance)
    can compute z-scores instead of unscaled deltas."""
    vals = [d[key] for d in dicts if d and d.get(key) is not None]
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return round((sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5, 3)


METRIC_KEYS = [
    "sentence_length_mean", "sentence_length_stdev",
    "paragraph_length_mean_sentences", "passive_per_100_sentences",
    "hedges_per_1000_words", "citations_per_paragraph",
    "flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog", "smog_index",
    "type_token_ratio", "corrected_ttr", "hapax_ratio", "yules_k",
    "sentence_length_cv", "mean_clause_length",
    "function_word_ratio", "paragraph_cohesion",
]


def aggregate(profiles):
    """Aggregate per-paper profiles into a corpus profile."""
    overall = [p["overall"] for p in profiles if p["overall"]]
    metric_keys = METRIC_KEYS
    agg = {k: mean_of(overall, k) for k in metric_keys}
    agg_std = {k: std_of(overall, k) for k in metric_keys}

    section_names = set()
    for p in profiles:
        section_names.update(p["sections"].keys())
    sections = {}
    for name in section_names:
        sec_metrics = [p["sections"][name] for p in profiles if name in p["sections"]]
        sections[name] = {k: mean_of(sec_metrics, k) for k in metric_keys}
        sections[name]["papers_with_section"] = len(sec_metrics)

    total_words = sum(p["frequency"]["total_words"] for p in profiles)
    word_freq = Counter()
    phrase_freq = Counter()
    idiom_freq = Counter()
    doc_freq = Counter()
    for p in profiles:
        word_freq.update(p["frequency"]["words"])
        phrase_freq.update(p["frequency"]["phrases"])
        idiom_freq.update(p["frequency"]["idioms"])
        doc_freq.update(set(p["frequency"]["words"].keys()))

    n_docs = len(profiles)
    jargon = {}
    for w, tf in word_freq.most_common(500):
        df = doc_freq[w]
        if df >= max(2, n_docs // 3):
            jargon[w] = {"count": tf, "papers": df,
                         "per_10k_words": round(10000 * tf / total_words, 2)}

    return {
        "papers": n_docs,
        "total_words": total_words,
        "metrics": agg,
        "metrics_std": agg_std,
        "sections": sections,
        "frequency": {
            "words": dict(word_freq.most_common(100)),
            "phrases": dict(phrase_freq.most_common(100)),
            "idioms": dict(idiom_freq.most_common(50)),
        },
        "jargon": dict(list(jargon.items())[:100]),
    }


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #

def compare_profiles(draft_profile, corpus_profile):
    metric_keys = METRIC_KEYS
    draft_overall = draft_profile["overall"] or {}
    corpus_metrics = corpus_profile["metrics"]

    deltas = {}
    for k in metric_keys:
        d, c = draft_overall.get(k), corpus_metrics.get(k)
        if d is not None and c is not None:
            deltas[k] = {"draft": d, "corpus": c, "delta": round(d - c, 2)}

    section_deltas = {}
    for name, draft_sec in draft_profile["sections"].items():
        corpus_sec = corpus_profile["sections"].get(name)
        if not corpus_sec:
            continue
        sd = {}
        for k in metric_keys:
            d, c = draft_sec.get(k), corpus_sec.get(k)
            if d is not None and c is not None:
                sd[k] = {"draft": d, "corpus": c, "delta": round(d - c, 2)}
        section_deltas[name] = sd

    draft_words = draft_profile["frequency"]["total_words"]
    corpus_words = corpus_profile["total_words"]
    draft_freq = draft_profile["frequency"]["words"]
    corpus_freq = corpus_profile["frequency"]["words"]

    overused, underused = [], []
    for w, dc in Counter(draft_freq).most_common(200):
        d_rate = 10000 * dc / draft_words
        c_rate = 10000 * corpus_freq.get(w, 0) / corpus_words
        if c_rate == 0 and d_rate > 2:
            overused.append({"term": w, "draft_per_10k": round(d_rate, 2),
                             "corpus_per_10k": 0})
        elif c_rate > 0 and d_rate > 3 * c_rate and d_rate > 1:
            overused.append({"term": w, "draft_per_10k": round(d_rate, 2),
                             "corpus_per_10k": round(c_rate, 2)})
    for w, cc in Counter(corpus_freq).most_common(100):
        c_rate = 10000 * cc / corpus_words
        d_rate = 10000 * draft_freq.get(w, 0) / draft_words
        if c_rate > 1 and d_rate < c_rate / 3:
            underused.append({"term": w, "draft_per_10k": round(d_rate, 2),
                              "corpus_per_10k": round(c_rate, 2)})

    draft_idioms = draft_profile["frequency"]["idioms"]
    corpus_idioms = corpus_profile["frequency"]["idioms"]

    return {
        "metric_deltas": deltas,
        "section_deltas": section_deltas,
        "overused_terms": overused[:30],
        "underused_terms": underused[:30],
        "idioms": {
            "draft_only": {k: v for k, v in draft_idioms.items() if k not in corpus_idioms},
            "corpus_only": dict(list(
                {k: v for k, v in corpus_idioms.items() if k not in draft_idioms}.items())[:20]),
            "shared": {k: {"draft": v, "corpus": corpus_idioms[k]}
                       for k, v in draft_idioms.items() if k in corpus_idioms},
        },
        "missing_sections": [s for s in corpus_profile["sections"]
                             if s not in draft_profile["sections"]
                             and s not in ("front", "other")],
    }


# --------------------------------------------------------------------------- #
# Similarity (plagiarism guard)
# --------------------------------------------------------------------------- #

def normalize_tokens(text):
    """Tokenize for similarity: strip markdown and citations, lowercase."""
    clean = strip_markdown(text)
    clean = CITATION_RE.sub(" ", clean)
    return words_of(clean)


def shingle_set(tokens, n):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def find_shared_runs(tokens_a, tokens_b, n):
    """Maximal shared word runs of length >= n between two token lists."""
    index = {}
    for i in range(len(tokens_b) - n + 1):
        index.setdefault(tuple(tokens_b[i:i + n]), []).append(i)
    runs = []
    i = 0
    while i <= len(tokens_a) - n:
        gram = tuple(tokens_a[i:i + n])
        if gram in index:
            j = index[gram][0]
            length = n
            while (i + length < len(tokens_a) and j + length < len(tokens_b)
                   and tokens_a[i + length] == tokens_b[j + length]):
                length += 1
            runs.append({"a_word_index": i, "b_word_index": j,
                         "words": length,
                         "text": " ".join(tokens_a[i:i + length])})
            i += length
        else:
            i += 1
    return runs


def is_stock_only(run_text):
    """True if a run is stock idioms plus glue — not worth flagging."""
    remaining = run_text
    for phrase in STOCK_PHRASES:
        remaining = remaining.replace(phrase, " ")
    content = [w for w in words_of(remaining) if w not in STOPWORDS]
    return len(content) < 3


def similarity_report(subject_text, against, n=8, baseline_text=None):
    """Compare subject against each (name, text) in `against`.

    Returns per-source matches (excluding baseline-carried and stock-only
    runs) plus summary stats.
    """
    subject_tokens = normalize_tokens(subject_text)
    subject_shingles = shingle_set(subject_tokens, n)
    baseline_shingles = (shingle_set(normalize_tokens(baseline_text), n)
                         if baseline_text else set())

    sources = []
    total_flagged = 0
    for name, text in against:
        tokens = normalize_tokens(text)
        runs = find_shared_runs(subject_tokens, tokens, n)
        flagged = []
        for run in runs:
            i = run["a_word_index"]
            run_shingles = {tuple(subject_tokens[k:k + n])
                            for k in range(i, i + run["words"] - n + 1)}
            if baseline_shingles and run_shingles <= baseline_shingles:
                continue
            if is_stock_only(run["text"]):
                continue
            flagged.append(run)
        overlap = len(subject_shingles & shingle_set(tokens, n))
        norm_subject = " ".join(subject_tokens)
        norm_source = " ".join(tokens)
        lcm = difflib.SequenceMatcher(None, norm_subject, norm_source,
                                      autojunk=False).find_longest_match(
            0, len(norm_subject), 0, len(norm_source))
        sources.append({
            "source": name,
            "matches": flagged,
            "shingle_overlap_ratio": round(
                overlap / max(len(subject_shingles), 1), 4),
            "longest_common_chars": lcm.size,
        })
        total_flagged += len(flagged)

    return {
        "ngram": n,
        "subject_words": len(subject_tokens),
        "total_flagged_matches": total_flagged,
        "sources": sources,
    }


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #

def cmd_profile(args):
    profiles = [profile_file(f, raw=args.raw) for f in args.files]
    out = profiles[0] if len(profiles) == 1 else profiles
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_corpus(args):
    corpus = select_corpus(args.db, include_all=args.all)
    if not corpus:
        sys.exit("No corpus papers found. Need entries with md_path"
                 + ("" if args.all else " and status: summarized")
                 + f" in {args.db}.")
    profiles = [profile_file(path) for _, path in corpus]
    agg = aggregate(profiles)
    agg["corpus_files"] = {
        path: os.path.getmtime(path) for _, path in corpus
    }
    db_dir = os.path.dirname(os.path.abspath(args.db))
    out_path = args.out or os.path.join(db_dir, "voice-profile.json")
    with open(out_path, "w") as f:
        json.dump(agg, f, indent=2, ensure_ascii=False)
    print(json.dumps({"written": out_path, "papers": agg["papers"],
                      "total_words": agg["total_words"]}, indent=2))


def cmd_compare(args):
    db_dir = os.path.dirname(os.path.abspath(args.db))
    profile_path = args.profile or os.path.join(db_dir, "voice-profile.json")
    if not os.path.exists(profile_path):
        sys.exit(f"Corpus profile not found: {profile_path}. Run `corpus` first.")
    with open(profile_path) as f:
        corpus_profile = json.load(f)
    draft_profile = profile_file(args.draft)
    result = compare_profiles(draft_profile, corpus_profile)
    result["draft"] = args.draft
    result["corpus_papers"] = corpus_profile["papers"]
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_freq(args):
    text = read_prose(args.file)
    print(json.dumps(frequency_tables(text, top=args.top),
                     indent=2, ensure_ascii=False))


def cmd_similarity(args):
    subject = read_prose(args.file)
    against = []
    for path in args.against:
        against.append((path, read_prose(path)))
    baseline = None
    if args.baseline:
        with open(args.baseline) as f:
            baseline = f.read()
    report = similarity_report(subject, against, n=args.ngram,
                               baseline_text=baseline)
    report["file"] = args.file
    report["baseline"] = args.baseline
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Quantitative style analyzer")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("profile", help="profile one or more markdown files")
    pr.add_argument("files", nargs="+")
    pr.add_argument("--raw", action="store_true",
                    help="include YAML front matter in metrics (default: strip it)")
    pr.set_defaults(func=cmd_profile)

    co = sub.add_parser("corpus", help="aggregate corpus profile, write voice-profile.json")
    co.add_argument("--all", action="store_true",
                    help="include every entry with md_path (default: status summarized only)")
    co.add_argument("--out", default=None, help="output path (default: <db-dir>/voice-profile.json)")
    co.set_defaults(func=cmd_corpus)

    cm = sub.add_parser("compare", help="compare a draft against the corpus profile")
    cm.add_argument("draft", help="path to the draft markdown file")
    cm.add_argument("--profile", default=None,
                    help="corpus profile path (default: <db-dir>/voice-profile.json)")
    cm.set_defaults(func=cmd_compare)

    fr = sub.add_parser("freq", help="ranked word/phrase/idiom frequency table")
    fr.add_argument("file")
    fr.add_argument("--top", type=int, default=50)
    fr.set_defaults(func=cmd_freq)

    si = sub.add_parser("similarity", help="flag shared word sequences (plagiarism guard)")
    si.add_argument("file", help="the file to check (e.g. the rewritten draft)")
    si.add_argument("--against", nargs="+", required=True,
                    help="source files to compare against (exemplars, corpus papers)")
    si.add_argument("--baseline", default=None,
                    help="original draft; phrasing already present there is not flagged")
    si.add_argument("--ngram", type=int, default=8,
                    help="minimum shared word-sequence length to flag (default: 8)")
    si.set_defaults(func=cmd_similarity)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
