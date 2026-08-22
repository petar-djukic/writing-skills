<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: inject-vernacular
description: >-
  Terminal, non-generative vernacular stage: apply the deterministic
  idiolect operators from writing-voice/idiolect.yaml (colon-verdicts,
  em-dashes, antitheses, connective and hedge swaps, spoken-marker strips,
  sentence splits) at per-register target rates, plus the substrate calque
  catalog (zapravo, recimo, ne ide) at site-matched landing spots.
  Substitution and restoration only — nothing samples, so it may run after
  every generative stage. Keeps a machine-readable edit log for marker-survival analysis; an
  optional verifier model judges each edit keep/drop but never writes.
  Triggers: inject vernacular, terminal stage, idiolect operators, apply my
  idiolect, restore my markers, vernacular pass.
---

# Inject Vernacular (terminal stage)

Every generative pass regresses text toward the model's distribution
center — the Strategy Theatre provenance logs showed match-voice injecting
bold lead-ins against instructions, tighten-style inventing a sentence,
and a rerun rewriting hand-cleaned prose eight times out of eight. The
voice therefore cannot be *protected* by prompts, and it cannot be
*restored* by another generative pass either. This stage is the answer to
the second half: a deterministic operator bank, applied mechanically, as
the LAST stage that writes. After it, models read but never write (the
humanize pipeline invariant).

## What it does

`scripts/inject_vernacular.py <draft.md|draft.yaml>` discovers
`writing-voice/` by walking up from the draft, loads `idiolect.yaml`, and
applies each marker's operator toward its `essay_target` (per 1000 words,
±30% tolerance before anything fires — the bank's `essay_target_rule`).
It refuses to run without the bank: this stage has no defaults, because
the operator bank IS the configuration.

Every edit is a substitution or restoration over text already in the
document or a fixed swap from the bank. Nothing samples; nothing is
generated. Runs are idempotent — a second pass over its own output makes
no edits.

| marker | operator here |
|---|---|
| colon-verdict | RESTORE: join "X. That is, / This means / In other words, y" into "X: y". REDUCE from the document's end (no provenance for "latest-added"). |
| em-dash | RESTORE: parenthetical asides become em-dash pairs. REDUCE: dash pairs back to parentheses. |
| antithesis-not | RESTORE: "X rather than Y" / "X instead of Y" → "X, not Y". REDUCE reverses it. |
| kind-of | Delete excess over the trace target, reverse document order; **never injected**. |
| okay, you-know | STRIP outside quoted speech; quoted speech survives. |
| right-tag | STRIP the ", right?" tag, keep the sentence. |
| so-initial | CAP: delete sentence-initial "So" above target; never injected. |
| ai-connectives | Sentence-initial "However," → "But"; "Moreover,/Furthermore,/Additionally," → "And". |
| i-think | REDUCE receipts-first (paragraphs carrying a number or citation lose their hedge first). RESTORE below target only at voice-critic unhedged-prediction flags (`--critic-flags report.json`): the flagged sentence gets an "I think" prefix, never past target, never on a sentence carrying a number or citation, and only when the first word is safely lowercasable (a determiner or pronoun — a possible proper noun skips the flag rather than risking "I think claude"). Which claims are unhedged predictions is the critic's judgment; the application stays deterministic over its spans. |
| maybe | "perhaps" → "maybe" always; excess capped. |
| sentence-length | SPLIT any sentence over 30 words at the semicolon or the top-level ", and/, but". MERGE is manual and never performed. |
| probably, be-able-to | RETAIN: structurally no-ops — never injected, never deleted. Listed in the report as intentionally untouched. |
| he-agent, article-density | Gate-read territory. The bank itself marks the referent/POS judgment not machine-checkable; this script never attempts them. |

### Calque operators (substrate layer)

The bank's `substrate.calques` catalog is applied by the same engine, as
injection-only site substitutions. A site is a regex over English that
marks where the Serbian form would land; the catalog records the Serbian
key and the English gloss, and this script owns the sites. There is no
REDUCE direction — an excess "actually" in its native sense is not the
calque, and removing it would be a register edit, not a substrate one.

| key | tier | site → substitution |
|---|---|---|
| zapravo | attested | a sentence-initial "But …" / "No, …" gets "actually" after its first copula or auxiliary ("But the gate is closed" → "is actually closed"); "you/we/they get/see/need/want" → "you actually get". |
| recimo | attested | sentence-initial "Suppose / Imagine" before a clause subject, "Say" before a pronoun or "that", and "For example/instance, you/we/I" → "Let's say". |
| ne ide | attested | "doesn't / does not / won't work" → "doesn't go", except before a phrasal particle (work out / on / with / …). |
| konkretno | proposed | sentence-initial "Specifically," → "Concretely,". |
| drzati predavanje | proposed | "give / gave a talk / lecture / presentation" → "hold / held a …". |
| doneti odluku | proposed | "make / made a decision" → "bring / brought a decision". |
| do petka | proposed | "by <weekday>" → "till <weekday>". |

Every other catalog entry (nekako, sve u svemu, kontrolisati, …) is
reported, not guessed at: `covered by marker kind-of` when the particle
table already routes it to a marker operator, `no site operator
(gate-read)` when no regex would land it without rewriting the native
sense too. `--calques` picks the tiers: `attested` (default), `proposed`
(both tiers), `none`.

The cap per entry follows the bank's `essay_target_rule`: an explicit
`essay_target` on the catalog entry wins, zero included; otherwise the
particle table's journal rate for that key, damped to the midpoint toward
the paper rate (zero for every calque), floored at the kind-of trace rate
(0.3/1000) so an attested entry with no journal rate still lands at trace.
The report names the source of each target. Budgets round to whole
applications, so a short draft under a real-bank target reports `below
target, budget rounds to zero` rather than pretending the target is met.

Each application is one edit-log entry (`calque:<key>`, with the tier and
site in its note), guarded by quoted speech and span locks like every
other operator, judged by the verifier when `--verify` is on, and
otherwise left to the author's gate read per `substrate.policy`.

Deviations from the bank's letter, where the bank asks for judgment a
mechanical stage cannot supply, are deliberate and visible in the report:
kind-of deletes in reverse document order rather than
"before-adjectives-first" (no POS tagging), and colon-verdict REDUCE works
from the document's end rather than "latest-added" (no provenance).

## Substrate policy — no diff ceremony

Per the 2026-08-21 amendment (idiolect.yaml `substrate.policy`): markers
are written directly into the text at target rates. No proposal tags, no
per-use approval, no diff presented to the author. The author's gate read
is the filter — he rewrites whatever reads unnatural, and marker survival
across the gate (observable from git history) informs promotion and
retirement in the bank.

The machine-readable edit log exists for that survival analysis, not for
review: every edit — kept and dropped — lands in
`<draft>.vernacular.json` (or `--edit-log PATH`) with operator, paragraph,
and full before/after text. Replaying the kept entries reproduces the
entire diff; the tests hold that as an invariant.

## Span locks

Protection is inherited from the shared drivers, not re-implemented:
block-locked regions never reach this script, and inline locks travel as
`[[LOCK-n]]` anchor tokens no operator pattern can match. A locked "okay"
survives; an unlocked one is stripped.

## The verifier gate (optional)

`--verify` judges each mechanical edit with an Ollama model
(`--model`, `--endpoint`; same defaults and no-silent-fallback rule as
match-voice): the model answers KEEP or DROP, a dropped edit reverts, and
the model's text goes nowhere — **the verifier judges, it never writes**.
Requested but unreachable is a hard error, not a skip. Without `--verify`
every mechanical edit stands, which is the normal offline mode.

## Pipeline position

Terminal. Stage order: draft (with declared/locked spans) → humanize
stages (lock-respecting) → **inject-vernacular** → read-only zone
(Pangram, voice-critic, cold reads, author gate). Defects found after this
stage are fixed by the author's hand or by re-running from a pre-terminal
checkpoint — never by a model repair on the final text. Snark and
disproportion are born at drafting and locked; this stage never inserts
them (mechanical joke insertion is prohibited by design).

## Usage

```bash
# normal run: apply in place, write the edit log
python3 scripts/inject_vernacular.py draft.md

# report only
python3 scripts/inject_vernacular.py draft.md --dry-run --json

# with the keep/drop verifier
python3 scripts/inject_vernacular.py draft.md --verify --model gemma4:12b

# proposed-tier calques too (default is attested only; --calques none disables)
python3 scripts/inject_vernacular.py draft.md --calques proposed
```

Tests: `scripts/test_inject_vernacular.py` (offline; synthetic bank, no
model, no network).
