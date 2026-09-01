<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: critic-apply
description: >-
  Rule-based application of a converged critic sheet: accept every
  convergent target (2+ critics), skip split panels, decline
  constitution-protected spans with cause, prefer the omission when
  remedies conflict, and count reverse-outline cheap ranks as
  convergence for single-critic deletions. Rewrites route through the
  rewrite transport with a narrow one-sentence instruction and a
  mechanical gate (numbers, citations, em-dash/colon budgets, size
  band); deletions apply directly; rst markers round-trip. Reports
  applied/kept/declined-by-rule for the generation: block. Triggers:
  critic apply, apply the critic sheet, apply the panel, apply
  suggestions by rule, converged sheet application.
argument-hint: '--article <draft.md> --sheet <stem>.critic-sheet.md'
---

# Critic Apply (rule-based sheet application)

critic-panel produces the sheet and never applies anything; the author
used to pick by hand, and the auto-application policy (operator,
2026-09-01) ran twice as throwaway scratchpad scripts. This skill is
that policy as versioned code: the author never reads drivel because the
rules decide, and the rules are arguable because they are deterministic.

## The rules

| rule | effect |
|---|---|
| convergent target (2+ distinct critics on one passage) | accepted |
| split panel (a proposal beside a KEEP/NO CHANGE dissent) | skipped — proposal + dissent is not convergence |
| constitution-protected span (`--protected` verbatim spans) | declined with cause, however many critics want it — the constitution outranks the panel |
| remedy conflict inside a convergence, one remedy a CUT | the omission wins — a deletion authors no prose |
| single-critic CUT on a paragraph reverse-outline ranked cheap (`--cheap-paragraphs`) | accepted — cross-instrument agreement counts as convergence for deletions |
| any other single-critic finding | skipped; the author picks those by hand |

## The mechanics (learned the hard way)

- **rst markers are stripped before the model call and reattached
  after** — their digits fail the number gate (measured on the first
  automated run). A deleted paragraph takes its marker line with it.
- **One narrow instruction per rewrite target**, built from the
  critics' *why*, sent through the rewrite transport
  (`CRITIC_APPLY_MODEL`, default `cohere:command-a-03-2025`) — persona
  prose is never spliced; it is guidance at most.
- **The gate**: number multiset (citations masked first), citation
  multiset (`[@key]` and `[n]`), em-dash and colon counts capped at the
  original's, candidate length within 0.5–1.35× of the original. A
  gated rejection keeps the original, recorded with its reason.
- **Deletions apply directly** with mechanical punctuation
  normalization; omission is not authorship.

## Usage

```bash
python3 <skill>/scripts/critic_apply.py \
  --article draft.md --sheet draft.critic-sheet.md \
  [--protected constitution-spans.txt] \
  [--cheap-paragraphs 3,7] \
  [--dry-run]
```

Output: `<stem>.applied.md` plus `<out>.critic-apply.json` — per-target
records and the applied/kept/declined-by-rule summary the `generation:`
block wants. `--dry-run` decides and reports with no model calls and no
writes. Offline tests: `scripts/test_critic_apply.py`.

## Position

Caller's review phase (GH-208), directly after critic-panel's merge:
sheet → critic-apply → the applied text re-enters the humanize chain as
a new cycle (applied targets are unlaundered rewrite-transport prose).
cold-review and voice-critic read the result; this skill never runs
after the terminal stage of the same cycle.
