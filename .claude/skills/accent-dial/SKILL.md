<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: accent-dial
description: >-
  Pre-terminal accent stage: dial a controllable amount of the author's
  Serbian-L1 accent into an article by accepting a ranked fraction of
  EN→Serbian→EN round-trip translation edits. One cached round-trip per
  article (gemma4:31b-cloud), paragraphs aligned 1:1, mechanically gated
  (citations, numbers, locks, length), ranked by Serbian-ness (calques,
  then restructuring depth); --dial 0..1 applies the top fraction
  deterministically with a full edit log. Generative source, deterministic
  application: the run is not done until the applied paragraphs pass an
  entailment review. Triggers: accent dial, serbian accent, round-trip
  translation, dial the accent, more serbian, less serbian, translation
  laundering, L2 accent stage.
---

# Accent Dial (pre-terminal stage)

The EN→SR→EN round-trip is the only measured source of the author's
Serbian-L1 accent: the regular published articles carry ZERO calques and
sit below the native exemplars on the L2 composite (paper-stash
`writing-voice/l2-markers.yaml`, v1.2), while the gemma round-trip of
Strategy Theatre measured +0.726 — and simultaneously produced the
strongest Pangram move ever recorded on that article (0.708 → 0.150
fraction_ai, all 27 citations intact). But a whole-text round-trip is
all-or-nothing: locked spans get paraphrased, quoted specimens drift from
their blockquotes, and confident mistranslations ride along.

This stage makes the accent a dial instead. The round-trip is a CANDIDATE
GENERATOR, not a transformation: every paragraph pair is gated
mechanically, the survivors are ranked by how much Serbian they carry, and
`--dial p` applies the best-ranked fraction. Application is deterministic
and prefix-monotone (edits applied at a lower dial stay applied at every
higher one), every candidate lands in the edit log with its gate verdict
and score, and unapplied paragraphs stay byte-identical to the input.

## Pipeline position (GH-57 ordering)

PRE-terminal, beside match-voice: the candidates come from a generative
model, so this stage runs before inject-vernacular (terminal) and the
read-only zone. Locked spans never enter the candidate pool (the gate
skips any paragraph carrying lock markers), but locks are excised and
spliced by the calling pipeline as usual — the gate is a backstop, not
the mechanism.

## Usage

```bash
python3 <skill>/scripts/accent_dial.py --article draft.md --dial 0.4
```

- First run generates and caches `<stem>.roundtrip.txt` via Ollama
  (~150 chunk calls on a 5k-word article; reruns at other dial values are
  free). `--roundtrip` points at an existing cache.
- Output: `<stem>.dial<p>.md` + `<out>.log.json` (per-candidate gate
  verdict, score, applied flag — the survival-analysis surface).
- `--model` overrides the translator. Keep gemma4:31b-cloud: the
  2026-08-21 A/B showed the stronger gpt-oss return leg polishes the
  accent away (L2 composite -0.009 vs gemma's +0.726) and scores worse on
  Pangram (0.247 vs 0.150).

## Calibration (Strategy Theatre payload, 2026-08-21)

| dial | Pangram fraction_ai | fraction_human | L2 composite | paragraphs touched |
|-----:|--------------------:|---------------:|-------------:|-------------------:|
| 0.0  | 0.708 | 0.292 | −0.201 | 0/75 |
| 0.25 | 0.464 | 0.475 | +0.755 | 19/75 |
| 0.5  | 0.154 | 0.692 | +0.742 | 38/75 |
| 1.0  | 0.150 | 0.772 | +0.726 | 75/75 |

Two saturation points, both useful: the L2 composite saturates by ~0.25
(ranking front-loads every calque-bearing paragraph), and Pangram
saturates by ~0.5 — half the edits buy the whole detector effect while
the other half of the article stays byte-identical to the author-gated
text. Default working range: **0.3–0.5**. Above 0.5 you pay review
surface for nothing measurable.

## The review gate (mandatory)

Mechanical gates pass what semantic review rejects — the 8/8 match-voice
lesson. After applying, entailment-review every applied paragraph against
its original (the edit log lists them): meaning preserved, no confident
mistranslation ("the pods sentence" → "a sentence about floors" passed
every mechanical gate), quoted phrases still match what they quote.
Reject by reverting the paragraph in place (the log records the original
index; unapplied paragraphs are untouched) — never by asking a model to
repair the final text. Then re-measure: paper-stash
`writing-voice/measure-l2.py --text <out>` for the accent,
`--pangram`-style scan only at the gate (scans cost credits; the dial
curve above is the planning surface).

## Known limits

- The ranking's accent signal is the calque list mirrored from
  l2-markers.yaml — sparse by design; grow the canonical bank first, then
  mirror here.
- Calibrated on one article. The saturation shape (accent by 0.25,
  Pangram by 0.5) should be re-checked on the next article before the
  defaults harden.
- Paragraph-level grain: a paragraph is swapped whole. Sentence-level
  grain is a follow-up if review-gate rejections cluster in otherwise
  good paragraphs.
