<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: voice-critic
description: >-
  Cold, read-only gatekeeper against writing-voice/voice-constitution.md:
  five per-dimension verdicts with flagged spans — stance, theory-of-mind
  device, disproportion (locked-span check), computed marker profile
  against idiolect targets, and a snark audit on the constitution's L0-L5
  scale with receipt-first, safe-enemy, and per-form density-cap hard
  rules. Never edits; flags route to the author gate. Triggers: voice
  critic, does this sound like me, snark audit, constitution check, voice
  gate, critique voice, off-voice check.
---

# Voice Critic (read-only gatekeeper)

filter-tells detects "sounds like a machine". This critic detects two
different failures: "doesn't sound like Petar" and "went too far". The
rubric is `writing-voice/voice-constitution.md` — discovered by the
standard walk-up, refused when absent, because the critic's taste is that
file, not anything built in. Rates come from `idiolect.yaml`, the single
source of truth the constitution itself defers to.

**Read-only is the contract.** `scripts/voice_critic.py` takes a document
and produces a report; it never modifies the input, and the tests assert
input bytes unchanged. That is why it may run after the terminal
inject-vernacular stage — the read-only zone of the pipeline — and equally
at any earlier gate; nothing in it assumes pipeline position.

**The critic flags; the author adjudicates.** It replaces self-monitoring
with a checklist, not with enforcement: over-ceiling snark is flagged,
never auto-deleted, and every flag carries the quoted span and line range
so the gate read is a yes/no per item.

## The five dimensions

| dimension | how | what it asks |
|---|---|---|
| stance | judged | Expert-watching, curiosity not contempt (§1)? At the bench, not the balcony? |
| tom-device | screened + judged | Model stated → predictions derived → tested against the artifact (§2)? The deterministic screen finds candidate evidence for each of the three parts; the judge (or the author) says whether the device is executed. |
| disproportion | computed | One declared overrun present and protected? Span locks are the declaration mechanism, so this reads the drivers' lock report. |
| marker-profile | computed, never judged | idiolect.yaml regex rates against essay targets, ±30% tolerance — the same arithmetic inject-vernacular applies as operators, run here as a check. |
| snark-audit | judged instances, computed rules | Every instance scored L0–L5; then the three hard rules run mechanically over the instances. |

## Snark scale and hard rules (constitution §4)

Levels: L0 none · L1 dry aside · L2 pointed irony with receipt · L3 open
mockery of an artifact (polemic only) · L4 contempt for a class · **L5
ridicule of a person — never**, always a violation.

Hard rules, checked mechanically over judge-identified instances:

1. **Receipt-first.** A receipt (number, percentage, citation, quoted
   material) must appear before the joke — earlier in the same paragraph,
   or anywhere in the preceding one (the factual-run-then-verdict shape).
2. **Safe-enemy only.** Allowed targets: artifact, institution, category,
   the dead, past self. A person target is a violation.
3. **Density caps** per 1000 words by form, counting L1 and above:
   how-to 1, essay 2, polemic 3 (`--form`, default essay).

Any hard-rule violation makes the snark dimension FAIL and the flagged
instances land in the report for the author gate.

## Judged vs computed, and the judge's leash

Computed dimensions are deterministic and run offline. Judged dimensions
use a model **in read-only mode**: it returns verdicts, levels, and exact
quotes — its text is never spliced anywhere. `--judge` wires an Ollama
model (`--model`, `--endpoint`; unreachable-when-requested is a hard
error, no silent fallback). Without a judge, judged dimensions report
`UNJUDGED` with their screen evidence, and the author gate adjudicates —
which is the normal offline mode, not a degraded one.

## The unhedged-prediction work list (for inject-vernacular)

Beside the five verdict dimensions, a judged report carries
`unhedged_predictions`: sentences that state a claim about a mind —
beliefs, motives, future behaviour — with no hedge and no receipt,
identified by the judge and then receipt-filtered mechanically (a
sentence carrying a number or citation is dropped; the bank never hedges
a receipted claim). Each entry has the paragraph index, line range, and
exact quote. It is a work list, not a verdict: feed the report to
`inject_vernacular.py --critic-flags report.json` and its i-think
RESTORE operator applies the hedge deterministically at those spans.
Without a judge the list is empty — the offline mode. The read-only
contract holds: the critic names the spans, the terminal stage does the
writing.

## Scope boundary with filter-tells

- **filter-tells**: machine tells — AI lexicon, structural patterns, CoT
  leakage. Register-generic; a document by any author can fail it.
- **voice-critic**: this author's constitution — stance, method,
  signature-marker rates, snark governance. A flawlessly human text by
  someone else fails it; that is the point.

Run both: they catch disjoint failures, and after GH-57's calibration work
filter-tells reads the same idiolect.yaml so the two never fight over
constructions native to the voice.

## Usage

```bash
# offline: computed dimensions + screens, judged dimensions UNJUDGED
python3 scripts/voice_critic.py draft.md

# full: judged dimensions through a local model (read-only)
python3 scripts/voice_critic.py draft.md --judge --model gemma4:12b

# polemic caps, machine-readable report for the gate checklist
python3 scripts/voice_critic.py draft.md --form polemic --json --report out.json
```

Exit 0 when no dimension FAILs, 1 otherwise. Tests:
`scripts/test_voice_critic.py` (offline; stub judges, no network).
