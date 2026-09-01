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

## Pipeline position (GH-57 ordering; a humanize stage since GH-208)

This is a stage of the humanize chain — its Phase 4, after tighten-style
and before inject-vernacular (terminal). The candidates come from a
generative model, so the stage must precede the deterministic terminal
stage and the caller's read-only review phase. Locked spans never enter
the candidate pool (the gate skips any paragraph carrying lock markers),
but locks are excised and spliced by the calling pipeline as usual — the
gate is a backstop, not the mechanism. It also runs standalone when the
author only wants the dial.

## Usage

```bash
python3 <skill>/scripts/accent_dial.py --article draft.md --dial 0.4
```

- First run generates and caches `<stem>.roundtrip.txt` via Ollama
  (~150 chunk calls on a 5k-word article; reruns at other dial values are
  free). `--roundtrip` points at an existing cache.
- Output: `<stem>.dial<p>.md` + `<out>.log.json` (per-candidate gate
  verdict, score, applied flag — the survival-analysis surface).
- **Fluency dial (GH-188).** `--fluency {fresh,settled,native}` (or
  `--fluency-years N`, mapped <=8 / <=22 / else) gives the return leg an
  immersion persona, dialing the accent between the mechanical round trip's
  total-beginner sound and polished-away. Measured on the way in: a bare
  years number in the prompt is a null — four levels produced identical
  fluent output — so years only select a *described feature band* (fronted
  adverbs and dropped articles at fresh, faint formality at settled,
  idiomatic at native). Absent, the blind return leg is byte-identical to
  the calibration.
- **Two dials since GH-186.** `--model-return` (env
  `ACCENT_DIAL_MODEL_RETURN`) splits the legs: the 2026-08-21 A/B located the
  accent effect on the return leg, so the productive pairing is a strong
  outbound translator (fidelity into the pivot) with the weak return one
  (where the accent is born) — e.g. `--model cohere:command-a-03-2025
  --model-return gemma4:31b-cloud`. `--language` swaps the pivot (default
  serbian); any other pivot produces its own accent flavor but sits outside
  the calque gate's calibration — score() then ranks by restructuring
  distance alone, and the run says so on stderr. Per-language marker banks
  (l2-markers.yaml is the canonical home) are the eventual fix.
- `--model` (or `ACCENT_DIAL_MODEL`) overrides the translator, and since
  GH-184 the script rides match-voice's shared transport, so
  `cohere:command-a-03-2025` routes with key handling and retries for free.
  The default stays gemma4:31b-cloud on the 2026-08-21 A/B: the stronger
  gpt-oss return leg polishes the accent away (L2 composite -0.009 vs
  gemma's +0.726) and scores worse on Pangram (0.247 vs 0.150) — the same
  risk applies to any stronger translator, Cohere included, so the
  pipeline-wide Cohere default deliberately does not reach this skill.

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

## Sentence grain (default since GH-73)

The GH-175 author gate rejected paragraph grain: dial 0.4 produced walls
of fully-translated paragraphs beside untouched ones, and the whole read
as ESL. Sentence grain dials the intensive margin instead — candidates
are 1:1-aligned sentences (monotone DP alignment; split/merged sentences
never pair, and the sentence-level length gate kills half-translations),
globally ranked, applied under a per-paragraph cap (--max-per-para,
default 2). The accent disperses: one lightly foreign sentence per
paragraph, nothing fully foreign. A quote gate rejects any candidate
whose double-quoted spans are not verbatim — mechanizing the failure
class that cost 5 of 9 review reverts at paragraph grain.

Calibration (strategy-theatre payload, cached gemma round-trip,
baseline 0.708 AI / full round-trip 0.150):

| grain, dial | Pangram AI | human | units swapped |
|---|---:|---:|---:|
| sentence 0.3 | 0.374 | 0.437 | 80/267 sentences |
| sentence 0.6 | 0.399 | 0.525 | 138/267 sentences |
| paragraph 0.25 | 0.464 | 0.475 | 19/75 paragraphs |
| paragraph 0.5 | 0.154 | 0.692 | 38/75 paragraphs |

The shapes differ: sentence grain beats paragraph grain at low dial
(0.374 vs 0.464) and plateaus near 0.4 — dispersed swaps blend inside
detector windows, so it never reaches the concentrated grain's floor.
Choose by objective: register smoothness and author tolerance → sentence
(start 0.3); maximum laundering on structurally clean text where the
author accepts paragraph walls → paragraph.

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

## Generalization (three pre-pipeline essays, 2026-08-21)

Dial 0.4 on essays that predate the voice program, all baseline 1.000 AI
(prose-only payloads):

| essay | dial 0.4 | dial 1.0 |
|---|---:|---:|
| your-ai-project-failed (2025-11) | 0.567 | — |
| hidden-cost-junior (2026-02) | 1.000 | 1.000 |
| block-layoffs (2026-04) | 1.000 | 0.872 |

The split has a measured mechanism: **round-trip launders diction, not
discourse structure.** The translation preserves — and sometimes
amplifies — the structural tells (junior antithesis 8→18 through the
round-trip, failed 9→14; tricolons, anaphoric lists, and opening
monotony pass through nearly unchanged), so an essay saturated with
structural signal scans 1.000 even fully translated. Strategy Theatre
responded because its structure was already pipeline-cleaned.

Consequences:
- **accent-dial composes AFTER structural repair, never instead of it.**
  Run the filter-tells structural pass first; dial the accent into
  structurally clean text.
- **gemma manufactures antithesis** (an AI tell inject-vernacular
  targets), so a structural recheck of applied paragraphs is part of the
  review gate.
- **The calque list does not transfer across articles**: all three fresh
  round-trips produced zero hits on the strategy-theatre-seeded list, so
  ranking degenerated to restructuring depth. Until an
  article-independent L2 signal exists, treat the ranking as
  laundering-depth-first on new material.

## Known limits

- The ranking's accent signal is the calque list mirrored from
  l2-markers.yaml — article-specific in practice (see Generalization);
  grow the canonical bank first, then mirror here.
- Saturation shape (accent by 0.25, Pangram by 0.5) measured on
  strategy-theatre only, and only meaningful where the round-trip moves
  the score at all — check the essay responds before choosing a dial.
- Paragraph-level grain: a paragraph is swapped whole. Sentence-level
  grain is a follow-up if review-gate rejections cluster in otherwise
  good paragraphs.
