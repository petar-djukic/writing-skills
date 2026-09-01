<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: cold-review
description: >-
  Fresh-context entailment check with a fixed contract: a reviewer that
  never saw the drafting conversation reads baseline + candidate,
  paragraph-aligned, hunting inverted claims, numbers reattached to
  wrong claims, altered quotations, and hedges that change assertions;
  verdicts limited to ship as-is / ship with listed verbatim-reverts /
  reject. Every accepted fix is a revert to the baseline span — no
  authored prose. Ships a mechanical drift screen and a revert applier
  with invariant re-checks. Triggers: cold review, cold read the
  candidate, entailment check, fresh-context review, did the rewrite
  change the meaning, revert list.
argument-hint: 'screen|apply --baseline <b.md> --candidate <c.md>'
---

# Cold Review (fresh-context entailment, reverts only)

Every generative stage measured against a cold read lost most of its raw
gain there, and the two 2026-09-01 runs that fixed this contract caught
real damage both times: swapped 0.768/0.867 arm numbers, an inverted
improvement direction, a lost constitution bridge sentence — and, on the
second run, confirmed ship-as-is with zero reverts, which is also a
result. The prompt was re-improvised per run; now it is versioned.

## The contract

- **Fresh context, maker is not checker.** The reviewer sees only the
  baseline, the candidate, the caller's named high-value targets, the
  constitution's [CHECK] items when the form has one, and the mechanical
  screen's findings. Never the rewrite history, reasoning, or diffs.
- **Meaning entailment, paragraph by paragraph**: inverted claims,
  numbers reattached to wrong claims, altered quotations (including
  reattributed judgment), hedges that change assertions, [CHECK] items
  no longer satisfied.
- **Closed verdict vocabulary**: `ship as-is` | `ship with reverts:
  p<N>: <damage>` | `reject candidate: <why>`. The reviewer never
  proposes prose.
- **The repair rule**: every accepted fix is a verbatim revert to the
  baseline span — kept-original at paragraph level, no authored prose.
  Damage that reverts cannot save (structural) rejects the candidate.

The prompt template with slots is
[references/review-prompt.md](./references/review-prompt.md).

## The scripts (deterministic halves)

```bash
# recall aid for the reviewer: mechanical drift per aligned paragraph
python3 <skill>/scripts/cold_review.py screen \
  --baseline base.md --candidate cand.md [--json]

# apply an accepted revert list, verbatim, with invariant re-checks
python3 <skill>/scripts/cold_review.py apply \
  --baseline base.md --candidate cand.md --revert "3,7" --out gated.md
```

`screen` flags number-multiset changes (citations masked), citation
changes, and altered double-quoted spans; it is a recall aid, not the
review — an inverted claim carries the same numbers and only the model
catches it. `apply` swaps the named paragraphs back to the baseline text
and re-checks the invariants on the written bytes: locked spans
preserved, paragraph count stable, reverted paragraphs byte-identical to
baseline. Both refuse mismatched paragraph counts — the chain rewrites
1:1, and a count drift means index reverts would land on the wrong text.

## Position

Caller's review phase (GH-208), after critic-apply and before
voice-critic: the gated candidate is what the scores are believed on.
Read-only plus reverts — a revert authors nothing, so running it after
the terminal stage does not violate the GH-57 contract.

Offline tests: `scripts/test_cold_review.py` (a planted number swap
yields a revert list naming it; the applier restores baseline bytes).
