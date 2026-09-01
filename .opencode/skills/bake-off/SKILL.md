<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: bake-off
description: >-
  Multi-payload model comparison as a first-class skill: arms through the
  real pipeline over real published material, >= 2 payloads before any
  verdict, seed-pinned replays, one Pangram framing per table, scores
  read together with per-model error forensics, dated results re-run on
  pipeline change. Owns the harness (sweep / replicate / bakeoff arms,
  any model the shared transport routes) and the report template.
  Triggers: bake-off, bakeoff, model comparison, A/B the models, which
  model should the stage use, re-pin the default, sweep the arms.
argument-hint: 'bakeoff <draft.md> --out-dir <dir> (see scripts/bakeoff.py)'
---

# Bake-off (multi-payload model comparison)

The methodology ran four times in one arc (GH-160, GH-166, GH-168,
GH-170) and re-pinned two pipeline defaults, but it lived as a
match-voice script plus discipline carried in issue prose — a fifth run
meant re-deriving the discipline again. This skill owns both: the
harness and the contract.

## The method contract

Every rule below has a run that broke without it.

1. **>= 2 payloads, real published material, never toy prompts.**
   Single-draft verdicts reversed twice (GH-160 vs GH-166/168). A
   verdict from one payload is a note, not a result.
2. **Arms run through the REAL pipeline, not bare prompts.** The prompt
   scaffold, the gate, and the retry loop are part of what is being
   measured; a bare-prompt arm measures a pipeline nobody runs.
3. **Read scores and per-model error forensics together.** Obedient
   models expose YOUR prompt bugs — GH-171's discovery path took
   citation survival from 46% to 88% by reading the error log of the
   model that followed instructions too well.
4. **Seed-pin every arm** (`COHERE_SEED`, verified bit-identical at
   temp 0.9) so any arm replays exactly. Do NOT best-of-N over seeds:
   the null measured 5 seeds within 0.003 Pangram — the detector reads
   register, not phrasing.
5. **One Pangram framing per table.** Slice / whole / prose-only scores
   of the same article measured 0.225 / 0.913 / 1.000 — a table mixing
   framings compares nothing. Uploads run under the consent rule
   (per-document, or the operator's standing grant, GH-210).
6. **Date every verdict and re-run on pipeline change.** Rankings are
   model x pipeline; the GH-194 re-pin overturned a July ranking without
   any model changing.

## The harness

`scripts/bakeoff.py` (promoted from `match-voice/scripts/cohere_ab.py`,
GH-205 — the name stopped saying cohere because it drives any model the
shared transport routes):

```bash
# 2 Cohere models x 2 prompt-shape arms over citation/number paragraphs
python3 <skill>/scripts/bakeoff.py sweep <draft.md> [--out results.json]

# the GH-153 disputed passage, repeated
python3 <skill>/scripts/bakeoff.py replicate [--trials 6]

# Cohere models AND the Ollama incumbents over one draft; assembles one
# rewritten draft per model for whole-document register measurement
python3 <skill>/scripts/bakeoff.py bakeoff <draft.md> --out-dir <dir>
```

Scoring is mechanical (`score()`): citation and number multisets,
meta-commentary hits, word counts. Detector and register measurements
run on the assembled per-model drafts with the usual tools.

## Report template

Per payload, then pooled:

| arm | clean | citations kept | numbers kept | detector (one framing) |
|---|---|---|---|---|

followed by a **replicated / reversed** section (which prior verdicts
this run confirms or overturns, by issue number) and a **limits** line
(payload count, arm isolation, sampling depth). Verdicts carry a date.

## Worked example (recorded): the GH-194 re-pin

Two published payloads (loop-engineering, prompts), seed and iterator
isolated on raw articles, prose-only framing throughout:

| arm (seed -> iterator) | loop (base 1.000) | prompts (base 0.913) | mean |
|---|--:|--:|--:|
| pinned: gemma-anchored -> gpt-oss | 1.000 | 0.734 (3 passes) | 0.867 |
| cohere-anchored -> gpt-oss | 0.896 | 0.913 | 0.904 |
| gemma-anchored -> cohere | 1.000 | 0.909 | 0.955 |
| **cohere -> cohere** | **0.802** | **0.735** | **0.768** |

Replicated/reversed: overturned the July gemma->gpt-oss pin (humanize
now carries the Cohere recipe); confirmed the GH-160/166 lesson that the
single-payload verdict would have picked differently. Limits: n=2,
stop-on-upturn sampled once per pass. Dated 2026-08-31. The full run
record and the earlier prompt-shape arms are in
[references/cohere-bakeoff.md](./references/cohere-bakeoff.md).

## Position

A data tool, not a chain stage (GH-208 taxonomy): it measures models so
the chain's defaults can be pinned; it never touches an article anyone
ships. Offline tests: `scripts/test_bakeoff.py`.
