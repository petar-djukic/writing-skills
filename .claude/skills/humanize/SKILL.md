---
name: humanize
description: >-
  Three-step pipeline to move AI-drafted prose to human-passing on Pangram:
  a configurable structural step (match-outline for section-level rewriting,
  tighten-style for paragraph-level tightening, or skip), filter-tells
  (semantic cleanup), then match-voice --no-anchors (paragraph diction).
  Parameterized blueprint and anchor-tag selection, inter-step Pangram
  measurement, consolidated five-category writing-quality report. Venue mode
  (--venue <name>) resolves every choice from a writing-voice/venues/
  profile instead of asking. Carries the pipeline's ordering contract:
  locked spans respected by every stage, inject-vernacular terminal, and
  after the terminal stage models read but never write. Triggers: humanize,
  humanize article, make it human, full rewrite pipeline, rewrite for
  pangram, three-step rewrite, humanize for venue.
---

# Humanize (three-step pipeline)

Orchestrates the three prose skills that together move an AI-drafted article
away from a 100% AI verdict on Pangram. The verified effect (2026-07-29,
working gate) is 100% AI -> Mixed: 23.8% AI / 76.2% AI-assisted, mean window
0.993 -> 0.576. Each step exists because the other two cannot compensate for
its absence.

## Why three steps

| step | what it does | what happens without it |
|---|---|---|
| structural step (match-outline or tighten-style) | changes enough sentence structure that the downstream paragraph rewriter can clear the mechanical gate — match-outline rewrites at section level against a blueprint, tighten-style tightens paragraph by paragraph toward the author's density floor | match-voice rewrites land at distance 0.0 from the original; the gate rejects every paragraph and nothing changes (unverified — measured against the broken gate, see calibration note) |
| filter-tells semantic cleanup | collapse antithesis pairs, remove CoT leakage, cut recap ballast, fix banned words | Pangram score stays at 100% AI even after match-voice, because the rhetorical patterns survive diction changes |
| seeded iteration (Phase 3) | seed in a second model family, then iterate the first --no-anchors to the score floor | unseeded, the iterator substitutes its own diction instead of stripping the old fingerprint: measured 0.609 gated, against 0.370 seeded, on the same article |

The compound effect: semantic cleanup alone does not move Pangram (rhetorical
patterns are not what it measures). Both steps together, with the structural
step providing the divergence, moved the verified run from 100% AI to
Mixed (76.2% AI-assisted, mean window 0.576). The ablation rows that showed
match-voice alone gate-rejected at distance 0.0 were measured against the
broken gate (GH-318) and are unverified — see the calibration note at the
end.

## Stage order and the read-only-after-terminal invariant (GH-57)

The full pipeline, in order:

```
draft (with declared/locked spans)
  -> humanize stages, lock-respecting (structural step, filter-tells,
     match-voice)
  -> inject-vernacular (terminal — the last stage that writes)
  -> read-only zone (Pangram, critic-panel, then voice-critic, cold
     reads, author gate — critic-panel precedes voice-critic because its
     author-accepted picks change what voice-critic audits)
```

**After the terminal stage, models may read but never write.** The
evidence behind the rule is the Strategy Theatre provenance logs: every
generative pass regresses text toward the model's distribution center —
match-voice injected bold lead-ins despite instructions, tighten-style
invented a sentence, and a step-6 rerun rewrote hand-cleaned prose 8/8
times until the entailment gate rejected all of it. So the ordering is a
contract, not a preference. A defect found after the terminal stage is
fixed by the author's hand, or by re-running from a pre-terminal
checkpoint — never by an additional model repair on the final text, which
would put a generative pass after the stage that exists to be last.

Three rules the order encodes:

1. **Locks travel the whole pipeline.** Spans marked `<!-- lock -->` …
   `<!-- /lock -->` at drafting are excised by the shared drivers before
   any model call and spliced back byte-identical after, in every stage —
   protection is mechanical, enforced in `prose_document.py` /
   `md_paragraphs.py`, never by prompts.
2. **inject-vernacular is terminal because it is deterministic.** It
   applies the idiolect.yaml operator bank by substitution and
   restoration only; nothing samples, so it cannot regress the text
   toward a model's center — which qualifies it to run after every stage
   that can.
3. **Snark and disproportion are born at drafting and locked.** The
   terminal stage never inserts them: mechanical joke insertion is
   prohibited by design. voice-critic audits them in the read-only zone
   (L0–L5 scale, receipt-first, density caps) and flags to the author
   gate; it never edits.

## Why no anchors for match-voice

Every anchor configuration tested made Pangram scores worse. gpt-oss
unconstrained produces formal Latinate prose (passive, nominalized, complex
sentences) that does not match Pangram's training distribution of
conversational AI text. Anchors constrain gpt-oss into register patterns
Pangram catches. See calibration data at the end.

## Prerequisites

- Ollama endpoint reachable with `kimi-k2.6:cloud` and `gpt-oss:120b-cloud`
- A `writing-voice/` directory with exemplars and at least one blueprint
  under `writing-voice/blueprints/`
- For Pangram measurement: an API key configured per the match-voice
  credential contract (`.secrets/keys.json` with `"pangram"` entry)

## Contract-field protection (GH-362)

YAML spec files carry contract fields (section_goal, goals, acceptance
criteria, metadata) whose values are terse, lowercase phrases the repo's
audit tools grep for. The pipeline protects them in two layers:

**Exclude keys.** Both tighten.py and drive.py accept `--exclude-keys` with
dot-separated key-path globs. For YAML files, the default exclusion list is
`section_goal`, `goals.*.goal`, `acceptance.*`, `meta.*`. These paragraphs
get status `excluded-key` and never reach the rewriter. Pass `--exclude-keys`
with no arguments to disable the default.

**Guard phrases.** verify.py accepts `--must-preserve` with exact phrases
that must survive rewriting unchanged. A candidate that loses a guard phrase
is rejected (fatal finding) and the original text is kept. Use this for
claims-integrity markers like "recorded as planned", "no number is cited",
"submission-status care" that the repo's claims audit greps for.

**ASCII normalization.** verify.py normalizes typographic unicode (curly
quotes, non-breaking hyphens and spaces, en-dashes) to ASCII before running
any check. A rewrite that reintroduces them is caught by the gate rather
than silently passing.

When running the pipeline on spec YAML, the exclude-keys defaults apply
automatically. For guard phrases, pass them explicitly on the drive.py or
tighten.py command line, or configure them in the venue profile.

## Procedure

### Phase 0: Discover and choose targets

1. Discover `writing-voice/` by walking up from the article path.
   Error if not found.

1b. **Venue mode (GH-336).** If the user named a venue (`--venue <name>`, or
   "humanize this for the book/newsletter/..."), resolve the profile and skip
   the interactive questions below:

   ```bash
   $RUN <match-structure>/scripts/venue_profile.py show \
     --venue <name> --for <article.md>
   ```

   A profile that fails validation is refused — report the errors and stop;
   never fall back to guessing. From the resolved profile:

   | profile field | replaces |
   |---|---|
   | `structural_step` | the step question (step 2) |
   | `blueprint`, `anchor_query` | the blueprint/tags questions (step 3) |
   | `targets`, `hedge_policy` | tighten-style's floor: pass `--venue <name>` to tighten.py in Phase 1 |
   | `tell_lexicon` | the lexical catalog: pass `--lexicon=<value>` in Phase 2 |
   | `gates` | which measurements run: no `pangram` gate → skip every Pangram scan in every phase (the consent rule still governs uploads when the gate IS present) |
   | `citations` | which citation markers to spot-check after each step (`[1]` numbered vs pandoc `[@citekey]` — both must survive every rewrite verbatim) |

   List venues with `venue_profile.py list --for <article.md>` when the user
   asks what is available. No venue named, or no `venues/` directory → the
   interactive flow below, unchanged.

2. Ask the user which structural step to run:

   | choice | when to use | what it does |
   |---|---|---|
   | match-outline | article structure needs section-level rewriting (new blueprint, different register) | section-level rewrite via Kimi with chosen blueprint and anchor-tags |
   | tighten-style | article structure is sound, paragraphs need tightening toward author density | paragraph-level rule-keyed rewriting via Ollama with anchor-gated verification |
   | skip | article already structurally rewritten (e.g. resuming after step 1) | proceed directly to filter-tells |

3. **If match-outline was chosen**, list available blueprints and tags, then
   ask which to use:

   ```bash
   ls <repo>/writing-voice/blueprints/*.md
   ```

   ```bash
   RUN="pixi run --manifest-path <agent-dir>/pixi.toml python"
   $RUN <match-structure>/scripts/voice_anchors.py \
     --voice-dir <repo>/writing-voice tags
   ```

   If the `tags` subcommand is not available, parse distinct tag values from
   `writing-voice/manifest.yaml` directly. If only one blueprint exists,
   propose it as the default. Show the available tags and let the user choose
   (or skip tags for untagged retrieval).

   **If tighten-style was chosen**, no blueprint or tag question is needed —
   it uses the writing-voice corpus floor and its rule catalog.

4. Capture baseline measurements:

   ```bash
   # Pangram baseline (one-shot scan; uploads the prose, costs a scan)
   $RUN <agent-dir>/scripts/pangram_report.py scan --article <article.md>

   # Style baseline
   $RUN <match-structure>/scripts/style.py profile <article.md>
   ```

   Record the baseline Pangram scores (human %, mean window score, verdict)
   and the full `text_metrics()` output. These are the "before" column in the
   final report. With the `skip` choice, capture the baseline and proceed to
   Phase 2. In venue mode, capture the Pangram baseline only when the
   profile's gates include `pangram`.

### Phase 1: Structural step

Run the step chosen in Phase 0. With `skip`, proceed directly to Phase 2.
Locked spans pass through untouched — both tools extract paragraphs through
the shared drivers, which excise `<!-- lock -->` spans before the model
sees the text and splice them back byte-identical.

**match-outline** — rewrite the whole article via `match_outline.py
--rewrite` with the user's chosen blueprint and anchor-tags:

```bash
$RUN <match-outline>/scripts/match_outline.py <article.md> \
  --voice-dir <repo>/writing-voice \
  --anchor-tags <chosen-tags> \
  --blueprint <chosen-blueprint> \
  --model kimi-k2.6:cloud \
  --rewrite
```

The output is `<article-stem>-rewritten.md` next to the original.

**tighten-style** — survey the findings, then tighten paragraph by
paragraph with the anchor-gated verifier:

```bash
$RUN <tighten-style>/scripts/check_style.py <article.md>
$RUN <tighten-style>/scripts/tighten.py --article <article.md> \
  --out <article-stem>-tightened.md
```

(Pass `--out` explicitly: tighten.py's default output name is
`<stem>.tightmd`, which the rest of this pipeline does not expect.
In venue mode add `--venue <name>` — the profile's targets become the
sentence floor and its hedge policy sets the TS-08 threshold.)

Either way, the output is expected to remain AI-flagged — the structural
step provides divergence, not diction cleanup.

Verify the rewrite preserved content: check that citations, numbers, code
blocks, and figures survived. Both tools run their own guards
(match_outline.py a similarity guard, tighten.py the match-voice gate), but
spot-check the sections that carry data.

Measure after the structural step:

```bash
$RUN <agent-dir>/scripts/pangram_report.py scan --article <step1-output.md>

$RUN <match-structure>/scripts/style.py profile <step1-output.md>
```

Record as the "after step 1" column.

### Phase 2: filter-tells semantic cleanup

Run the lexical and structural scans on the step-1 output (or the original
article when the structural step was skipped). Block-locked regions never
enter the scans' prose view, and semantic edits are applied through the
lock-respecting drivers — a locked antithesis or authored snark span is
not filter-tells' to collapse. With `writing-voice/idiolect.yaml`
discoverable, the structural scan calibrates to the author baseline:
native constructions flag only above the author ceiling, and calibrated
flags say reduce toward the target, not to zero.

```bash
bash <filter-tells>/scripts/detect-lexical.sh <step1-output.md>
$RUN <filter-tells>/scripts/detect-structural.py <step1-output.md>
```

In venue mode pass `--lexicon=<tell_lexicon>` to detect-lexical.sh — the
newsletter banned-word list must not drive edits on an academic methods
section, and the academic lexicon adds paper-template tells the default
list does not carry.

Apply the semantic edits following the filter-tells Step 3 procedure. The
edits that matter most for this pipeline:

1. **Antithesis pairs** — collapse every negation-flip pair into a single
   sentence. These are the dominant AI rhetorical pattern. Target: 0 pairs.
2. **CoT leakage** — delete bridge sentences that add no information.
   Apply the removal test: delete the sentence, re-read the paragraph.
   If nothing is lost, it was scaffolding.
3. **Recap ballast** — compress paragraphs that restate earlier points
   without adding new information.
4. **Banned words** — swap any remaining banned words (check the lexical
   scan output).
5. **Author-stance narration** — sentences written from the author's chair:
   scope negotiation ("here we deal with", "this article covers"), and system
   facts stated as author experience ("waiting for my approval"). Rewrite as
   claims about the system ("a human approves it before it exists"). The
   bridge sentence and the learning-objectives paragraph are the sanctioned
   exceptions; everything else in this register goes.

After editing, re-run both scans to confirm:
- Structural verdict: MINOR-ISSUES or better (was LIKELY-AI)
- Antithesis pairs: 0
- No banned words

Measure after filter-tells:

```bash
$RUN <agent-dir>/scripts/pangram_report.py scan --article <step1-output.md>

$RUN <match-structure>/scripts/style.py profile <step1-output.md>
```

Record as the "after-tells" column.

### Phase 3: seeded iteration (seed in a second family, then iterate)

**Run the seed. It is the mechanism, not an enhancement.** A single
unseeded match-voice pass has only its own distribution to push against,
so it substitutes diction instead of stripping it. Seeding with a
different model family first leaves a foreign fingerprint the iterator
has something to erase — and that difference decides whether the phase
helps or hurts.

Measured on strategy-theatre (2026-08-22), same article, same iterator,
same cold-review standard:

| variant | review-gated result | verdict |
|---|---|---|
| unseeded single pass | 0.609 ai, against a 0.375 baseline | dropped |
| **seeded iteration** | **0.370 ai / 0.550 human** | **kept** |

The unseeded pass is retained below as a named ablation. Choosing it is a
deviation a run has to state and justify.

#### 3.1 Seed — a different family, anchored

```bash
$RUN <match-voice>/scripts/drive.py \
  --article <cleaned.md> \
  --model gemma4:31b-cloud \
  --anchor-tags <tags that select one author's exemplars> \
  --voice-dir <repo>/writing-voice \
  --out <seed.md>
```

Anchor by **tags**, not `--author`: the corpus carries no author field, so
`--author` selects an empty pool and aborts (writing-skills GH-98). Pick
tags exclusive to the author you want — `parable,ledger-read` selects the
22 Krugman exemplars and nothing else. Verify the pool size before
trusting the run:

```bash
$RUN <match-structure>/scripts/voice_anchors.py tags --voice-dir <repo>/writing-voice
```

The seed is expected to score badly on its own. That is not failure; a
seed that scores well has not changed the fingerprint.

#### 3.2 Iterate — the first family, no anchors, stop at the upturn

```bash
PREV=<seed.md>
for i in 01 02 03 04; do
  $RUN <match-voice>/scripts/drive.py --article $PREV \
    --model gpt-oss:120b-cloud --no-anchors --pangram \
    --canonical-blocks <repo>/writing-voice/canonical-blocks.txt \
    --out pass$i.md
  PREV=pass$i.md   # read the score; STOP at the first upturn
done
```

Three rules, all load-bearing:

1. **Score every pass and stop at the first upturn.** Never run a fixed
   count. The floor is typically pass 1–4; past it each pass concentrates
   the iterator's own signature and the score climbs back.
2. **The publish candidate is the floor pass, not the last pass.** Keep
   every pass on disk with its provenance.
3. **Cold-review the floor pass before believing its score.** Every stage
   measured this way lost most of its gain at review — the raw floor and
   the gated floor are different numbers, and only the gated one counts.

**Pass `--canonical-blocks` explicitly** when the article is staged
anywhere but its repo: discovery walks up from the article path, so a run
staged in a scratch directory silently has no registry and will rewrite
the disclosure and subscribe lines.

#### 3.3 Ablation: the unseeded single pass

Run the paragraph-level diction rewrite with no voice anchors and no seed. Inline
locks reach the rewriter as opaque `[[LOCK-n]]` anchor tokens; a rewrite
that drops one is refused by the drivers and the original paragraph is
kept — the locked bytes cannot be lost to this phase.

```bash
$RUN <match-voice>/scripts/drive.py \
  --article <rewritten-and-cleaned.md> \
  --model gpt-oss:120b-cloud \
  --no-anchors \
  --pangram \
  --out <output.md>
```

In venue mode, include `--pangram` only when the profile's gates carry
`pangram`; a venue without that gate (academic) is never uploaded to the
external detector.

Check the output for:
- `accepted-mechanical` count (should be most paragraphs, not `kept-original`)
- Distance > 0 (confirms the gate accepted rewrites)
- Pangram verdict and mean window score (when the gate ran)

Measure final style:

```bash
$RUN <match-structure>/scripts/style.py profile <output.md>
```

Record as the "after-voice" column.

### Phase 3b: iteration calibration (reference)

A single no-anchors pass leaves most windows near 0.75. Iterating the
Phase 3 rewrite on its own output keeps stripping the previous model's
fingerprint — up to a point. Measured on the stay-on-track article
(2026-07-29, experiments/2026-07-29-gptoss-iter/): the per-pass mean
window traces a **U-curve** — 0.992 -> 0.579 -> 0.432 (55% human) ->
0.489 -> 0.418 -> then monotonic regression back to 0.70 by pass 10.
Past the floor, each pass concentrates the rewriter's own single-family
signature, which is exactly what Pangram's synthetic-mirror training
detects (arXiv:2402.14873).

Rules:

1. **Seed with a different family than the iterator.** The best floor
   came from seeding with an anchored gemma pass (Krugman tags) that
   itself scored 0.992 — useless as an endpoint, useful as a seed. The
   iterator (gpt-oss) then has a foreign fingerprint to erase.
2. **Score every pass** (`--pangram`) and **stop at the first upturn**.
   Never run a fixed pass count. The floor is typically pass 2-4.
3. **Keep every pass on disk** with its provenance YAML; the publish
   candidate is the floor pass, not the last pass.
4. **Expect decay.** Pangram retrains on new model families; a floor
   measured today drifts up as the iterator model enters their mirror
   set. Re-measure before reusing a recipe.

```bash
PREV=<seed.md>
for i in 01 02 03 04; do
  $RUN <match-voice>/scripts/drive.py --article $PREV \
    --model gpt-oss:120b-cloud --no-anchors --pangram \
    --out pass$i.md
  PREV=pass$i.md   # read mean window from pass$i.generation.yaml; stop on upturn
done
```

### Phase 3c: inject-vernacular (terminal)

When the repository carries `writing-voice/idiolect.yaml`, run the
terminal vernacular stage on the Phase 3 (or 3b floor-pass) output:

```bash
$RUN <inject-vernacular>/scripts/inject_vernacular.py <output.md>
```

Deterministic operators only — it restores the author's markers toward
the bank's essay targets and writes an edit log for the survival
analysis; nothing samples. This is the last stage that writes. Everything
after this line — the Phase 4 report, any final Pangram scan, a
voice-critic run, cold reads, the author gate — reads the text and never
modifies it. A defect found from here on means the author's hand or a
re-run from a pre-terminal checkpoint. No idiolect.yaml → skip this
phase; the invariant then attaches to the end of Phase 3.

For the gate checklist, run the read-only critic on the final text:

```bash
$RUN <voice-critic>/scripts/voice_critic.py <output.md> --form essay
```

### Phase 3d: run-completeness check

Before the report, state what actually ran. A partial run must report
itself as partial — the failure this prevents is a run that stops at an
unseeded Phase 3, looks complete, and quietly omits the step that does the
work.

| item | required |
|---|---|
| structural step | ran, or skipped with the reason |
| filter-tells | ran; findings triaged into real vs false positives |
| Phase 3 seed | ran, with the model family and anchor tags named |
| Phase 3 iteration | every pass scored; stopped at an upturn, not a count |
| floor selection | the publish candidate is the floor pass |
| cold review | run on the floor pass; survival rate stated |
| inject-vernacular | ran, or skipped with the reason |
| canonical blocks | registry found, or passed explicitly |
| locks and markers | verified byte-identical after every stage |

### Phase 4: Consolidated report

Print a single report with five categories. Each metric shows four columns:
baseline, after step 1, after-tells, after-voice, and the total delta
(after-voice minus baseline).

In venue mode, head the report with the venue name and add a `target`
column to categories 2–5 wherever the profile's `targets` block carries the
metric — the question the report answers becomes "did the pipeline land on
the venue's measured register", not only "did the numbers move". Run each
gate from the profile's `gates` list in order and state pass/fail per gate;
omit the Pangram category entirely when that gate is absent.

**1. AI/Human detection (Pangram)**

| stage | human % | mean score | verdict |
|---|---|---|---|
| baseline | — | — | — |
| after step 1 (match-outline or tighten-style) | — | — | — |
| after filter-tells | — | — | — |
| after match-voice | — | — | — |

**2. Readability**

| metric | baseline | after step 1 | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Flesch Reading Ease | — | — | — | — | — |
| Flesch-Kincaid Grade | — | — | — | — | — |
| Gunning Fog | — | — | — | — | — |
| SMOG Index | — | — | — | — | — |

**3. Lexical diversity**

| metric | baseline | after step 1 | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Type-Token Ratio | — | — | — | — | — |
| Corrected TTR | — | — | — | — | — |
| Hapax Ratio | — | — | — | — | — |
| Yule's K | — | — | — | — | — |

**4. Syntactic and structural**

| metric | baseline | after step 1 | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Sentence length mean | — | — | — | — | — |
| Sentence length stdev | — | — | — | — | — |
| Sentence length CV | — | — | — | — | — |
| Mean clause length | — | — | — | — | — |
| Passive / 100 sentences | — | — | — | — | — |
| Paragraph cohesion | — | — | — | — | — |

**5. Stylometrics**

| metric | baseline | after step 1 | after-tells | after-voice | delta |
|---|---|---|---|---|---|
| Function word ratio | — | — | — | — | — |
| Hedges / 1000 words | — | — | — | — | — |
| Commas / 1000 words | — | — | — | — | — |
| Semicolons / 1000 words | — | — | — | — | — |
| Em dashes / 1000 words | — | — | — | — | — |
| Colons / 1000 words | — | — | — | — | — |
| Top sentence openers | — | — | — | — | — |

**6. Filter-tells results**

| metric | before cleanup | after cleanup |
|---|---|---|
| Antithesis pairs | — | — |
| Banned words | — | — |
| Structural verdict | — | — |

**7. Match-voice gate stats**

| metric | value |
|---|---|
| Accepted (mechanical) | — |
| Kept original | — |
| Skipped (short) | — |
| Mean distance | — |

## File naming convention

| file | step |
|---|---|
| `<stem>.md` | original article |
| `<stem>-rewritten.md` | after match-outline (when chosen) |
| `<stem>-tightened.md` | after tighten-style (when chosen; pass `--out`, the tool's own default is `<stem>.tightmd`) |
| `<step1-output>.md` | same file, after semantic edits applied in place |
| `<step1-output>.vr-gptoss-noanchor.md` | final output after match-voice |
| `<step1-output>.vr-gptoss-noanchor.generation.yaml` | provenance record |

## When it breaks

- **Every paragraph kept-original with reason `?`:** suspect a gate crash
  before blaming the rewrite model. GH-318 had verify.py crashing on the
  `--no-anchors` anchors JSON, and drive.py recorded every crash as an
  ordinary rejection — runs shipped an untouched copy of the input while
  reporting success (Pangram before == after is the tell). Check the
  provenance YAML: `accepted: 0` with unchanged scores means the gate never
  ran, not that the rewrites failed.
- **match-voice gate rejects everything (distance 0.0):** the structural
  step (when match-outline was chosen) did not change the prose enough. Try
  a different model or blueprint for match-outline, or apply more aggressive
  semantic edits in Phase 2.
- **tighten-style gate rejects everything:** the prose is already at or
  below the author's density floor — there is nothing to tighten. When the
  structure itself needs to change, match-outline is the right step 1, not
  tighten-style.
- **Pangram score does not improve:** the semantic cleanup missed rhetorical
  patterns. Re-run filter-tells Step 3 (the full semantic analysis) and look
  for surviving antithesis pairs, tricolon patterns, or CoT leakage.
- **Meaning drift:** three rewrites compound. The match-outline rewrite is
  the largest source of drift. Compare the final output against the original
  (not the intermediate) to catch cumulative losses.
- **Filler regression:** gpt-oss without anchors tends toward formal prose,
  but can introduce filler. Check the stylometrics section of the report.

## Calibration data

Tested on `2026-10-29-how-to-break-an-ais-heresy.md` (2,357 words) with
hardcoded Evans how-to blueprint and anchor-tags.

**Gate-bug caveat (GH-318, fixed 2026-07-29).** Through 2026-07-28, verify.py
crashed on the list-format anchors JSON that `--no-anchors` writes, and
drive.py recorded every crash as kept-original. Any `--no-anchors` row from
that window may describe an untouched copy of its input, not a rewrite: the
on-disk provenance for the 2026-07-28 no-anchors runs shows `accepted: 0`
with Pangram before == after. Rows marked *unverified* below predate the fix
and could not be reproduced from provenance; the *verified* row is a
post-fix run with all 35 paragraphs accepted (distance 0.533).

| variant | pipeline | Pangram human % | mean score | status |
|---|---|---|---|---|
| original | none | 0% | 0.993 | verified |
| match-outline only | Kimi rewrite | 0% | 0.993 | verified |
| semantic cleanup only | filter-tells on Kimi rewrite | 0% | 0.993 | verified |
| match-voice venue-voice | Kimi + semantic + Tanenbaum/Martin anchors | 0% | 0.765 | pre-fix, anchored |
| match-voice author 2.5x | Kimi + semantic + Djukic anchors | 26.6% | 0.454 | pre-fix, anchored |
| match-voice Evans how-to | Kimi + semantic + Evans anchors | 0% | 0.955 | pre-fix, anchored |
| match-voice no-anchors | Kimi + semantic + gpt-oss no anchors | 100% | 0.245 | **unverified** (broken-gate window) |
| **match-voice no-anchors (2026-07-29)** | **Kimi + semantic + gpt-oss no anchors** | **0% human, 76.2% AI-assisted, 23.8% AI** | **0.576** | **verified, working gate** |
| no match-outline | semantic + gpt-oss no anchors on original | 0% | 0.993 (gate rejected) | **unverified** — matches the GH-318 crash signature |
| no semantic cleanup | gpt-oss no anchors on original | 0% | 0.993 (gate rejected) | **unverified** — matches the GH-318 crash signature |

The ablation claim (each step necessary) rests on the two unverified rows and
needs re-measurement with the working gate before it can be stated as fact.

All calibration above was measured with match-outline as the structural
step. tighten-style calibration is pending.

**Iteration calibration (2026-07-29, working gate, stay-on-track article,
published as pass02).** Seed: Kimi match-outline + filter-tells + gemma4
match-voice with Krugman anchors (0.992 — anchored passes still do not move
Pangram, but change the fingerprint the iterator erases). Then gpt-oss
no-anchors, iterated; full per-pass data in
idea-factory:substack/2026/Q4/experiments/2026-07-29-gptoss-iter/stats.csv.

| pass | mean window | human % |
|---|---|---|
| seed | 0.992 | 0 |
| 1 | 0.579 | 43 |
| **2** | **0.432** | **55** |
| 4 | 0.418 (floor) | 34 |
| 10 | 0.700 | 0 |

**Well-edited-input regime (2026-08-22, strategy-theatre).** The table
above was measured descending from a fresh AI draft at 0.992, where every
pass had something to strip. Against prose already through two critic
panels and a socratic pass, the same recipe behaves differently and still
works:

| stage | score | note |
|---|---|---|
| article | 0.375 ai / 0.370 human | three rounds of human editing |
| anchored gemma seed | 0.395 / 0.435 | **19 of 125 paragraphs changed** — the gate rejected most rewrites because the text is tight |
| pass 1 (gpt-oss) | 0.251 / 0.615 | floor |
| pass 2 | 0.344 / 0.597 | upturn, stopped |
| floor, cold-reviewed (23 of 65 kept) | 0.370 / 0.550 | the publishable number |

Two lessons. The seed does not need to rewrite wholesale to work — 19
paragraphs of foreign fingerprint were enough. And survival at cold review
falls as input quality rises (21% single-shot, 51% harness on mid-edit
text, 33–35% on well-edited text): the pipeline's value is front-loaded
onto drafts, and on edited prose the gated gain is real but small.

Same-family iteration is a no-op: kimi match-voice on kimi-derived prose
moved distance 0.05, Pangram 0.993 -> 0.993. The iterator must be a
different family from whatever produced the input.
