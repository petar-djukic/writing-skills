---
name: tune-anchors
description: >-
  Sweep anchor selections over a writing-voice corpus and report which tag
  query produces the best register outcome. Runs match-voice over (article ×
  arm) combinations, ranks arms on the four-axis register composite, and
  optionally verifies the top candidates with an external detector.
  Triggers: tune anchors, sweep anchors, which anchors should I use,
  calibrate writing-voice, onboard corpus.
---

# tune-anchors

## The objective

Given a `writing-voice/` corpus and one or more target articles, answer:
**which anchor-selection rule produces rewrites closest to the author's own
register?**

A rule is an *arm* — a set of filters over the manifest: `role=venue-voice`,
`tags~clipped`, `pre_ai=true`. Different arms produce different anchor sets,
and the model copies the register of whatever it sees. The right arm is the
one whose anchors give the model a register worth copying.

## When to run

- **Writing-voice onboarding.** After the manifest exists and before the first
  real rewrite. Output is the `--anchor-tags` query to use thereafter.
- **After the corpus grows.** Pool sizes change, and guidance hardcoded to
  a count goes stale. The source study's recommendation (idea-factory#355)
  went stale exactly this way.
- **After adding or removing tags.** A tag query that was inert on the old
  corpus may now select a meaningful subset.

## Prerequisites

| What | Required for | Notes |
|------|-------------|-------|
| `writing-voice/` with manifest | all commands | the corpus being tuned |
| Ollama with the target model | `sweep` (full) | `--dry-run` needs no model |
| Pangram key in `.secrets/` | `verify` only | optional; verify is the last step |

## Commands

### sweep

Run match-voice over (article × arm) pairs, record register markers.

```bash
pixi run python3 tune_anchors.py sweep \
  --voice-dir ../writing-voice \
  --articles article-a.md article-b.md \
  --arms "tags~clipped" "role=venue-voice" "pre_ai=true" \
  [--n 24] [--model gemma4:12b] [--out ledger.yaml] [--dry-run]
```

`--dry-run` runs retrieval only (no model, no cost). It records which
anchors would be selected per paragraph — enough to detect the GH-215 shape
(wrong anchors selected, correct ones discarded) without spending compute.

Full mode runs `drive.py` per (article, arm), captures register markers and
structural metrics from the output. Requires Ollama.

### rank

Score arms on the register composite, emit a sorted table.

```bash
pixi run python3 tune_anchors.py rank --ledger ledger.yaml [--blind]
```

`--blind` hides arm labels, replacing them with 8-character hashes, and
shuffles the output. Blindness matters: in the source study the operator
twice guessed wrong about which sources were clipped.

Disagreements — an arm that ranks well on local metrics but poorly on the
detector (or vice versa) — are flagged with a WARNING rather than averaged
away.

### verify

Scan top K with Pangram, record detector results.

```bash
pixi run python3 tune_anchors.py verify --ledger ledger.yaml --top 3 [--budget 10]
```

This is where the money goes, and it is deliberately last. Refuses to exceed
`--budget` total scans. Records results back to the ledger so `rank` can
surface disagreements on the next run.

## Worked example

```bash
# 1. Dry-run: see what retrieval selects (free)
pixi run python3 tune_anchors.py sweep --dry-run \
  --voice-dir ../autogenic-systems/writing-voice \
  --articles posts/2026-07-distributed-scheduling.md \
  --arms "tags~clipped" "role=venue-voice" "tags~economics"

# 2. Full sweep: run the model (requires Ollama)
pixi run python3 tune_anchors.py sweep \
  --voice-dir ../autogenic-systems/writing-voice \
  --articles posts/2026-07-distributed-scheduling.md \
  --arms "tags~clipped" "role=venue-voice" \
  --model gemma4:12b --out calibration.yaml

# 3. Rank: which arm produced the best register?
pixi run python3 tune_anchors.py rank --ledger calibration.yaml

# 4. Verify top 2 with Pangram (optional, costs 2-4 scans)
pixi run python3 tune_anchors.py verify --ledger calibration.yaml --top 2 --budget 6
```

## The two findings this harness encodes

**Pool size is a confound.** A comparison of two tag queries with different
pool sizes measures size and identity together. The `--n` flag samples arms
to a common size; vary size only as its own arm.

**Local metrics and the external detector can point opposite ways.** A sweep
cannot rank on either signal alone: it needs both, recorded separately, with
disagreement surfaced rather than averaged away. That is why `verify` is a
separate step that records to the ledger rather than a number folded into the
composite.

## Relationship to other skills

- **match-voice** — the rewrite engine this harness drives. `sweep` calls
  `drive.py` per trial.
- **filter-tells** — the register measurement this harness reads. `rank`
  scores on the same four-axis composite `register_markers.py` computes.
- **match-structure** — provides `voice_anchors.py`, the retrieval engine
  that `sweep --dry-run` calls directly.
