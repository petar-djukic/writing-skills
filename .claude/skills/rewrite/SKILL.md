---
name: rewrite
description: >-
  Three-step pipeline to rewrite an AI-drafted article into prose that reads
  as human: match-outline (Kimi, section-level rewrite), filter-tells
  (semantic cleanup of antithesis pairs, CoT leakage, recap ballast), then
  match-voice (gpt-oss paragraph diction, no anchors). Each step is
  necessary — skip any one and the result either stays AI-flagged or gets
  gate-rejected.
  Triggers: rewrite article, full rewrite pipeline, rewrite for pangram,
  make it human, run the rewrite pipeline, three-step rewrite.
---

# Rewrite (three-step pipeline)

Orchestrates the three prose skills that together move an AI-drafted article
from 100% AI-flagged to human-passing on Pangram. Each step exists because
the other two cannot compensate for its absence.

## Why three steps

| step | what it does | what happens without it |
|---|---|---|
| match-outline | section-level rewrite via Kimi — changes enough sentence structure that the downstream paragraph rewriter can clear the mechanical gate | match-voice rewrites land at distance 0.0 from the original; the gate rejects every paragraph and nothing changes |
| filter-tells semantic cleanup | collapse antithesis pairs, remove CoT leakage, cut recap ballast, fix banned words | Pangram score stays at 100% AI even after match-voice, because the rhetorical patterns survive diction changes |
| match-voice --no-anchors | paragraph-level diction rewrite via gpt-oss with no voice anchors | prose retains the original model's lexical fingerprint; Pangram detects it |

The compound effect: semantic cleanup alone does not move Pangram (rhetorical
patterns are not what it measures). match-voice alone on raw text gets
gate-rejected (distance 0.0). Both steps together, with match-outline
providing the structural divergence, produce 100% human.

## Why no anchors

Every anchor configuration tested made Pangram scores worse. gpt-oss
unconstrained produces formal Latinate prose (passive, nominalized, complex
sentences) that does not match Pangram's training distribution of
conversational AI text. Anchors constrain gpt-oss into register patterns
Pangram catches. Tested: venue-voice only (0% human), author-voice 2.5x
(26.6% human), Evans how-to (0% human), zero anchors (100% human, mean
0.245).

## Prerequisites

- Ollama endpoint reachable with `kimi-k2.6:cloud` and `gpt-oss:120b-cloud`
- A `writing-voice/` directory with exemplars and a blueprint for
  match-outline (e.g. `blueprints/evans-howto.md`)
- For the Pangram measurement: a Pangram API key configured per the
  match-voice credential contract

## Procedure

### Step 1: match-outline (Kimi, section-level rewrite)

Rewrite the whole article via `match_outline.py --rewrite`. This produces
`<article-stem>-rewritten.md` next to the original.

```bash
RUN="pixi run --manifest-path <agent-dir>/pixi.toml python"
$RUN <match-outline>/scripts/match_outline.py <article.md> \
  --voice-dir <repo>/writing-voice \
  --anchor-tags how-to \
  --blueprint <repo>/writing-voice/blueprints/evans-howto.md \
  --model kimi-k2.6:cloud \
  --rewrite
```

The output is expected to remain AI-flagged. That is correct — match-outline
provides structural divergence, not diction cleanup.

Verify the rewrite preserved content: check that citations, numbers, code
blocks, and figures survived. match_outline.py runs its own similarity guard,
but spot-check the sections that carry data.

### Step 2: filter-tells semantic cleanup

Run the lexical and structural scans on the rewritten file to identify the
edit targets.

```bash
bash <filter-tells>/scripts/detect-lexical.sh <rewritten.md>
$RUN <filter-tells>/scripts/detect-structural.py <rewritten.md>
```

Then apply the semantic edits by hand or by model, following the filter-tells
Step 3 procedure. The edits that matter most for this pipeline:

1. **Antithesis pairs** — collapse every negation-flip pair into a single
   sentence. These are the dominant AI rhetorical pattern. Target: 0 pairs.
2. **CoT leakage** — delete bridge sentences that add no information.
   Apply the removal test: delete the sentence, re-read the paragraph.
   If nothing is lost, it was scaffolding.
3. **Recap ballast** — compress paragraphs that restate earlier points
   without adding new information.
4. **Banned words** — swap any remaining banned words (check the lexical
   scan output).

After editing, re-run both scans to confirm:
- Structural verdict: MINOR-ISSUES or better (was LIKELY-AI)
- Antithesis pairs: 0
- No banned words

### Step 3: match-voice gpt-oss --no-anchors

Run the paragraph-level diction rewrite with no voice anchors.

```bash
$RUN <match-voice>/scripts/drive.py \
  --article <rewritten-and-cleaned.md> \
  --model gpt-oss:120b-cloud \
  --no-anchors \
  --pangram \
  --out <output.md>
```

Check the output for:
- `accepted-mechanical` count (should be most paragraphs, not `kept-original`)
- Distance > 0 (confirms the gate accepted rewrites)
- Pangram verdict and mean window score

Expected result with the full pipeline: 100% human, mean score ~0.25.

### Step 4: Verify

After the pipeline completes:

1. **Pangram result** — already reported by `--pangram`. Confirm verdict
   and per-window scores.
2. **Structural scan** — run detect-structural.py on the final output to
   confirm no new antithesis pairs or tells were introduced.
3. **Meaning preservation** — read the final output against the original.
   The three rewrites compound meaning drift. Check that claims, citations,
   numbers, and the article's argument survived.
4. **Register markers** — the drive.py output reports register markers
   (passive, nominalization, filler). Confirm filler/500w did not regress
   above the input's level.

## File naming convention

The pipeline produces files with these suffixes:

| file | step |
|---|---|
| `<stem>.md` | original article |
| `<stem>-rewritten.md` | after match-outline (Kimi) |
| `<stem>-rewritten.md` | same file, after semantic edits applied in place |
| `<stem>-rewritten.vr-gptoss-noanchor.md` | final output after match-voice |
| `<stem>-rewritten.vr-gptoss-noanchor.generation.yaml` | provenance record |

## When it breaks

- **match-voice gate rejects everything (distance 0.0):** the match-outline
  step did not change the prose enough. Try a different model or blueprint
  for match-outline, or apply more aggressive semantic edits in step 2.
- **Pangram score does not improve:** the semantic cleanup missed rhetorical
  patterns. Re-run filter-tells Step 3 (the full semantic analysis) and look
  for surviving antithesis pairs, tricolon patterns, or CoT leakage.
- **Meaning drift:** three rewrites compound. The match-outline rewrite is
  the largest source of drift. Compare the final output against the original
  (not the intermediate) to catch cumulative losses.
- **Filler regression:** gpt-oss without anchors tends toward formal prose,
  but can introduce filler. Check the register markers in the drive.py
  output.

## Calibration data

Tested on `2026-10-29-how-to-break-an-ais-heresy.md` (2,357 words):

| variant | pipeline | Pangram human % | mean score |
|---|---|---|---|
| original | none | 0% | 0.993 |
| match-outline only | Kimi rewrite | 0% | 0.993 |
| semantic cleanup only | filter-tells on Kimi rewrite | 0% | 0.993 |
| match-voice venue-voice | Kimi + semantic + Tanenbaum/Martin anchors | 0% | 0.765 |
| match-voice author 2.5x | Kimi + semantic + Djukic anchors | 26.6% | 0.454 |
| match-voice Evans how-to | Kimi + semantic + Evans anchors | 0% | 0.955 |
| **match-voice no-anchors** | **Kimi + semantic + gpt-oss no anchors** | **100%** | **0.245** |
| no match-outline | semantic + gpt-oss no anchors on original | 0% | 0.993 (gate rejected) |
| no semantic cleanup | gpt-oss no anchors on original | 0% | 0.993 (gate rejected) |
