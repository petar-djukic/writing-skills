# Voice comparison report template

One file per compared draft, written to `<db-dir>/voice-reports/<draft-stem>-voice.md`.
The report should let the author fix the biggest voice mismatches in one
editing pass without re-reading the corpus.

Use this exact structure.

```markdown
---
draft: <path to the draft>
corpus_papers: <N>
corpus_words: <N>
date_compared: <YYYY-MM-DD>
verdict: <close match | partial match | divergent>
---

# Voice Comparison: <draft title or filename>

## Summary

<2-3 sentences: overall how close the draft is to the corpus voice, and
the two or three highest-impact changes.>

## Metric Deltas

<Table of quantitative deltas from style.py compare — only rows where the
draft falls meaningfully outside the corpus norm, with a one-line reading
of each.>

| Metric | Draft | Corpus | Reading |
|--------|-------|--------|---------|
| Sentence length mean | 31.2 | 22.4 | Sentences run long, concentrated in the intro |

## Per-Section Deltas

<Same table shape, one subsection per section where the draft diverges.
Methodology and Results always get a subsection, even if the verdict is
"matches corpus norms".>

### Methodology
### Results

## Voice Mismatches

<One entry per qualitative mismatch. Quote draft and corpus side by side.>

**<dimension>** — <one-line finding>

> Draft: "<quote>"
> Corpus (<paper id>): "<quote>"

Direction: <what to change, not the changed text>

## Methodology Conventions Check

<Per convention from the voice profile: met / not met / partially, with
evidence from the draft.>

## Results Conventions Check

<Same shape as methodology.>

## Jargon Alignment

**Field vocabulary missing from the draft:** <terms with corpus rates>

**Draft terms the corpus never uses:** <terms with draft rates — flag any
that read as AI-tell phrasing>

**Overused stock phrases:** <idioms the draft uses at a higher rate than
the corpus>
```

Notes:
- Findings are ranked by impact; the Summary names the top ones.
- Every qualitative claim quotes evidence. No unquoted assertions.
- "Matches corpus norms" is a valid and useful entry — say it where true.
