---
name: humanize
description: >-
  Three-step pipeline to move AI-drafted prose to human-passing on Pangram:
  match-outline (structural rewrite), filter-tells (semantic cleanup), then
  match-voice --no-anchors (paragraph diction). Parameterized blueprint and
  anchor-tag selection, inter-step Pangram measurement, consolidated
  five-category writing-quality report.
  Triggers: humanize, humanize article, make it human, full rewrite pipeline,
  rewrite for pangram, three-step rewrite.
---

# Humanize (three-step pipeline)

Orchestrates the three prose skills that together move an AI-drafted article
from 100% AI-flagged to human-passing on Pangram. Each step exists because
the other two cannot compensate for its absence.

## Why three steps

| step | what it does | what happens without it |
|---|---|---|
| match-outline | section-level rewrite — changes enough sentence structure that the downstream paragraph rewriter can clear the mechanical gate | match-voice rewrites land at distance 0.0 from the original; the gate rejects every paragraph and nothing changes |
| filter-tells semantic cleanup | collapse antithesis pairs, remove CoT leakage, cut recap ballast, fix banned words | Pangram score stays at 100% AI even after match-voice, because the rhetorical patterns survive diction changes |
| match-voice --no-anchors | paragraph-level diction rewrite via gpt-oss with no voice anchors | prose retains the original model's lexical fingerprint; Pangram detects it |

The compound effect: semantic cleanup alone does not move Pangram (rhetorical
patterns are not what it measures). match-voice alone on raw text gets
gate-rejected (distance 0.0). Both steps together, with match-outline
providing the structural divergence, produce 100% human.

## Why no anchors for match-voice

Every anchor configuration tested made Pangram scores worse. gpt-oss
unconstrained produces formal Latinate prose (passive, nominalized, complex
sentences) that does not match Pangram's training distribution of
conversational AI text. Anchors constrain gpt-oss into register patterns
Pangram catches. See calibration data at the end.

## Prerequisites

- Ollama endpoint reachable with `kimi-k2.6:cloud` and `gpt-oss:120b-cloud`
- A `writing-voice/` directory with exemplars and at least one blueprint
  under `writing-voice/blueprints/`
- For Pangram measurement: an API key configured per the match-voice
  credential contract (`.secrets/keys.json` with `"pangram"` entry)

## Procedure

### Phase 0: Discover and choose targets

1. Discover `writing-voice/` by walking up from the article path.
   Error if not found.

2. List available blueprints:

   ```bash
   ls <repo>/writing-voice/blueprints/*.md
   ```

3. List available tags from the manifest:

   ```bash
   RUN="pixi run --manifest-path <agent-dir>/pixi.toml python"
   $RUN <match-structure>/scripts/voice_anchors.py \
     --voice-dir <repo>/writing-voice tags
   ```

   If the `tags` subcommand is not available, parse distinct tag values from
   `writing-voice/manifest.yaml` directly.

4. Ask the user which blueprint and anchor-tags to use for match-outline.
   If only one blueprint exists, propose it as the default. Show the available
   tags and let the user choose (or skip tags for untagged retrieval).

5. Capture baseline measurements:

   ```bash
   # Pangram baseline
   $RUN <match-voice>/scripts/drive.py \
     --article <article.md> --dry-run --pangram \
     --no-anchors --model gpt-oss:120b-cloud

   # Style baseline
   $RUN <match-structure>/scripts/style.py profile <article.md>
   ```

   Record the baseline Pangram scores (human %, mean window score, verdict)
   and the full `text_metrics()` output. These are the "before" column in the
   final report.

### Phase 1: match-outline (structural rewrite)

Rewrite the whole article via `match_outline.py --rewrite` with the user's
chosen blueprint and anchor-tags.

```bash
$RUN <match-outline>/scripts/match_outline.py <article.md> \
  --voice-dir <repo>/writing-voice \
  --anchor-tags <chosen-tags> \
  --blueprint <chosen-blueprint> \
  --model kimi-k2.6:cloud \
  --rewrite
```

The output is `<article-stem>-rewritten.md` next to the original. It is
expected to remain AI-flagged — match-outline provides structural divergence,
not diction cleanup.

Verify the rewrite preserved content: check that citations, numbers, code
blocks, and figures survived. match_outline.py runs its own similarity guard,
but spot-check the sections that carry data.

Measure after match-outline:

```bash
$RUN <match-voice>/scripts/drive.py \
  --article <rewritten.md> --dry-run --pangram \
  --no-anchors --model gpt-oss:120b-cloud

$RUN <match-structure>/scripts/style.py profile <rewritten.md>
```

Record as the "after-outline" column.

### Phase 2: filter-tells semantic cleanup

Run the lexical and structural scans on the rewritten file.

```bash
bash <filter-tells>/scripts/detect-lexical.sh <rewritten.md>
$RUN <filter-tells>/scripts/detect-structural.py <rewritten.md>
```

Apply the semantic edits following the filter-tells Step 3 procedure. The
edits that matter most for this pipeline:

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

Measure after filter-tells:

```bash
$RUN <match-voice>/scripts/drive.py \
  --article <rewritten.md> --dry-run --pangram \
  --no-anchors --model gpt-oss:120b-cloud

$RUN <match-structure>/scripts/style.py profile <rewritten.md>
```

Record as the "after-tells" column.

### Phase 3: match-voice --no-anchors

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

Measure final style:

```bash
$RUN <match-structure>/scripts/style.py profile <output.md>
```

Record as the "after-voice" column.

### Phase 4: Consolidated report

Print a single report with five categories. Each metric shows four columns:
baseline, after-outline, after-tells, after-voice, and the total delta
(after-voice minus baseline).

**1. AI/Human detection (Pangram)**

| stage | human % | mean score | verdict |
|---|---|---|---|
| baseline | — | — | — |
| after match-outline | — | — | — |
| after filter-tells | — | — | — |
| after match-voice | — | — | — |

**2. Readability**

| metric | baseline | after-outline | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Flesch Reading Ease | — | — | — | — | — |
| Flesch-Kincaid Grade | — | — | — | — | — |
| Gunning Fog | — | — | — | — | — |
| SMOG Index | — | — | — | — | — |

**3. Lexical diversity**

| metric | baseline | after-outline | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Type-Token Ratio | — | — | — | — | — |
| Corrected TTR | — | — | — | — | — |
| Hapax Ratio | — | — | — | — | — |
| Yule's K | — | — | — | — | — |

**4. Syntactic and structural**

| metric | baseline | after-outline | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Sentence length mean | — | — | — | — | — |
| Sentence length stdev | — | — | — | — | — |
| Sentence length CV | — | — | — | — | — |
| Mean clause length | — | — | — | — | — |
| Passive / 100 sentences | — | — | — | — | — |
| Paragraph cohesion | — | — | — | — | — |

**5. Stylometrics**

| metric | baseline | after-outline | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Function word ratio | — | — | — | — | — |
| Hedges / 1000 words | — | — | — | — | — |
| Commas / 1000 words | — | — | — | — | — |
| Semicolons / 1000 words | — | — | — | — | — |
| Em dashes / 1000 words | — | — | — | — | — |
| Colons / 1000 words | — | — | — | — | — |
| Top sentence openers | — | — | — | — | — |

**6. Filter-tells results**

| metric | before cleanup | after cleanup |
|---|---|---|
| Antithesis pairs | — | — |
| Banned words | — | — |
| Structural verdict | — | — |

**7. Match-voice gate stats**

| metric | value |
|---|---|
| Accepted (mechanical) | — |
| Kept original | — |
| Skipped (short) | — |
| Mean distance | — |

## File naming convention

| file | step |
|---|---|
| `<stem>.md` | original article |
| `<stem>-rewritten.md` | after match-outline |
| `<stem>-rewritten.md` | same file, after semantic edits applied in place |
| `<stem>-rewritten.vr-gptoss-noanchor.md` | final output after match-voice |
| `<stem>-rewritten.vr-gptoss-noanchor.generation.yaml` | provenance record |

## When it breaks

- **match-voice gate rejects everything (distance 0.0):** the match-outline
  step did not change the prose enough. Try a different model or blueprint
  for match-outline, or apply more aggressive semantic edits in Phase 2.
- **Pangram score does not improve:** the semantic cleanup missed rhetorical
  patterns. Re-run filter-tells Step 3 (the full semantic analysis) and look
  for surviving antithesis pairs, tricolon patterns, or CoT leakage.
- **Meaning drift:** three rewrites compound. The match-outline rewrite is
  the largest source of drift. Compare the final output against the original
  (not the intermediate) to catch cumulative losses.
- **Filler regression:** gpt-oss without anchors tends toward formal prose,
  but can introduce filler. Check the stylometrics section of the report.

## Calibration data

Tested on `2026-10-29-how-to-break-an-ais-heresy.md` (2,357 words) with
hardcoded Evans how-to blueprint and anchor-tags:

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
