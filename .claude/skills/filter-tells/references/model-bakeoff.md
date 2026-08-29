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

## Caveats

Pangram-human is not an HN pass. filter-tells output is neutral by design — not
voice-graded. Cohere is a hosted API (cost/egress); the incumbent gpt-oss and
gemma are Ollama-cloud.
