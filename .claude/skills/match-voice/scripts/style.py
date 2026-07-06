#!/usr/bin/env python3
"""Quantitative style analyzer for the match-voice skill.

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

Corpus selection defaults to entries with status: summarized (papers the
user actually engaged with). --all widens to every entry with an md_path.

Stdlib only except PyYAML.
"""

import argparse
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

    return {
        "sentences": n_sent,
        "words": n_words,
        "sentence_length_mean": round(mean_sl, 2),
        "sentence_length_stdev": round(math.sqrt(var_sl), 2),
        "paragraph_length_mean_sentences": round(mean_pl, 2),
        "paragraphs": len(paragraphs),
        "passive_per_100_sentences": round(100 * passive / n_sent, 2),
        "hedges_per_1000_words": round(1000 * hedges / n_words, 2),
        "citations_per_paragraph": round(citations / len(paragraphs), 2) if paragraphs else 0,
        "top_sentence_openers": dict(openers.most_common(10)),
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


def profile_file(path):
    with open(path) as f:
        text = f.read()
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


def mean_of(dicts, key):
    vals = [d[key] for d in dicts if d and key in d]
    return round(sum(vals) / len(vals), 2) if vals else None


def aggregate(profiles):
    """Aggregate per-paper profiles into a corpus profile."""
    overall = [p["overall"] for p in profiles if p["overall"]]
    metric_keys = [
        "sentence_length_mean", "sentence_length_stdev",
        "paragraph_length_mean_sentences", "passive_per_100_sentences",
        "hedges_per_1000_words", "citations_per_paragraph",
    ]
    agg = {k: mean_of(overall, k) for k in metric_keys}

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
    metric_keys = [
        "sentence_length_mean", "sentence_length_stdev",
        "paragraph_length_mean_sentences", "passive_per_100_sentences",
        "hedges_per_1000_words", "citations_per_paragraph",
    ]
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
# Subcommands
# --------------------------------------------------------------------------- #

def cmd_profile(args):
    profiles = [profile_file(f) for f in args.files]
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
    with open(args.file) as f:
        text = f.read()
    print(json.dumps(frequency_tables(text, top=args.top),
                     indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Quantitative style analyzer")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("profile", help="profile one or more markdown files")
    pr.add_argument("files", nargs="+")
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

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
