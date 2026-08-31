# filter-tells model bake-off (GH-147)

Which model to run filter-tells' semantic analysis + targeted rewrite with, and
why. Parallel to the match-voice bake-off (writing-skills GH-138). 2026-08-29.

## Two bugs had to be fixed before it could run (GH-148, GH-149)

The bake-off surfaced two pre-existing defects that made filter-tells' headless
rewrite unreliable for every model:

- **Multi-pass loop corruption (GH-148):** run_rewrite spliced a multi-line
  rewrite in as a single list element and carried a stale in-memory buffer
  across passes, so after pass 1 the line indices no longer matched and later
  passes spliced at wrong offsets — a 1386-word draft ballooned to 7094 words.
  Fixed: seed the draft, re-read it fresh each pass, expand rewrites with
  `split("\n")`. 7094 → ~1600.
- **No Ollama retry (GH-149):** a dropped `RemoteDisconnected` connection killed
  the whole run (12 semantic prompts + 3 rewrite passes); the incumbent gpt-oss
  crashed twice before finishing. Fixed: bounded retry/backoff on the Ollama
  path (`OLLAMA_MAX_RETRIES`).

Only after both fixes could all four candidates complete.

## Setup

Non-saturated draft (code-quality-recursively, 1386 words, baseline Pangram
0.744). Each candidate run through the fixed filter-tells drive.py (scan →
semantic → up to 3 rewrite passes). Prose-only Pangram on the filtered output;
length and structural-tell delta recorded.

## Result

| Model | Pangram AI | human | words (base 1386) | struct tells | notes |
|-------|-----------:|------:|------------------:|-------------:|-------|
| baseline | 0.744 | — | 1386 | 7 | — |
| **gpt-oss:120b-cloud (incumbent)** | **0.000** | 0.742 | 1477 | 7→10 | winner; clean output |
| gemma4:31b-cloud | 0.167 | 0.833 | 1249 | 7→8 | close second |
| cohere:command-a-03-2025 | 0.397 | 0.374 | 1623 | 7→13 | 4 meta-leak lines |
| kimi-k2.6:cloud | 0.490 | 0.269 | 1390 | 7→9 | weakest on Pangram |

## Verdict: keep the incumbent — no default change

**gpt-oss:120b-cloud wins decisively (Pangram 0.000)** and is already the
`FILTER_TELLS_MODEL` default. gemma4:31b-cloud is a clean second (0.167, highest
human fraction). This is the OPPOSITE of the match-voice result (GH-138), where
Cohere beat the incumbents — because the tasks differ: filter-tells rewards the
analytical detect-and-fix that the large gpt-oss model does best, whereas Cohere
(the match-voice winner) is middling here (0.397) and leaks instruction fragments
on filter-tells' rules-heavy rewrite prompt (4 meta-leak lines). Cohere is NOT a
filter-tells default candidate.

Refinement (GH-156): those meta-leak lines are not a Cohere trait. A 76-call
sweep found the same rule-echo on 4 of 19 paragraphs for *both* Cohere families,
and the other 15 clean for both — it is triggered by the paragraph, not the
model. The incumbents were not run against those four items, so this bake-off
does not establish that they survive them. See
[cohere-bakeoff.md](../../match-voice/references/cohere-bakeoff.md), "Where the
leak actually lives".

Voice note: gpt-oss's output drifted toward generic register ("Massive churn
makes any meaningful review impossible"). That is acceptable HERE and only here —
filter-tells deliberately produces neutral prose ("no tells, but no voice
either"); match-voice restores voice downstream. The same drift disqualified
Cohere as a match-voice default (GH-145 sample) because voice is match-voice's
whole job; it does not count against a filter-tells model.

## Cross-model observation (worth a follow-up)

Every model RAISED the structural tell count (7 → 8/9/10/13) even as Pangram
fell. This is the "suspicious-overshoot" the SKILL warns about — the recursive
rewrite pushes toward a different, LinkedIn-flavored tell profile. It is
model-independent (all four did it), so it points at the rewrite prompt or
max_passes=3, not at model choice. A candidate for a separate pass-count / prompt
tuning issue. Pangram and the structural scan disagreeing is exactly why the
SKILL says to read both, never one alone.


## Three-article re-run (GH-170, 2026-08-30/31)

GH-147's verdict rested on one draft and a pipeline that has since changed
four ways (#154/#155 backend, #157 resilience, #159 citation gate, #171
targeting). Four models, three published articles, the full real pipeline per
cell, run twice: once on the pipeline as it stood, once under the #171 fix —
because the first run exposed that bug mid-flight.

### The #171 bug decided the pre-fix results

`_issues_for_lines` appended every structural issue — verbatim quotes from
other paragraphs included — to every paragraph's rewrite prompt. Measured
consequence: a sentence quoted in one issue detail appeared 6x in Cohere's
draft (1x baseline), and a vocabulary word appeared 13x from nowhere.
Instruction-literal models obeyed the noise; noise-ignoring models hid the bug.

### Register, pre-fix -> post-fix (Pangram fraction_ai; baselines 0.919 / 0.913 / 1.000)

| article | cohere | gpt-oss | gemma | kimi |
|---|--:|--:|--:|--:|
| who-reads-your-prompts | 0.652 -> **0.180** | 0.206 -> 0.153 | 0.350 -> 0.148 | 0.534 -> 0.882 |
| the-loop-is-the-easy-part | 0.068 -> **0.000** | 0.073 -> 0.074 | 0.080 -> 0.082 | 0.386 -> 0.486 |
| biking-on-sidewalks | 0.858 -> 0.656 | 0.228 -> **0.115** | 0.378 -> 0.330 | 0.158 -> 0.510 |

Mean improvement from the fix: cohere **-0.247**, gemma -0.083, gpt-oss
-0.055, kimi **+0.267 (worse)**.

### Mechanical, post-fix (citations intact in every cell)

| model | gate refusals | issue delta (3 articles) | length behavior |
|---|--:|---|---|
| cohere | 22 | 32->50, 41->39, 58->25 | -3% avg; the +49% overshoot is gone |
| gpt-oss | 10 | 32->38, 41->6, 58->18 | disciplined |
| gemma | 0 | 32->24, 41->16, 58->24 | trims |
| kimi | 0 | 32->37, 41->6, 58->59 | stops early (see below) |

### Verdict

- **Keep `gpt-oss:120b-cloud` as FILTER_TELLS_MODEL.** Post-fix means: gpt-oss
  0.114, gemma 0.187, cohere 0.279, kimi 0.626. Consistent everywhere, best on
  the hardest payload. GH-147's conclusion survives on a clean pipeline —
  with its mechanism corrected below.
- **GH-147's "Cohere leaks instruction fragments / not a candidate" is
  superseded.** The leak was #171's noise, which Cohere obeyed and the
  incumbents ignored; under the fix Cohere improved most of any model and
  posted the run's only perfect score (loop: 0.000 ai / 0.931 human). It is a
  legitimate second option for technical prose, still the weakest on the
  personal essay, and still the only model needing the citation gate (22
  refusals — the #172 prompt rules address this, lab-verified 46%->88%).
- **kimi's pre-fix strength was the bug.** The document-wide issue blob goaded
  it into 225 aggressive rewrites; correctly scoped, it applies 71, reads "no
  improvement", and stops. A pipeline bug can flatter a model as easily as
  damage one — the pre-fix biking column had kimi ranked first.
- GH-147's cross-model "every model RAISED the structural tell count" does not
  reproduce post-fix: issue counts fall in 9 of 12 cells.

Limits: n=3 articles, one detector, one prompt shape; per-article spread is
wide (gemma beats gpt-oss on prompts). The per-cell records and drafts live in
the GH-170 run archive.

## Caveats

Pangram-human is not an HN pass. filter-tells output is neutral by design — not
voice-graded. Cohere is a hosted API (cost/egress); the incumbent gpt-oss and
gemma are Ollama-cloud.

## Default change (GH-176, 2026-08-31) — operator decision

`FILTER_TELLS_MODEL` now defaults to `cohere:command-a-03-2025`, overriding
this bake-off's verdict. Recorded as an operator decision, not a measurement:
the GH-170 post-fix means had gpt-oss ahead (0.114 vs 0.279). The grounds:
Cohere was best-in-run on technical prose (the run's only perfect 0.000 score),
improved most once GH-171/172 fixed the pipeline faults that had depressed it,
and the operator values one model family across both skills. gpt-oss remains
the measured leader and the keyless/local fallback (`FILTER_TELLS_MODEL=gpt-oss:120b-cloud`).
