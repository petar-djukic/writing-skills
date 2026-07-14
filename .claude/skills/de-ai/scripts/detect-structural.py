#!/usr/bin/env python3
"""
detect-structural.py — Detect structural AI writing patterns in markdown files.

Measures:
- Sentence length variance (burstiness) — two-sided: too uniform is AI,
  extremely high is overshoot (text tuned against this very check)
- Paragraph length uniformity
- Parallelism (repeated syntactic openings)
- Negation-then-affirmation / clipped antithesis pairs
- List-to-prose ratio
- Colon density
- Dash density
- Sentence opening diversity
- Performance intensity ("LinkedIn voice"): per-sentence rhetoric markers,
  plain-sentence rate, intensity variance
- Punch detection: short contrast sentences in positions of emphasis
- Word salad: function-word ratio, content-word runs, nominalizations,
  hyphenated compounds
- Repeated formulae: coined 4-word phrases recurring within or across files

Usage:
    python3 detect-structural.py <file-or-dir> [file-or-dir ...] [--json] [--threshold=strict]

Accepts: single file, multiple files, directories (scans *.md recursively).
Exit codes: 0 = clean, 1 = issues found, 2 = usage error
"""

import sys
import re
import json
import difflib
import statistics
from pathlib import Path
from collections import Counter

import detex  # LaTeX -> prose preprocessing (same dir)

# --- Thresholds ---
THRESHOLDS = {
    "strict": {
        "sentence_length_std_min": 5.0,   # sentences should vary this much
        "sentence_length_std_max": 35.0,   # above this: overshoot suspicion
        "paragraph_length_std_min": 20.0,  # paragraphs should vary
        "parallelism_max_repeats": 2,      # max consecutive same-opening sentences
        "list_ratio_max": 0.25,            # max fraction of lines that are list items
        "colon_density_max": 3.0,          # max colons per 500 words
        "dash_density_max": 2.0,           # max em-dashes per 500 words
        "opening_diversity_min": 0.7,      # min ratio of unique openings to total sentences
        "plain_sentence_rate_min": 0.30,   # min fraction of sentences with no rhetoric markers
        "punch_clustering_max": 0.25,      # max fraction of paragraphs closing on a punch
        "salad_rate_max": 8.0,             # max salad sentences per 100
        "hyphen_compound_max": 5.0,        # max coined hyphen compounds per 500 words
    },
    "medium": {
        "sentence_length_std_min": 4.0,
        "sentence_length_std_max": 40.0,
        "paragraph_length_std_min": 15.0,
        "parallelism_max_repeats": 2,
        "list_ratio_max": 0.30,
        "colon_density_max": 4.0,
        "dash_density_max": 3.0,
        "opening_diversity_min": 0.6,
        "plain_sentence_rate_min": 0.25,
        "punch_clustering_max": 0.30,
        "salad_rate_max": 10.0,
        "hyphen_compound_max": 6.0,
    },
    "relaxed": {
        "sentence_length_std_min": 3.0,
        "sentence_length_std_max": 50.0,
        "paragraph_length_std_min": 10.0,
        "parallelism_max_repeats": 3,
        "list_ratio_max": 0.40,
        "colon_density_max": 5.0,
        "dash_density_max": 4.0,
        "opening_diversity_min": 0.5,
        "plain_sentence_rate_min": 0.20,
        "punch_clustering_max": 0.40,
        "salad_rate_max": 15.0,
        "hyphen_compound_max": 8.0,
    },
}

# Issue types that indicate the overshoot direction (Goodharted, over-polished
# prose) rather than the bland-AI direction.
OVERSHOOT_TYPES = {
    "overshoot-burstiness", "performing-heavy", "punch-clustered",
    "word-salad-heavy", "hyphen-compound-heavy", "colon-heavy", "dash-heavy",
    "contrast-flip-heavy",
}


def extract_prose(text: str) -> str:
    """Strip markdown headers, code blocks, frontmatter, and metadata."""
    lines = text.split("\n")
    prose_lines = []
    in_code_block = False
    in_frontmatter = False

    for i, line in enumerate(lines):
        # Frontmatter
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            continue

        # Code blocks
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip headers
        if line.strip().startswith("#"):
            continue

        # Skip HTML comments
        if line.strip().startswith("<!--"):
            continue

        # Skip image/link-only lines
        if re.match(r"^\s*!\[.*\]\(.*\)\s*$", line):
            continue

        # Skip numbered reference-list entries: "[1] Author (2026). ..."
        if re.match(r"^\s*\[\d+\]\s", line):
            continue

        prose_lines.append(line)

    prose = "\n".join(prose_lines)
    # Strip inline/display math so LaTeX tokens don't pollute word metrics
    prose = re.sub(r"\$\$.*?\$\$", " ", prose, flags=re.DOTALL)
    prose = re.sub(r"\$[^$\n]+\$", " ", prose)
    return prose


def split_sentences(text: str) -> list:
    """Split text into sentences. Handles abbreviations roughly."""
    # Replace common abbreviations to avoid false splits
    text = re.sub(r"\b(e\.g|i\.e|etc|vs|Dr|Mr|Mrs|Ms|Jr|Sr)\.", r"\1<DOT>", text)
    sentences = re.split(r"[.!?]+(?=\s|$)", text)
    sentences = [s.strip().replace("<DOT>", ".") for s in sentences if s.strip()]
    # Filter out very short fragments (< 4 words)
    return [s for s in sentences if len(s.split()) >= 4]


def split_sentences_all(text: str) -> list:
    """Split into sentences WITHOUT dropping short fragments.

    split_sentences() discards anything under 4 words to keep the burstiness
    math clean. But the clipped second clause ("The meter was.", "Different
    bill.") IS the antithesis tell, so the antithesis detector needs a list
    that keeps every fragment.
    """
    text = re.sub(r"\b(e\.g|i\.e|etc|vs|Dr|Mr|Mrs|Ms|Jr|Sr)\.", r"\1<DOT>", text)
    sentences = re.split(r"[.!?]+(?=\s|$)", text)
    return [s.strip().replace("<DOT>", ".") for s in sentences if s.strip()]


# Light verbs / negations that, as a sentence's final word, signal an elliptical
# antithesis where the complement is elided to mirror the prior sentence:
# "The meter was.", "The missing workflow is.", "...a number that does not."
_ELLIPTICAL_FINAL = {
    "is", "was", "are", "were", "does", "do", "did", "will", "would",
    "has", "have", "had", "can", "could", "should", "not",
    "isn't", "wasn't", "aren't", "weren't", "doesn't", "didn't", "don't", "won't",
}
# A bare negation as the final word is almost always antithesis, regardless of
# sentence length ("...a number that does not.").
_NEGATION_FINAL = {
    "not", "isn't", "wasn't", "aren't", "weren't",
    "doesn't", "didn't", "don't", "won't",
}
_NEGATION = re.compile(
    r"\b(not|never|no|isn't|wasn't|aren't|weren't|don't|doesn't|didn't|won't"
    r"|cannot|can't|hadn't|haven't|hasn't|couldn't|wouldn't|shouldn't)\b",
    re.IGNORECASE,
)
# Sentence 2 of a negation flip re-affirms by pointing back: "It is...", "That
# is...". Requiring this restart separates the real flip ("...is not X. It is
# Y.") from a mid-sentence "not" followed by an unrelated next sentence.
_RESTART = {"it", "it's", "that", "that's", "this", "they", "they're", "those",
            "these", "there", "i'd", "you", "you're", "we'd", "we're"}
# Demonstrative restarts that carry the flip even in a LONG completion:
# "The problem wasn't the AI. It was my lack of structure around how I worked."
_STRONG_RESTART = {"it", "it's", "that's", "this"}


def detect_antithesis(sentences_all: list) -> list:
    """Flag negation-then-affirmation and clipped declarative pairs.

    Three sub-patterns, each an "obvious AI" antithesis reflex. Zero tolerance:
    every instance is reported individually, because a single one reads as AI.

      A. negation flip  — sentence 1 negates, sentence 2 is a short counter
                          ("...is not the dollars. It is the ceiling.")
      B. elliptical end — sentence 2 ends on a bare copula/auxiliary/negation
                          ("The meter was.", "...a number that does not.")
      C. clipped pair   — two adjacent fragments, both very short
                          ("Same quality out. Different bill.")
    """
    issues = []
    for i in range(1, len(sentences_all)):
        s1, s2 = sentences_all[i - 1], sentences_all[i]
        w1, w2 = s1.split(), s2.split()
        if not w1 or not w2:
            continue
        len1, len2 = len(w1), len(w2)
        last2 = w2[-1].rstrip(".,;:!?\"'").lower()
        first2 = w2[0].rstrip(".,;:!?\"'").lower()

        first1 = w1[0].rstrip(".,;:!?\"'").lower()
        s1_negated = bool(_NEGATION.search(s1))
        # negation in s2's opening words (for the mirrored affirm -> negate flip)
        s2_head_negated = bool(_NEGATION.search(" ".join(w2[:4])))

        if s1_negated and len2 <= 6 and first2 in _RESTART:
            kind, sev = "antithesis-negation", "high"
        elif s1_negated and len2 <= 15 and first2 in _STRONG_RESTART:
            # Long completion: the demonstrative restart is the tell, not the
            # brevity ("The constraint is not the tool. It is the imagination
            # of the person holding it.")
            kind, sev = "antithesis-long-completion", "medium"
        elif (s1_negated and len2 <= 12 and first1 == first2
              and first2 in ("the", "a", "an")):
            # Noun-phrase restart: "The developer isn't disappearing. The job
            # is moving up the stack."
            kind, sev = "antithesis-noun-restart", "medium"
        elif (not s1_negated and s2_head_negated and len2 <= 15
              and (first2 in _RESTART or first2 == first1)):
            # Mirrored flip, affirm -> negate: "Cutting costs improves
            # margins. It doesn't produce the next Cash App."
            kind, sev = "antithesis-reverse", "medium"
        elif last2 in _ELLIPTICAL_FINAL and (len2 <= 6 or last2 in _NEGATION_FINAL):
            kind, sev = "antithesis-elliptical", "high"
        elif len1 <= 4 and len2 <= 4:
            kind, sev = "antithesis-fragment", "medium"
        else:
            continue

        snippet = f"{s1}. {s2}."
        if len(snippet) > 110:
            snippet = snippet[:107] + "..."
        issues.append({
            "type": kind,
            "detail": f'Negation/antithesis pair (obvious AI cadence): "{snippet}"',
            "severity": sev,
            "position": f"sentence pair {i}-{i + 1}",
        })
    return issues


def split_with_terminators(text: str) -> list:
    """Sentence chunks that KEEP their terminator, for interrogative checks.

    split_sentences_all() drops the [.!?] delimiter, so question marks are
    invisible to it. This split preserves them.
    """
    text = re.sub(r"\b(e\.g|i\.e|etc|vs|Dr|Mr|Mrs|Ms|Jr|Sr)\.", r"\1<DOT>", text)
    chunks = re.findall(r"[^.!?]+[.!?]+", text)
    return [c.strip().replace("<DOT>", ".") for c in chunks if c.strip()]


def detect_question_patterns(paragraphs: list) -> list:
    """Question volleys and question->short-answer templates, per paragraph.

    Volley: >= 3 consecutive interrogative sentences (the checklist-as-
    questions move). Template: >= 2 adjacent (question, answer <= 4 words)
    pairs — the self-interview cadence ("Is it reliable? Not really. Does
    it work? Absolutely.").
    """
    issues = []
    for p_idx, para in enumerate(paragraphs):
        chunks = split_with_terminators(para)
        if len(chunks) < 3:
            continue
        is_q = [c.endswith("?") for c in chunks]

        # Volley: runs of consecutive questions
        run = 0
        for i, q in enumerate(is_q + [False]):
            if q:
                run += 1
                continue
            if run >= 3:
                snippet = " ".join(chunks[i - run:i])[:110]
                issues.append({
                    "type": "question-volley",
                    "detail": (f"{run} consecutive questions in paragraph "
                               f"{p_idx + 1} — checklist-as-questions cadence: "
                               f'"{snippet}..."'),
                    "severity": "high" if run >= 5 else "medium",
                    "position": f"paragraph {p_idx + 1}",
                })
            run = 0

        # Question -> short-answer template
        qa_pairs = 0
        example = ""
        for i in range(len(chunks) - 1):
            if is_q[i] and not is_q[i + 1] and len(chunks[i + 1].split()) <= 4:
                qa_pairs += 1
                if not example:
                    example = f"{chunks[i]} {chunks[i + 1]}"
        if qa_pairs >= 2:
            issues.append({
                "type": "question-short-answer",
                "detail": (f"{qa_pairs} question->short-answer pairs in paragraph "
                           f"{p_idx + 1} — self-interview template: "
                           f'"{example[:100]}..."'),
                "severity": "medium",
                "position": f"paragraph {p_idx + 1}",
            })
    return issues


def split_paragraphs(text: str) -> list:
    """Split into paragraphs (separated by blank lines)."""
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip() and len(p.split()) >= 5]


def count_list_lines(text: str) -> tuple:
    """Count lines that are list items vs total non-empty lines."""
    lines = [l for l in text.split("\n") if l.strip()]
    list_lines = [l for l in lines if re.match(r"^\s*[-*+•]\s|^\s*\d+[.)]\s", l)]
    return len(list_lines), len(lines)


def get_sentence_openings(sentences: list) -> list:
    """Extract first 3 words of each sentence (lowercased)."""
    openings = []
    for s in sentences:
        words = s.split()[:3]
        openings.append(" ".join(words).lower().rstrip(",;:"))
    return openings


def detect_parallelism(openings: list, max_repeats: int) -> list:
    """Find runs of consecutive sentences with the same opening pattern."""
    issues = []
    if len(openings) < 3:
        return issues

    run_start = 0
    for i in range(1, len(openings)):
        # Check if opening matches (first 2 words)
        prev_prefix = " ".join(openings[i - 1].split()[:2])
        curr_prefix = " ".join(openings[i].split()[:2])

        if prev_prefix == curr_prefix and len(prev_prefix) > 2:
            # Continue run
            pass
        else:
            run_length = i - run_start
            if run_length > max_repeats:
                issues.append({
                    "type": "parallelism",
                    "detail": f"{run_length} consecutive sentences start with '{openings[run_start].split()[0]}...'",
                    "severity": "high" if run_length > 3 else "medium",
                    "position": f"sentences {run_start + 1}-{i}",
                })
            run_start = i

    # Check final run
    run_length = len(openings) - run_start
    if run_length > max_repeats:
        issues.append({
            "type": "parallelism",
            "detail": f"{run_length} consecutive sentences start with '{openings[run_start].split()[0]}...'",
            "severity": "high" if run_length > 3 else "medium",
            "position": f"sentences {run_start + 1}-{len(openings)}",
        })

    return issues


# Endings so trivial that a shared pair is noise, not an echo.
_TRIVIAL_TAIL = set("the a an of to in on it and or is are be as at by for with".split())


def _tail_tokens(sentence: str, n: int = 4) -> list:
    """Last n word tokens of a sentence, lowercased."""
    return re.findall(r"[a-z0-9']+", sentence.lower())[-n:]


def detect_tail_echo(sentences: list) -> list:
    """Flag adjacent sentences whose endings echo each other (epanalepsis).

    detect_parallelism compares sentence *openings*; a rewrite that varies the
    heads but keeps near-identical tails ("...whatever model you run." /
    "...whatever you run it on.") sails through it while staying a mirror pair.
    Compare the last 4 tokens of each adjacent pair; flag when they share >=2,
    at least one of which is not a trivial stopword (so "...of the day." /
    "...of the week." does not trip it).
    """
    issues = []
    for i in range(1, len(sentences)):
        a = _tail_tokens(sentences[i - 1])
        b = _tail_tokens(sentences[i])
        if len(a) < 4 or len(b) < 4:
            continue
        shared = set(a) & set(b)
        if len(shared) >= 2 and any(t not in _TRIVIAL_TAIL for t in shared):
            issues.append({
                "type": "tail_echo",
                "detail": f"adjacent sentence endings echo: shared tail words {sorted(shared)}",
                "severity": "medium",
                "position": f"sentences {i}-{i + 1}",
            })
    return issues


# --------------------------------------------------------------------------- #
# Overshoot detectors ("LinkedIn voice", punches, word salad, formulae)
# --------------------------------------------------------------------------- #

FUNCTION_WORDS = set("""
a an the this that these those it its they them their he she his her we our
you your i my me us of in on at by for with from to into onto over under
between among through during within without across along after before
against about around near behind beyond up down off out and or but nor so
yet if then than as because since while when where whether although though
unless until who whom whose which what is are was were be been being am do
does did done have has had having will would shall should can could may
might must not no any some each every all both few more most other such
only own same too very just there here how why also
""".split())

_ANTITHESIS_INLINE = [
    re.compile(r"\bnot\b[^.;:]{0,80}\bbut\b", re.IGNORECASE),          # not X but Y
    re.compile(r"[,;—]\s*(?:and\s+)?not\s+\w+", re.IGNORECASE),   # appositive ", not Y"
    re.compile(r"\brather than\b", re.IGNORECASE),
    re.compile(r",\s*never\b", re.IGNORECASE),
]
_REVERSAL_OPENERS = {"but", "yet", "except", "nor"}
_FINITE_MARKERS = FUNCTION_WORDS & {
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did",
    "have", "has", "had", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must",
}
_DEMONSTRATIVE_SUBJECTS = {"that", "this", "it", "no", "not", "so", "such"}
_NOMINALIZATION = re.compile(
    r"\b\w{4,}(?:tion|ment|ance|ence|ity|ness)s?\b", re.IGNORECASE)
_HYPHEN_COMPOUND = re.compile(r"\b[a-z]{3,}-[a-z]{3,}(?:-[a-z]{3,})?\b")
_CITE_OR_DATA = re.compile(r"\d|\[@|`|\\ref|\\cite")


def _words(sentence: str) -> list:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)


def _has_finite_verb(words_lower: list) -> bool:
    if any(w in _FINITE_MARKERS for w in words_lower):
        return True
    # Approximate: any -s/-ed verb form beyond the first word
    return any(re.match(r".{3,}(?:ed|es)$", w) for w in words_lower[1:])


def performance_score(sentence: str) -> int:
    """Count rhetoric markers in one sentence (0 = plain declarative)."""
    score = 0
    core = sentence.strip()
    # pivot: colon or em-dash mid-sentence
    if re.search(r"\S\s*[:—]\s+\S", core):
        score += 1
    if any(rx.search(core) for rx in _ANTITHESIS_INLINE):
        score += 1
    # parallelism: 3+ comma-separated short clauses
    if len(re.findall(r",\s+\w+", core)) >= 3:
        score += 1
    wl = [w.lower() for w in _words(core)]
    if wl and not _has_finite_verb(wl):
        score += 1  # fragment
    if wl and wl[0] in _REVERSAL_OPENERS:
        score += 1
    return score


def analyze_performance(sentences_all: list) -> dict:
    """Plain-sentence rate and intensity variance over all sentences."""
    if len(sentences_all) < 5:
        return {}
    scores = [performance_score(s) for s in sentences_all]
    plain = sum(1 for s in scores if s == 0)
    return {
        "plain_sentence_rate": round(plain / len(scores), 2),
        "intensity_variance": round(statistics.pvariance(scores), 2),
        "mean_performance_score": round(statistics.mean(scores), 2),
    }


def is_punch(sentence: str, other_lengths: list, position_final_or_solo: bool) -> bool:
    """Punchy = contrast + position of emphasis + rhetorical shape."""
    words = _words(sentence)
    n = len(words)
    if n == 0 or n > 8:
        return False
    if not position_final_or_solo:
        return False
    if _CITE_OR_DATA.search(sentence):
        return False  # data sentences are exempt
    if other_lengths:
        mean_other = statistics.mean(other_lengths)
        if not (n < 0.4 * mean_other):
            return False
    # else: single-sentence paragraph — position alone qualifies
    wl = [w.lower() for w in words]
    copular = any(w in ("is", "are", "was", "were") for w in wl)
    fragment = not _has_finite_verb(wl)
    demonstrative = wl[0] in _DEMONSTRATIVE_SUBJECTS
    return copular or fragment or demonstrative


def analyze_punch(paragraphs: list) -> dict:
    """Punch rate and clustering over paragraphs."""
    if len(paragraphs) < 3:
        return {}
    punches = []
    total_sentences = 0
    closing_punches = 0
    for p_idx, para in enumerate(paragraphs):
        sents = split_sentences_all(para)
        if not sents:
            continue
        total_sentences += len(sents)
        lengths = [len(_words(s)) for s in sents]
        for i, s in enumerate(sents):
            others = lengths[:i] + lengths[i + 1:]
            is_edge = (i == 0 or i == len(sents) - 1) or len(sents) == 1
            if is_punch(s, others, is_edge):
                punches.append({"paragraph": p_idx + 1, "sentence": s.strip()[:90]})
                if i == len(sents) - 1:
                    closing_punches += 1
    if total_sentences == 0:
        return {}
    return {
        "punch_rate_per_100": round(100 * len(punches) / total_sentences, 1),
        "punch_clustering": round(closing_punches / len(paragraphs), 2),
        "punch_candidates": punches[:20],
    }


def salad_components(sentence: str) -> list:
    """Which word-salad components does this sentence trip?"""
    words = _words(sentence)
    if len(words) < 8:
        return []
    wl = [w.lower() for w in words]
    comps = []
    fw = sum(1 for w in wl if w in FUNCTION_WORDS)
    if fw / len(wl) < 0.30:
        comps.append("low-function-word-ratio")
    run = best = 0
    for w in wl:
        run = 0 if w in FUNCTION_WORDS else run + 1
        best = max(best, run)
    if best >= 5:
        comps.append(f"content-run-{best}")
    if len(_NOMINALIZATION.findall(sentence)) >= 4:
        comps.append("nominalization-dense")
    return comps


def analyze_salad(sentences_all: list, prose: str, word_count: int) -> dict:
    """Word-salad metrics: flagged sentences, rate, hyphen-compound density."""
    if len(sentences_all) < 5:
        return {}
    candidates = []
    for i, s in enumerate(sentences_all):
        comps = salad_components(s)
        if len(comps) >= 2:
            candidates.append({"sentence_index": i + 1,
                               "components": comps,
                               "sentence": s.strip()[:110]})
    hyphens = len(_HYPHEN_COMPOUND.findall(prose.lower()))
    return {
        "salad_rate_per_100": round(100 * len(candidates) / len(sentences_all), 1),
        "salad_candidates": candidates[:20],
        "hyphen_compound_per_500w": round(hyphens / word_count * 500, 1) if word_count else 0,
    }


def _content_terms(text: str) -> set:
    """Lowercased content words (stopword-free, lightly stemmed)."""
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text.lower()):
        if w in FUNCTION_WORDS:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


_LINK_PRONOUNS = {"it", "this", "that", "these", "those", "they", "such",
                  "he", "she", "its", "their", "both", "each", "here"}


def analyze_paragraph_schema(paragraphs: list) -> dict:
    """Mechanical proxies for paragraph-schema conformance (Gopen & Swan,
    Williams, Strunk & White). Advisory scores, not pass/fail — the
    semantic prompt adjudicates. Three proxies per paragraph:

      topic_overlap: content-term overlap between sentence 1 and the body.
        Low overlap = the paragraph opens mid-argument (the TOPIC defect).
      cohesion: fraction of sentences whose opening clause shares a
        referent (content term or linking pronoun) with the prior sentence
        (Williams' old-to-new flow).
      subject_churn: distinct sentence-subject heads / sentences. High
        churn = topic drift, more than one point per paragraph.
    """
    per_para = []
    for p_idx, para in enumerate(paragraphs):
        sents = split_sentences_all(para)
        if len(sents) < 3:
            continue
        s1_terms = _content_terms(sents[0])
        body_terms = _content_terms(" ".join(sents[1:]))
        topic_overlap = (len(s1_terms & body_terms) / len(s1_terms)
                         if s1_terms else 0.0)

        linked = 0
        for i in range(1, len(sents)):
            opening = " ".join(sents[i].split()[:6]).lower()
            open_words = set(re.findall(r"[a-z'-]+", opening))
            prev_terms = _content_terms(sents[i - 1])
            if (open_words & _LINK_PRONOUNS
                    or _content_terms(opening) & prev_terms):
                linked += 1
        cohesion = linked / (len(sents) - 1)

        heads = set()
        for s in sents:
            words = [w.lower().strip(".,;:!?\"'") for w in s.split()]
            head = ""
            for w in words[:4]:
                if w and w not in FUNCTION_WORDS:
                    head = w
                    break
            if not head and words:
                head = words[0]
            heads.add(head)
        subject_churn = len(heads) / len(sents)

        # Anaphoric opener: the paragraph's first sentence starts on a
        # back-reference ("That axis...", "Both predictions...") — its topic
        # lives in the previous paragraph. The other face of the TOPIC
        # defect: overlap can be high while the referent is still distant.
        first_word = sents[0].split()[0].strip(".,;:!?\"'").lower() if sents[0].split() else ""
        opens_anaphorically = first_word in _LINK_PRONOUNS

        per_para.append({
            "paragraph": p_idx + 1,
            "opening": " ".join(para.split()[:7]),
            "sentences": len(sents),
            "topic_overlap": round(topic_overlap, 2),
            "cohesion": round(cohesion, 2),
            "subject_churn": round(subject_churn, 2),
            "opens_anaphorically": opens_anaphorically,
        })

    if not per_para:
        return {}
    lows = [p for p in per_para
            if p["topic_overlap"] < 0.2 or p["opens_anaphorically"]]
    return {
        "paragraphs_scored": len(per_para),
        "mean_topic_overlap": round(
            sum(p["topic_overlap"] for p in per_para) / len(per_para), 2),
        "mean_cohesion": round(
            sum(p["cohesion"] for p in per_para) / len(per_para), 2),
        "mean_subject_churn": round(
            sum(p["subject_churn"] for p in per_para) / len(per_para), 2),
        "low_topic_paragraphs": [
            {"paragraph": p["paragraph"], "opening": p["opening"],
             "topic_overlap": p["topic_overlap"],
             "reason": ("anaphoric-opener" if p["opens_anaphorically"]
                        else "low-overlap")} for p in lows][:10],
        "per_paragraph": per_para[:30],
    }


def detect_opener_duplication(file_texts: list, threshold: float = 0.75):
    """Abstract/introduction first-sentence duplication (cross-document).

    file_texts: list of (filename, RAW text). Finds the first sentence after
    an Abstract marker (markdown heading, bold, or \\begin{abstract}) and
    after an Introduction heading — across all files of the invocation —
    and reports when their similarity exceeds the threshold. Motivating
    case: a manuscript whose abstract and introduction opened with the
    identical sentence, invisible to every per-file check.
    """
    markers = {
        "abstract": re.compile(
            r"(?:^|\n)\s*(?:#{1,4}\s*abstract\b[^\n]*|\*\*abstract\*\*[^\n]*"
            r"|\\begin\{abstract\})",
            re.IGNORECASE),
        "introduction": re.compile(
            r"(?:^|\n)#{1,4}\s*(?:\d+[.\s]*)?introduction\b[^\n]*",
            re.IGNORECASE),
    }
    openers = {}
    for fname, text in file_texts:
        for kind, rx in markers.items():
            if kind in openers:
                continue
            m = rx.search(text)
            if not m:
                continue
            after = text[m.end():]
            # If the marker sits inside a code fence (e.g. \\begin{abstract}
            # wrapped in a {=latex} fence), the next ``` line CLOSES that
            # fence — drop just that line so extract_prose sees balanced
            # fences and can strip the real blocks (tikz figures) itself.
            fence_parity = sum(
                1 for l in text[:m.end()].split("\n")
                if l.strip().startswith("```")) % 2
            lines = after.split("\n")
            if fence_parity == 1:
                for li, l in enumerate(lines):
                    if l.strip().startswith("```"):
                        del lines[li]
                        break
            cleaned = "\n".join(
                l for l in lines if not l.strip().startswith("\\"))
            sents = split_sentences_all(extract_prose(cleaned)[:2000])
            if sents:
                openers[kind] = (fname, " ".join(sents[0].split()))
    if "abstract" in openers and "introduction" in openers:
        (fa, sa), (fi, si) = openers["abstract"], openers["introduction"]
        ratio = difflib.SequenceMatcher(None, sa.lower(), si.lower()).ratio()
        if ratio >= threshold:
            return {
                "similarity": round(ratio, 2),
                "abstract": {"file": fa, "sentence": sa[:140]},
                "introduction": {"file": fi, "sentence": si[:140]},
            }
    return None


def repeated_formulae(file_proses: list, min_count: int = 3) -> list:
    """Coined 4-word phrases recurring within a document or across files.

    file_proses: list of (filename, prose). Returns phrases with >= min_count
    total occurrences and at least 2 content words, with per-file counts.
    """
    gram_counts = Counter()
    gram_files = {}
    for fname, prose in file_proses:
        tokens = re.findall(r"[a-z][a-z'-]*", prose.lower())
        seen_here = Counter()
        for i in range(len(tokens) - 3):
            gram = tuple(tokens[i:i + 4])
            content = sum(1 for w in gram if w not in FUNCTION_WORDS)
            if content < 2:
                continue
            seen_here[gram] += 1
        for gram, c in seen_here.items():
            gram_counts[gram] += c
            gram_files.setdefault(gram, {})[fname] = c
    def trigrams(g):
        return {g[i:i + 3] for i in range(len(g) - 2)}

    out = []
    reported_tris = set()
    for gram, count in gram_counts.most_common():
        if count < min_count:
            break
        # skip grams overlapping an already-reported one (same source phrase)
        if trigrams(gram) & reported_tris:
            continue
        reported_tris |= trigrams(gram)
        out.append({
            "phrase": " ".join(gram),
            "count": count,
            "files": gram_files[gram],
        })
    return out[:25]


_DEF_MARKERS = re.compile(
    r"\b(that is|i\.e\.|e\.g\.|meaning|we call|we term|we define|defined as|"
    r"refers? to|namely|in other words|which we (?:call|term|define)|"
    r"is defined|means that|denotes|stands for|by which we mean)\b", re.I)


def detect_coinage(file_proses: list, min_count: int = 2) -> list:
    """Repeated content bigrams/trigrams that never appear near a definition.

    The compressed-conversation class: coined insider phrases ("claims
    posture", "running matrix", "connective tissue") used more than once but
    never defined, so a cold reader cannot act on them. Advisory — these are
    candidates for the semantic pass (Prompt 8/8b), not hard failures. A phrase
    that co-occurs (in any sentence) with a definition marker is treated as
    defined and dropped.
    """
    counts = Counter()
    files = {}
    defined = set()
    for fname, prose in file_proses:
        for sent in split_sentences_all(prose):
            has_def = bool(_DEF_MARKERS.search(sent))
            toks = re.findall(r"[a-z][a-z'-]*", sent.lower())
            for n in (2, 3):
                for i in range(len(toks) - n + 1):
                    gram = tuple(toks[i:i + n])
                    if sum(1 for w in gram if w not in FUNCTION_WORDS) < 2:
                        continue
                    counts[gram] += 1
                    files.setdefault(gram, {})
                    files[gram][fname] = files[gram].get(fname, 0) + 1
                    if has_def:
                        defined.add(gram)

    out = []
    reported_bigrams = set()  # dedup nested/overlapping phrases
    for gram, c in counts.most_common():
        if c < min_count:
            break
        if gram in defined:
            continue
        bgs = {(gram[i], gram[i + 1]) for i in range(len(gram) - 1)}
        if bgs & reported_bigrams:
            continue
        reported_bigrams |= bgs
        out.append({"phrase": " ".join(gram), "count": c, "files": files[gram]})
    return out[:20]


def voice_distance(file_proses: list, profile_path: str) -> dict:
    """Compare the draft's rhythm metrics against a match-voice corpus profile.

    Positive-specification check (GH-121): the denylist detectors catch named
    tells; distance from the target corpus catches unnamed ones. Reads the
    voice-profile.json that match-voice's `style.py corpus` writes (a plain
    file — no cross-skill import; skills are mirrored independently). Compares
    the three metrics this script can compute in the profile's terms; the full
    comparison (passive/hedges/citations/vocabulary) is `style.py compare`.

    z-scores use the profile's per-metric std across papers (metrics_std);
    when absent (older profiles), falls back to relative deviation.
    """
    try:
        with open(profile_path) as f:
            profile = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"could not read voice profile: {e}"}

    corpus_m = profile.get("metrics", {})
    corpus_s = profile.get("metrics_std", {}) or {}

    prose = "\n\n".join(p for _, p in file_proses)
    sent_lens = [len(s.split()) for s in split_sentences_all(prose)]
    paras = split_paragraphs(prose)
    para_sents = [len(split_sentences_all(p)) for p in paras if p.strip()]

    draft = {}
    if sent_lens:
        m = sum(sent_lens) / len(sent_lens)
        draft["sentence_length_mean"] = round(m, 2)
        draft["sentence_length_stdev"] = round(
            (sum((v - m) ** 2 for v in sent_lens) / len(sent_lens)) ** 0.5, 2)
    if para_sents:
        draft["paragraph_length_mean_sentences"] = round(
            sum(para_sents) / len(para_sents), 2)

    comparisons = {}
    deviating = []
    for k, d in draft.items():
        c = corpus_m.get(k)
        if c is None:
            continue
        entry = {"draft": d, "corpus": c}
        s = corpus_s.get(k)
        if s:
            z = round((d - c) / s, 2)
            entry["z"] = z
            if abs(z) >= 2.0:
                deviating.append(k)
        elif c:
            rel = round((d - c) / abs(c), 2)
            entry["rel_dev"] = rel
            if abs(rel) >= 0.5:
                deviating.append(k)
        comparisons[k] = entry

    return {
        "profile": profile_path,
        "corpus_papers": profile.get("papers"),
        "metrics": comparisons,
        "deviating": deviating,
        "note": "rhythm metrics only; run match-voice style.py compare for the full profile",
    }


_DET_CLASS = {"the", "a", "an", "this", "that", "these", "those"}
_PRON_CLASS = {"i", "you", "we", "they", "it", "he", "she"}


def _first_word_class(sentence: str) -> str:
    words = sentence.split()
    if not words:
        return ""
    w = words[0].rstrip(".,;:!?\"'").lower()
    if w in _DET_CLASS:
        return "DET"
    if w in _PRON_CLASS:
        return "PRON"
    return w


def detect_frame_parallelism(sentences: list) -> list:
    """Frame-level parallels the identical-first-2-words check misses.

    AI parallelism varies the surface while repeating the syntactic frame:
    "The methodology is learnable. The discipline is maintainable. The
    results are real." — same frame, distinct nouns. Two passes:

      1. first-word runs: >= 3 consecutive sentences opening with the same
         word ("More tools... More specifications... More parallelism...");
         for the high-frequency openers The/I/It/A the run only counts when
         every sentence is short (<= 8 words), which is the attribute-triple
         and anaphora shape.
      2. skeleton runs: >= 3 consecutive short sentences (<= 10 words)
         sharing first-word CLASS (determiner or pronoun) with distinct
         second words — catches mixed-determiner frames pass 1 misses.
    """
    issues = []
    if len(sentences) < 3:
        return issues
    firsts = [s.split()[0].rstrip(".,;:!?\"'").lower() if s.split() else ""
              for s in sentences]
    seconds = [s.split()[1].rstrip(".,;:!?\"'").lower() if len(s.split()) > 1 else ""
               for s in sentences]
    lengths = [len(s.split()) for s in sentences]
    flagged_ranges = []

    def overlaps(a, b):
        return not (a[1] <= b[0] or b[1] <= a[0])

    # Pass 1: first-word runs
    common = {"the", "i", "it", "a"}
    i = 0
    while i < len(sentences):
        j = i
        while (j + 1 < len(sentences) and firsts[j + 1] == firsts[i]
               and firsts[i]):
            j += 1
        run_len = j - i + 1
        if run_len >= 3:
            short_ok = all(lengths[k] <= 8 for k in range(i, j + 1))
            if firsts[i] not in common or short_ok:
                # distinct continuations — otherwise the original
                # identical-first-2-words check already reports it
                if len({seconds[k] for k in range(i, j + 1)}) >= 2:
                    snippet = " ".join(sentences[i:j + 1])[:110]
                    issues.append({
                        "type": "frame-parallelism",
                        "detail": (f'{run_len} consecutive sentences open with '
                                   f'"{sentences[i].split()[0]}" and repeat the frame '
                                   f'with varied content: "{snippet}..."'),
                        "severity": "high" if run_len >= 4 else "medium",
                        "position": f"sentences {i + 1}-{j + 1}",
                    })
                    flagged_ranges.append((i, j + 1))
        i = j + 1

    # Pass 2: skeleton runs (first-word CLASS + short + distinct nouns)
    classes = [_first_word_class(s) for s in sentences]
    i = 0
    while i < len(sentences):
        j = i
        while (j + 1 < len(sentences)
               and classes[j + 1] == classes[i]
               and classes[i] in ("DET", "PRON")
               and lengths[j + 1] <= 10):
            j += 1
        run_len = j - i + 1
        if (run_len >= 3 and all(lengths[k] <= 10 for k in range(i, j + 1))
                and len({seconds[k] for k in range(i, j + 1)}) == run_len
                and not any(overlaps((i, j + 1), r) for r in flagged_ranges)):
            snippet = " ".join(sentences[i:j + 1])[:110]
            issues.append({
                "type": "frame-parallelism",
                "detail": (f"{run_len} consecutive short sentences share the "
                           f"{classes[i]}-opener frame with distinct subjects: "
                           f'"{snippet}..."'),
                "severity": "medium",
                "position": f"sentences {i + 1}-{j + 1}",
            })
        i = j + 1

    return issues


def analyze(text: str, threshold_name: str = "medium") -> dict:
    """Run all structural checks. Return issues dict."""
    thresholds = THRESHOLDS[threshold_name]
    prose = extract_prose(text)
    issues = []
    metrics = {}

    if len(prose.split()) < 50:
        # Structural metrics (burstiness, opening diversity) are meaningless on
        # a handful of sentences, so scoring is skipped — but this is NOT a
        # clean bill. Single-sentence leads, goal statements, and captions are
        # exactly where lexical/semantic tells live (GH-135). The lexical scan
        # (detect-lexical.sh, no length gate) and Step 3 still apply.
        return {"issues": [], "metrics": {"word_count": len(prose.split())},
                "verdict": "too-short",
                "note": "structural scoring skipped (too short); run detect-lexical.sh "
                        "and the semantic pass — this is not a clean verdict"}

    sentences = split_sentences(prose)
    paragraphs = split_paragraphs(prose)
    word_count = len(prose.split())

    # --- Sentence length variance (burstiness) ---
    if len(sentences) >= 5:
        lengths = [len(s.split()) for s in sentences]
        std = statistics.stdev(lengths)
        mean = statistics.mean(lengths)
        metrics["sentence_length_mean"] = round(mean, 1)
        metrics["sentence_length_std"] = round(std, 1)

        if std < thresholds["sentence_length_std_min"]:
            issues.append({
                "type": "low-burstiness",
                "detail": f"Sentence length std={std:.1f} (threshold: >{thresholds['sentence_length_std_min']}). Text is unnaturally uniform.",
                "severity": "high",
                "metric": std,
            })
        elif std > thresholds["sentence_length_std_max"]:
            issues.append({
                "type": "overshoot-burstiness",
                "detail": f"Sentence length std={std:.1f} (threshold: <{thresholds['sentence_length_std_max']}). Extreme variance suggests text tuned against the burstiness check.",
                "severity": "medium",
                "metric": std,
            })

    # --- Paragraph length uniformity ---
    if len(paragraphs) >= 3:
        para_lengths = [len(p.split()) for p in paragraphs]
        para_std = statistics.stdev(para_lengths)
        metrics["paragraph_length_std"] = round(para_std, 1)

        if para_std < thresholds["paragraph_length_std_min"]:
            issues.append({
                "type": "uniform-paragraphs",
                "detail": f"Paragraph length std={para_std:.1f} (threshold: >{thresholds['paragraph_length_std_min']}). Paragraphs are suspiciously similar in length.",
                "severity": "medium",
                "metric": para_std,
            })

    # --- Parallelism ---
    openings = get_sentence_openings(sentences)
    parallelism_issues = detect_parallelism(openings, thresholds["parallelism_max_repeats"])
    issues.extend(parallelism_issues)

    # --- Frame-level parallelism (varied surface, repeated frame) ---
    frame_issues = detect_frame_parallelism(sentences)
    issues.extend(frame_issues)
    metrics["frame_parallelism_runs"] = len(frame_issues)

    # --- Tail-echo parallelism (varied heads, mirrored endings) ---
    # Advisory, not a hard issue: the GH-123 noise audit found tail overlap
    # fires on ordinary domain repetition in human technical prose (8/8 proxy
    # papers, e.g. shared ['an','element']). Candidates go to the semantic
    # pass (Prompt 6 / Step 3) for the mirror-pair judgment.
    tail_echo_candidates = detect_tail_echo(sentences)
    metrics["tail_echo_pairs"] = len(tail_echo_candidates)
    result_extra_tail_echo = tail_echo_candidates

    # --- Antithesis / negation-flip pairs (zero tolerance) ---
    # Uses the unfiltered sentence list so clipped second clauses survive, but
    # strips list-item lines first: two short bullets ("- OpenCode installed.")
    # are not a prose antithesis, and list density is measured separately.
    prose_no_lists = "\n".join(
        l for l in prose.split("\n")
        if not re.match(r"^\s*[-*+•]\s|^\s*\d+[.)]\s", l)
    )
    sentences_all = split_sentences_all(prose_no_lists)
    antithesis_issues = detect_antithesis(sentences_all)
    issues.extend(antithesis_issues)
    metrics["antithesis_pairs"] = len(antithesis_issues)

    # --- Opening diversity ---
    if len(openings) >= 5:
        first_words = [o.split()[0] if o.split() else "" for o in openings]
        unique_ratio = len(set(first_words)) / len(first_words)
        metrics["opening_diversity"] = round(unique_ratio, 2)

        if unique_ratio < thresholds["opening_diversity_min"]:
            # Find the most repeated openings
            counter = Counter(first_words)
            top = counter.most_common(3)
            issues.append({
                "type": "low-opening-diversity",
                "detail": f"Only {unique_ratio:.0%} of sentences start with unique words. Most common: {top}",
                "severity": "medium",
                "metric": unique_ratio,
            })

    # --- List ratio ---
    list_count, total_lines = count_list_lines(text)
    if total_lines > 0:
        list_ratio = list_count / total_lines
        metrics["list_ratio"] = round(list_ratio, 2)

        if list_ratio > thresholds["list_ratio_max"]:
            issues.append({
                "type": "list-heavy",
                "detail": f"{list_ratio:.0%} of lines are list items (threshold: <{thresholds['list_ratio_max']:.0%}). Over-reliance on lists.",
                "severity": "low",
                "metric": list_ratio,
            })

    # --- Colon density ---
    colon_count = prose.count(":")
    colon_density = (colon_count / word_count) * 500 if word_count > 0 else 0
    metrics["colon_density_per_500w"] = round(colon_density, 1)

    if colon_density > thresholds["colon_density_max"]:
        issues.append({
            "type": "colon-heavy",
            "detail": f"{colon_density:.1f} colons per 500 words (threshold: <{thresholds['colon_density_max']}). AI over-uses colons as introducers.",
            "severity": "low",
            "metric": colon_density,
        })

    # --- Dash density ---
    dash_count = len(re.findall(r"[—–]", prose))
    dash_density = (dash_count / word_count) * 500 if word_count > 0 else 0
    metrics["dash_density_per_500w"] = round(dash_density, 1)

    if dash_density > thresholds["dash_density_max"]:
        issues.append({
            "type": "dash-heavy",
            "detail": f"{dash_density:.1f} dashes per 500 words (threshold: <{thresholds['dash_density_max']}). AI favors em-dashes.",
            "severity": "low",
            "metric": dash_density,
        })

    # --- Tricolon density ---
    # AI gravitates toward groups of three. The habit is phrase-level, not
    # single words: "no baseline to compare against, no iterative validation
    # during development, and too much hope". Two shapes:
    #   1. phrase tricolon: A, B, and C where each part is a phrase
    #   2. anaphoric comma list: 3+ segments opening with the same word
    #      ("no X, no Y, no Z" / "doesn't A, doesn't B, doesn't C")
    tricolon_count = len(re.findall(
        r"[^,.;:\n]{3,60},\s+[^,.;:\n]{3,60},\s+and\s+[^,.;:\n]{3,60}", prose))
    anaphoric_lists = 0
    asyndetic_lists = 0
    for s in split_sentences_all(prose):
        segs = [seg.strip() for seg in s.split(",") if seg.strip()]
        if len(segs) < 3:
            continue
        heads = []
        for seg in segs:
            w = seg.split()
            h = w[0].lower() if w else ""
            # strip a leading "and" so the closing segment compares by content
            if h == "and" and len(w) > 1:
                h = w[1].lower()
            heads.append(h)
        found_anaphora = False
        for k in range(len(heads) - 2):
            h = heads[k]
            if h and len(h) > 1 and h == heads[k + 1] == heads[k + 2]:
                found_anaphora = True
                break
        if not found_anaphora:
            # subject-carrying first segment: "It doesn't A, doesn't B,
            # doesn't C" — repeated head starts at segment 2 but appears
            # inside segment 1.
            for k in range(len(heads) - 1):
                h = heads[k + 1]
                if (h and len(h) > 1 and k + 2 <= len(heads) - 1
                        and h == heads[k + 2]
                        and h in (w.lower() for w in segs[k].split())):
                    found_anaphora = True
                    break
        if found_anaphora:
            anaphoric_lists += 1
            continue
        # Asyndetic verb tricolon: 3+ segments, no "and" joining the last,
        # continuation segments short and lowercase ("He optimizes the
        # asset, squeezes the margin, runs it lean.")
        if (not re.match(r"(?i)and\b", segs[-1])
                and all(len(seg.split()) <= 8 for seg in segs[1:])
                and all(seg[0].islower() for seg in segs[1:] if seg)):
            asyndetic_lists += 1
    tricolon_count += anaphoric_lists + asyndetic_lists
    tricolon_density = (tricolon_count / word_count) * 500 if word_count > 0 else 0
    metrics["tricolon_density_per_500w"] = round(tricolon_density, 1)
    metrics["anaphoric_list_count"] = anaphoric_lists
    metrics["asyndetic_list_count"] = asyndetic_lists

    if tricolon_density > thresholds.get("tricolon_density_max", 3.0):
        issues.append({
            "type": "tricolon-heavy",
            "detail": f"{tricolon_density:.1f} tricolons per 500 words (threshold: <3.0). AI defaults to groups of three.",
            "severity": "low",
            "metric": tricolon_density,
        })

    # --- Parenthetical definition density ---
    # AI inserts inline definitions in parentheses: "the orchestrator (the component
    # responsible for...)" at unnaturally high frequency.
    paren_def_count = len(re.findall(r"\w+\s+\([^)]{10,}[^)]*\)", prose))
    paren_def_density = (paren_def_count / word_count) * 500 if word_count > 0 else 0
    metrics["paren_def_density_per_500w"] = round(paren_def_density, 1)

    if paren_def_density > thresholds.get("paren_def_density_max", 4.0):
        issues.append({
            "type": "paren-def-heavy",
            "detail": f"{paren_def_density:.1f} parenthetical definitions per 500 words (threshold: <4.0). AI over-defines inline.",
            "severity": "low",
            "metric": paren_def_density,
        })

    # --- Passive enabling verb density ---
    # Clustered "is achieved", "is enabled", "is realized", "is facilitated" etc.
    passive_enabling = len(re.findall(
        r"\bis\s+(achieved|enabled|realized|facilitated|accomplished|attained|ensured|maintained|provided|supported)\b",
        prose, re.IGNORECASE
    ))
    passive_density = (passive_enabling / word_count) * 500 if word_count > 0 else 0
    metrics["passive_enabling_per_500w"] = round(passive_density, 1)

    if passive_density > thresholds.get("passive_enabling_max", 2.0):
        issues.append({
            "type": "passive-enabling-heavy",
            "detail": f"{passive_density:.1f} passive enabling verbs per 500 words (threshold: <2.0). AI avoids naming the actor.",
            "severity": "medium",
            "metric": passive_density,
        })

    # --- "rather than" frequency ---
    # AI uses "rather than" at 2-3x the natural rate to set up every contrast.
    rather_than_count = len(re.findall(r"\brather than\b", prose, re.IGNORECASE))
    rather_than_density = (rather_than_count / word_count) * 500 if word_count > 0 else 0
    metrics["rather_than_per_500w"] = round(rather_than_density, 1)

    if rather_than_density > thresholds.get("rather_than_max", 2.0):
        issues.append({
            "type": "rather-than-heavy",
            "detail": f"{rather_than_density:.1f} 'rather than' per 500 words (threshold: <2.0). AI's default contrast device.",
            "severity": "low",
            "metric": rather_than_density,
        })

    # --- Intra-sentence contrast flips ---
    # The antithesis reflex compressed into one sentence: "isn't X—it's Y",
    # "Not because X—because Y", "X, not Y." Both constructions are
    # legitimate in isolation; the tell is frequency, so this is a density
    # metric like rather_than (the same class of default contrast device).
    dash_flip = len(re.findall(
        r"\b(?:is not|isn't|not)\s[^.?!]{0,40}[—–-]\s*(?:it's|it is|because|that's)",
        prose, re.IGNORECASE))
    comma_not = len(re.findall(r",\s+not\s+[^,.?!]{3,40}[.?!]", prose))
    contrast_flip_density = ((dash_flip + comma_not) / word_count) * 500 if word_count > 0 else 0
    metrics["dash_flip_count"] = dash_flip
    metrics["comma_not_count"] = comma_not
    metrics["contrast_flip_per_500w"] = round(contrast_flip_density, 1)

    if contrast_flip_density > thresholds.get("contrast_flip_max", 2.0):
        issues.append({
            "type": "contrast-flip-heavy",
            "detail": (f"{contrast_flip_density:.1f} intra-sentence contrast flips per 500 words "
                       f"(threshold: <2.0; dash flips: {dash_flip}, comma-not: {comma_not}). "
                       "\"isn't X—it's Y\" / \"X, not Y.\" is the antithesis reflex "
                       "compressed into one sentence."),
            "severity": "medium",
            "metric": contrast_flip_density,
        })

    # --- "both X and Y" frequency ---
    # AI produces balanced pair constructions at unnaturally high density.
    both_and_count = len(re.findall(r"\bboth\s+\w+\s+and\s+\w+", prose, re.IGNORECASE))
    both_and_density = (both_and_count / word_count) * 500 if word_count > 0 else 0
    metrics["both_and_per_500w"] = round(both_and_density, 1)

    if both_and_density > thresholds.get("both_and_max", 1.5):
        issues.append({
            "type": "both-and-heavy",
            "detail": f"{both_and_density:.1f} 'both X and Y' per 500 words (threshold: <1.5). AI over-balances pairs.",
            "severity": "low",
            "metric": both_and_density,
        })

    # --- Paragraph schema proxies (advisory; semantic prompt adjudicates) ---
    schema = analyze_paragraph_schema(paragraphs)
    if schema:
        metrics["paragraph_schema"] = {
            k: schema[k] for k in ("paragraphs_scored", "mean_topic_overlap",
                                   "mean_cohesion", "mean_subject_churn",
                                   "low_topic_paragraphs")
        }
        if len(schema["low_topic_paragraphs"]) >= 3:
            issues.append({
                "type": "topic-sentence-weak",
                "detail": (f"{len(schema['low_topic_paragraphs'])} paragraphs open "
                           "mid-argument (first-sentence content barely overlaps the "
                           "body — the TOPIC defect). Advisory: adjudicate in the "
                           "schema prompt; topic-sentence-first is convention, not law."),
                "severity": "low",
                "candidates": schema["low_topic_paragraphs"],
            })

    # --- Question volleys and self-interview templates ---
    question_issues = detect_question_patterns(paragraphs)
    issues.extend(question_issues)
    metrics["question_pattern_flags"] = len(question_issues)

    # --- Ordinal walkthrough template ---
    # "The first was X. ... The second was Y. ... The third was Z." — the
    # enumerated-walkthrough template. A single "The first thing" is
    # legitimate; flag a paragraph only when 2+ DISTINCT ordinals appear in
    # the template shape.
    _ordinal_tpl = re.compile(
        r"\bthe\s+(first|second|third|fourth|fifth)\s+"
        r"(thing|one|was|is|step|reason|problem|issue|lesson|part)\b",
        re.IGNORECASE)
    ordinal_paras = 0
    for p_idx, para in enumerate(paragraphs):
        ordinals = {m.group(1).lower() for m in _ordinal_tpl.finditer(para)}
        if len(ordinals) >= 2:
            ordinal_paras += 1
            issues.append({
                "type": "ordinal-walkthrough",
                "detail": (f"Paragraph {p_idx + 1} walks through "
                           f"{sorted(ordinals)} with the 'The <ordinal> <noun>' "
                           "template — enumerated-walkthrough AI cadence."),
                "severity": "medium",
                "position": f"paragraph {p_idx + 1}",
            })
    # Cross-paragraph variant: each ordinal opens its OWN paragraph
    # ("The first was X." <para> "The second was Y." <para> ...). Flag when
    # 2+ distinct ordinals open paragraphs within a 6-paragraph window.
    openers = []
    for p_idx, para in enumerate(paragraphs):
        m = _ordinal_tpl.search(para[:60])
        if m:
            openers.append((p_idx, m.group(1).lower()))
    for i in range(len(openers)):
        window = [o for o in openers if 0 <= o[0] - openers[i][0] < 6]
        distinct = {o[1] for o in window}
        if len(distinct) >= 2:
            ordinal_paras += 1
            issues.append({
                "type": "ordinal-walkthrough",
                "detail": (f"Paragraphs {[o[0] + 1 for o in window]} open with "
                           f"'The {sorted(distinct)} ...' — the enumerated-walkthrough "
                           "template spread across paragraphs."),
                "severity": "medium",
                "position": f"paragraphs {window[0][0] + 1}-{window[-1][0] + 1}",
            })
            break  # one report per document is enough

    metrics["ordinal_walkthrough_paragraphs"] = ordinal_paras

    # --- Performance intensity ("LinkedIn voice") ---
    perf = analyze_performance(sentences_all)
    metrics.update(perf)
    if perf and perf["plain_sentence_rate"] < thresholds["plain_sentence_rate_min"]:
        issues.append({
            "type": "performing-heavy",
            "detail": (f"Only {perf['plain_sentence_rate']:.0%} of sentences are plain "
                       f"declaratives (threshold: >{thresholds['plain_sentence_rate_min']:.0%}). "
                       "Nearly every sentence performs (pivot, antithesis, fragment, reversal) — "
                       "constant rhetorical intensity is an overshoot tell."),
            "severity": "high",
            "metric": perf["plain_sentence_rate"],
        })

    # --- Punch detection ---
    punch = analyze_punch(paragraphs)
    if punch:
        metrics["punch_rate_per_100"] = punch["punch_rate_per_100"]
        metrics["punch_clustering"] = punch["punch_clustering"]
        if punch["punch_clustering"] > thresholds["punch_clustering_max"]:
            issues.append({
                "type": "punch-clustered",
                "detail": (f"{punch['punch_clustering']:.0%} of paragraphs close on a punch "
                           f"(threshold: <{thresholds['punch_clustering_max']:.0%}). "
                           "A punch every few paragraphs is the LinkedIn voice. "
                           "Candidates carried to the semantic pass for the removal test."),
                "severity": "medium",
                "metric": punch["punch_clustering"],
                "candidates": punch["punch_candidates"],
            })

    # --- Word salad ---
    salad = analyze_salad(sentences_all, prose, word_count)
    if salad:
        metrics["salad_rate_per_100"] = salad["salad_rate_per_100"]
        metrics["hyphen_compound_per_500w"] = salad["hyphen_compound_per_500w"]
        if salad["salad_rate_per_100"] > thresholds["salad_rate_max"]:
            issues.append({
                "type": "word-salad-heavy",
                "detail": (f"{salad['salad_rate_per_100']:.1f} salad sentences per 100 "
                           f"(threshold: <{thresholds['salad_rate_max']}). Sentences stack "
                           "content words without function-word joints; unpack them."),
                "severity": "high",
                "metric": salad["salad_rate_per_100"],
                "candidates": salad["salad_candidates"],
            })
        if salad["hyphen_compound_per_500w"] > thresholds["hyphen_compound_max"]:
            issues.append({
                "type": "hyphen-compound-heavy",
                "detail": (f"{salad['hyphen_compound_per_500w']:.1f} hyphenated compounds per 500 words "
                           f"(threshold: <{thresholds['hyphen_compound_max']}). Each coined compound "
                           "is a packed relative clause; expand them."),
                "severity": "medium",
                "metric": salad["hyphen_compound_per_500w"],
            })

    # --- Verdict ---
    high_count = sum(1 for i in issues if i.get("severity") == "high")
    med_count = sum(1 for i in issues if i.get("severity") == "medium")

    if high_count >= 2 or (high_count >= 1 and med_count >= 2):
        verdict = "likely-ai"
    elif high_count >= 1 or med_count >= 2:
        verdict = "suspicious"
    elif issues:
        verdict = "minor-issues"
    else:
        verdict = "clean"

    # Overshoot re-labeling: when the flags point at the over-polished
    # direction, name it — the fix (plainer prose) is the opposite of the
    # bland-AI fix, so the verdicts must not be conflated.
    overshoot_hits = [i for i in issues if i["type"] in OVERSHOOT_TYPES]
    if len(overshoot_hits) >= 2 and len(overshoot_hits) >= len(issues) / 2:
        verdict = "suspicious-overshoot"

    metrics["word_count"] = word_count
    metrics["sentence_count"] = len(sentences)
    metrics["paragraph_count"] = len(paragraphs)

    return {"issues": issues, "metrics": metrics, "verdict": verdict,
            "tail_echo_candidates": result_extra_tail_echo}


def main():
    if len(sys.argv) < 2:
        print("Usage: detect-structural.py <file-or-dir> [file-or-dir ...] [--json] [--threshold=strict|medium|relaxed]", file=sys.stderr)
        sys.exit(2)

    json_mode = "--json" in sys.argv
    threshold = "strict"
    voice_profile = None

    # Separate flags from paths
    paths = []
    for arg in sys.argv[1:]:
        if arg.startswith("--threshold="):
            threshold = arg.split("=")[1]
            if threshold not in THRESHOLDS:
                print(f"Error: Unknown threshold '{threshold}'. Use: strict, medium, relaxed", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--voice-profile="):
            voice_profile = arg.split("=", 1)[1]
        elif arg == "--json":
            continue
        else:
            paths.append(arg)

    if not paths:
        print("Usage: detect-structural.py <file-or-dir> [file-or-dir ...] [--json] [--threshold=strict|medium|relaxed]", file=sys.stderr)
        sys.exit(2)

    # Resolve all paths into a list of .md files
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(list(path.rglob("*.md")) + list(path.rglob("*.tex"))))
        elif path.is_file():
            files.append(path)
        else:
            print(f"Error: Not found: {p}", file=sys.stderr)
            sys.exit(2)

    if not files:
        print("Error: No .md files found in the given paths.", file=sys.stderr)
        sys.exit(2)

    any_issues = False
    all_results = []
    file_proses = []
    file_raws = []

    for filepath in files:
        text = filepath.read_text(encoding="utf-8")
        # LaTeX input: analyze the prose view so \item runs, table rows, math,
        # and float environments are not counted as sentences. The aligned view
        # keeps one entry per source line (blank where markup was dropped), so
        # paragraph boundaries survive — the compact view would collapse the
        # whole document into one paragraph and skew paragraph metrics.
        if filepath.suffix == ".tex":
            text = "\n".join(detex.detex_aligned(text))
        result = analyze(text, threshold)
        file_proses.append((str(filepath), extract_prose(text)))
        file_raws.append((str(filepath), text))

        if result["issues"]:
            any_issues = True

        if json_mode:
            all_results.append({"file": str(filepath), **result})
        else:
            print(f"=== Structural AI Detection: {filepath} ===")
            print(f"    Threshold: {threshold}")
            print(f"    Verdict: {result['verdict'].upper()}")
            if result.get("note"):
                print(f"    Note: {result['note']}")
            if result.get("tail_echo_candidates"):
                print(f"    Tail-echo candidates (advisory, semantic pass): {len(result['tail_echo_candidates'])}")
            print()

            print("--- Metrics ---")
            for k, v in result["metrics"].items():
                print(f"  {k}: {v}")
            print()

            if result["issues"]:
                print("--- Issues ---")
                for issue in result["issues"]:
                    sev = issue["severity"].upper()
                    print(f"  [{sev}] {issue['type']}: {issue['detail']}")
                    if "position" in issue:
                        print(f"         at {issue['position']}")
                print()
            else:
                print("✓ No structural AI patterns detected.")
                print()

    # --- Repeated formulae (whole-invocation: within and across files) ---
    formulae = repeated_formulae(file_proses)
    if formulae:
        any_issues = True

    # --- Undefined coinage candidates (advisory; for the semantic pass) ---
    coinage = detect_coinage(file_proses)

    # --- Voice distance vs a match-voice corpus profile (optional) ---
    vdist = voice_distance(file_proses, voice_profile) if voice_profile else None

    # --- Abstract/introduction opener duplication (cross-document) ---
    opener_dup = detect_opener_duplication(file_raws)
    if opener_dup:
        any_issues = True

    if json_mode:
        payload = all_results if len(all_results) > 1 else all_results[0]
        if len(all_results) > 1:
            payload = {"files": all_results, "repeated_formulae": formulae,
                       "opener_duplication": opener_dup,
                       "coinage_candidates": coinage}
        else:
            payload["repeated_formulae"] = formulae
            payload["opener_duplication"] = opener_dup
            payload["coinage_candidates"] = coinage
        if vdist is not None:
            payload["voice_distance"] = vdist
        print(json.dumps(payload, indent=2))
    else:
        if opener_dup:
            print("=== Abstract/Introduction Opener Duplication ===")
            print(f"  similarity {opener_dup['similarity']}:")
            print(f"  abstract     ({Path(opener_dup['abstract']['file']).name}): \"{opener_dup['abstract']['sentence']}\"")
            print(f"  introduction ({Path(opener_dup['introduction']['file']).name}): \"{opener_dup['introduction']['sentence']}\"")
            print("  A reviewer reads the same opener twice. Rewrite one.")
            print()
        if formulae:
            print("=== Repeated Formulae (coined phrases, whole invocation) ===")
            for f in formulae:
                locs = ", ".join(f"{Path(k).name} x{v}" for k, v in f["files"].items())
                print(f"  [{f['count']}x] \"{f['phrase']}\"  ({locs})")
            print("  Each coined phrase gets one home; paraphrase the rest.")
            print()
        if coinage:
            print("=== Undefined Coinage Candidates (for the semantic pass) ===")
            for f in coinage:
                locs = ", ".join(f"{Path(k).name} x{v}" for k, v in f["files"].items())
                print(f"  [{f['count']}x] \"{f['phrase']}\"  ({locs})")
            print("  Repeated insider phrases never defined. Confirm in Prompt 8/8b:")
            print("  does the sentence state a mechanism a cold reader could act on?")
            print()
        if vdist is not None:
            print("=== Voice Distance (vs corpus profile) ===")
            if "error" in vdist:
                print(f"  {vdist['error']}")
            else:
                for k, e in vdist["metrics"].items():
                    score = f"z={e['z']}" if "z" in e else f"rel={e.get('rel_dev')}"
                    mark = "  <-- deviating" if k in vdist["deviating"] else ""
                    print(f"  {k}: draft {e['draft']} vs corpus {e['corpus']} ({score}){mark}")
                if vdist["deviating"]:
                    print("  Far from the target voice on the marked metrics — even if all")
                    print("  named checks pass, this is not clean. Seed Step 3 with these.")
                print(f"  ({vdist['note']})")
            print()

    sys.exit(1 if any_issues else 0)


if __name__ == "__main__":
    main()
