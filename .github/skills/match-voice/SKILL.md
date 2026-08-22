---
name: match-voice
description: >-
  Rewrite paragraphs of a draft in the author's voice using a second model
  family served by Ollama, with a verification gate before any text is spliced
  back. Retrieves voice anchors from the repository's writing-voice/ exemplars,
  sends paragraph plus anchors to a local (or cloud) Ollama model, then gates
  the result on citation/number preservation, meaning entailment, anchor
  similarity, and register. Triggers: voice rewrite, rewrite in my voice,
  ollama rewrite, rewrite paragraphs, local model rewrite, sound like my
  earlier papers, rewrite against writing-voice.
---

*Renamed from `voice-rewrite` (2026-07). **The name `match-voice` previously
belonged to the stylometry skill, now `match-structure`** — if you invoked
`match-voice` before this date expecting measurement, you want
`match-structure`. This skill rewrites.*

# match-voice (Ollama rewrites, Claude judges)

## The objective, and its constraint

**Minimize the Pangram AI score — subject to the gate holding and the anchors
being appropriate to the draft.** The constraint is not decoration. Optimizing
the score alone has a known optimum, and it is not prose you want.

Recorded run (GH-219): a hand-written, twice-hand-edited published article went
from **AI 77.8% to AI 0.0%**, Mixed to Human, all 25 paragraphs "improved". By
the score alone, a total success. What it produced:

| before | after |
|---|---|
| The grouping does two jobs. | Grouping serves two primary purposes. First, … |
| Let the orchestrator run git, not the agents. | Git operations are executed by the orchestrator rather than the agents. |
| One structural detail deserves attention before it becomes a bug. | A specific structural detail must be noted. |

The local register metrics moved the other way in the same run:
`passive_enabling_per_500w` 0.0 → 0.5, `salad_rate_per_100` 5.5 → 8.3,
`opening_diversity` 0.72 → 0.67. Academic passive-voice prose scores zero.

Two facts sit behind this. Pangram rated the author's own hand-written prose
77.8% AI, and `filter-tells` catches only 24% of real AI documents (GH-192).
**Neither detector is a reliable proxy for "reads as human" on its own.** The
score is evidence, and a score that falls while the register metrics worsen is
evidence of the wrong thing.

The cause of that run was anchors, not the objective: retrieval was showing the
model IEEE papers for a punchy blog post (GH-216). Fix the anchors and the
objective is reachable without the failure mode — which is why the driver now
reports the anchors it selected, not only the pool it selected them from,
before it starts.

There is deliberately **no automatic quality gate on the Pangram number**. One
run is not a threshold, and inventing one from it would be the overfitting
GH-188 warned about.

A later run measured the same divergence while the score moved a long way
(GH-233). An article fell 58 points, 81.1% to 23.3%, and in the same run
`sentence_length_std` fell 8.9 → 8.3, `dash_density_per_500w` rose 1.4 → 2.0,
`antithesis_pairs` rose 1 → 3, bold lead-ins fell 11 → 8, and ` just ` went
1 → 10. A 58-point improvement is the most persuasive number this pipeline has
produced, and the prose underneath it got worse on five measures at once. Read
the register report beside the score, never instead of it.

The rewriting model is deliberately **not** Claude. filter-tells detects and steers
within the Claude loop (GH-156); this skill hands the rewrite itself to a
different model family so the prose decorrelates from Claude's own lexical
fingerprints, instead of Claude grading its own homework. Claude keeps the
job it is good at: judging whether the result is faithful.

That division is the point. **Verification is not optional** — an 8B model
rewriting technical prose will drop a citation, round a number, or quietly
strengthen a claim. Nothing is spliced into a draft until the gate passes.

## Prerequisites

- A `writing-voice/` directory of exemplars (contract: the repository's
  writing-voice rule; roles `author-voice` / `venue-voice`). Without it this
  skill has no target and should not run — use plain filter-tells instead.
- A reachable Ollama endpoint with the model pulled, at
  `http://localhost:11434` by default.
- For the `--pangram` measurement only, a Pangram API key. It resolves through
  `<agent-dir>/scripts/credentials.py` in order: an explicit `--api-key`, then
  `PANGRAM_API_KEY`, then the nearest `.secrets/keys.json` found by walking up
  from the working directory (contract: the repository's secrets rule). So
  `env | grep -i pangram` coming back empty settles nothing — the file is where
  the key usually lives, and checking the environment first is what makes a
  configured key look missing. Ask the loader instead:
  `python3 <agent-dir>/scripts/credentials.py` reports which services are
  configured, printing names and never values.

**Model choice.** Default `gemma4:12b` — the best local model in the GH-163
bake-off that runs anywhere. On a 32 GB Apple Silicon machine, `gemma4:31b-mlx`
reaches the top tier without sending drafts off the machine; `gemma4:31b-cloud`
when the memory is not there. **Prefer local when the machine can hold the
model**: this operates on unpublished prose, and the cloud rows buy quality a
big-memory Mac already has. Sizes, the full ranking, and the reasoning are in
[model-choice.md](./references/model-choice.md).

Check the endpoint before starting:

```bash
python3 <skill>/scripts/rewrite.py --check --text /dev/null
```

If this fails, **report it and stop**. The skill never falls back to a Claude
rewrite: that would defeat the decorrelation it exists for.

## When not to run it

Two kinds of draft do not benefit, and each costs a whole run to find out.

**Prose already cleaned by hand.** Measured on two articles that had been
through the full filter-tells battery and an editing pass before the run: the
pipeline put back what the cleanup had taken out. ` just ` went 1 → 10 and
1 → 15, ` actually ` 1 → 7 and 0 → 15, bold lead-ins fell 11 → 8, and
`antithesis_pairs` rose 1 → 3 (GH-233). A second model re-emitting finished
prose finds little to repair and adjusts register anyway. The wins this skill
can show were measured on drafts that had not been hand-tightened, and they do
not transfer to prose that has.

**An article about AI writing.** One document did not shift by a point — 8 of 8
segments flagged before and after — through the same run that moved a sibling
article 58 points. Its vocabulary *is* the flagged lexicon: it quotes
"leverage", "robust", "seamless" and "delve", explains burstiness, and carries a
table of AI artifacts. No rewrite reaches that, because the subject matter is
what the detector measures. Expect no movement and spend the scans elsewhere.

## Steering the anchors

The driver reports both the pool and the anchors retrieval actually chose,
**before** rewriting anything:

```
anchors: 52 exemplars available from .../writing-voice
         pool {'author-voice': 24, 'venue-voice': 28}
         selected 15 anchors over 5 of 27 paragraphs
         roles {'author-voice': 11, 'venue-voice': 4}
         top sources Djukic-2009-rrm.md x4, Djukic-2005-lifetime.md x3, ...
```

Read the `selected` block, not the `pool` line. They answer different questions
and only the second one predicts the output: the pool says what retrieval *may*
reach, the selection says what it *chose*. A pool of 22 author-voice against 91
venue-voice looks healthy and still hands a how-to paragraph two IEEE papers out
of three anchors — the GH-215 failure on a corpus assembled to prevent it, which
is why the pool line alone could not catch it (GH-233).

The pre-run block samples the first few paragraphs and says so. For the real
selection over every paragraph, with no model called and no draft written:

```bash
python3 <skill>/scripts/drive.py --article draft.md --dry-run
```

Judge on sources as well as roles. `{'venue-voice': 2, 'author-voice': 1}` reads
balanced while every anchor is a paper.

A flag that filters nothing is reported as inert rather than left to look like a
control — `--stratum pre-ai` on a corpus whose diction-eligible samples are all
pre-AI is a no-op, and following it as the register control produces the
register it was meant to avoid (GH-234, idea-factory#355).

| you want | flags |
|---|---|
| default — nearest passages, author-voice weighted | none |
| diction-safe only (exclude AI-era samples) | `--stratum pre-ai` — inert, and reported as such, when the corpus holds no AI-era diction samples |
| **punch: the pre-AI peer essays** | `--role venue-voice --anchor-tags clipped` |
| **one specific author's voice** | `--author Yegge` — hard pin, not a weight; empty pool if no exemplars carry that author |
| see the real selection before spending tokens | `--dry-run` |
| **register that topic will not find** | `--anchor-tags economics` |
| shape references, deliberately | `--anchor-tags structure-only` |
| a specific corpus | `--voice-dir <path>` |
| no voice steering at all | `--no-anchors` — skips retrieval entirely; contradicts `--role`/`--anchor-tags`/`--stratum` |

The last combination is what a repository README means by "anchor on the Yegge
and Beck samples". `--stratum pre-ai` alone is often not enough: it removes the
AI-era samples, but if the remaining peer essays are not *topically* near the
draft, the academic papers still win on similarity. Forcing the role is how you
say "punch matters more than topic here".

**Tags are the axis similarity cannot reach.** Retrieval matches topic, and the
register that fits an article is often the one least topically similar — on a
113-exemplar corpus, an economics paragraph ranked the Krugman samples no
better than 25th of 2,420. Tags select the pool and similarity ranks within it,
so `--anchor-tags economics` returns Krugman at a *third* the similarity score
of the software essays it displaced. Measured (GH-229): that swap took a
published article from an external score of 100% to 17.9% while holding the
passive rate at the author's own level.

`structure-only` samples are held out of diction anchoring unless you ask for
them by name — they are shape references, and their prose is often the register
you are escaping.

Anchors used per paragraph, with scores, land in `results.json` — so a bad mix
is diagnosable after the fact without re-running retrieval by hand.

## Driver (whole-article orchestration)

`scripts/drive.py` runs the per-paragraph pipeline over a full article and
assembles the gate-passing rewrites into a sibling `<article>.vr-draft.md`:

```bash
python3 <skill>/scripts/drive.py --article <path.md> --model gemma4:31b-cloud
python3 <skill>/scripts/drive.py --article <path.md> --coverage-only   # no model calls
python3 <skill>/scripts/drive.py --article <path.md> --pangram         # + before/after, uploads
```

- **Coverage audit is mandatory output.** Every body line is classified
  (prose / heading / figure / table / code / reference / blockquote / list /
  rule / blank); any unclassifiable line is reported as a WARNING and
  `--coverage-only` exits nonzero. Added after a real question — "did the
  driver skip the first paragraphs?" — that an ad-hoc driver could not answer.
  Run `--coverage-only` first when in doubt; the paragraph map is the answer.
- Retries are failure-classified automatically (copy → anti-copy note,
  number/citation loss → preserve-numbers note, register → banned-vocab note).
- The driver applies the MECHANICAL gate only. The emitted draft is a set of
  candidates: run the meaning-entailment review (references/prompts.md) on each
  accepted paragraph, and filter-tells over the assembled file, before treating the
  draft as accepted.
- Kept-original paragraphs are listed with their failure category. A kept
  original is a correct outcome, and the keeps double as an internal control
  in redistribution experiments (the 2026-07 Pangram run: flagged residue
  mapped to the kept paragraphs).
- `--pangram` measures whether the rewrite worked, and is the only way to get
  the comparison — see [Did it work?](#did-it-work-the---pangram-measurement)
  below for what it costs and what it discloses.

## The pipeline (per paragraph)

Paragraph is the unit of work. The skill never restructures across
paragraphs.

**1. Retrieve anchors.**

```bash
python3 <skill>/scripts/retrieve.py --text <paragraph-file> --for <draft> -k 3 --json > anchors.json
python3 <skill>/scripts/retrieve.py --text <paragraph-file> --for <draft> -k 3 > anchors.txt
```

Top-k topically nearest exemplar passages, `author-voice` preferred.
**Retrieval is lexical (tf-idf), so anchors match the author's vocabulary, not
necessarily the paragraph's subject** — a meta-paragraph about fragmented
literatures may pull scheduling papers. That is fine and often correct: the
anchors exist to carry register, not content. Do not treat an off-topic anchor
as a retrieval failure.
Retrieval is the filter-tells `voice_anchors` implementation imported from the
sibling skill — built once, imported twice, so the two skills cannot drift.

**2. Rewrite.**

```bash
python3 <skill>/scripts/rewrite.py --text <paragraph-file> --anchors anchors.txt \
  [--model gemma4:12b] [--endpoint http://localhost:11434] [--temperature 0.7] [--timeout 300]
```

**3. Gate — all four checks, fail closed.**

```bash
python3 <skill>/scripts/verify.py --original <paragraph-file> --rewrite <candidate> \
  --anchors-json anchors.json
```

| Check | Who | Fails on |
|---|---|---|
| Citations, numbers, terms | `verify.py` | a key or figure lost, altered, or invented |
| Citation syntax family | `verify.py` | `[@key]` silently rewritten as `\citep{key}` — the key survives but the build breaks |
| Inline markup | `verify.py` | a `**bold**`, `*italic*`, or `` `code` `` span dropped, or a bold lead-in returned as plain prose — same class as citation syntax, and the reason a section of lead-ins lost three of six |
| Em-dashes | `verify.py` | a dash the original did not have — manufactured punch, measured at 7 → 10 and 7 → 15 across two articles against a house limit of 2.0 per 500 words |
| Anchor similarity | `verify.py` (match-structure shingles) | a long verbatim run copied from an exemplar |
| Meaning entailment | **Claude**, per references/prompts.md | any claim weakened, added, or re-scoped |
| Register | filter-tells lexical scan on the candidate | banned words — one machine register traded for another |

`verify.py` exits nonzero on violation so the loop can gate on it directly.
It is the *mechanical* half only; a clean exit is necessary, not sufficient —
run the entailment judgment and the filter-tells scan before accepting.

**3b. Two-model mode (optional).** Run the same paragraph and anchors through
both cloud models, gate both candidates, and have the Claude judge pick the
better rewrite (or keep the original if neither is faithful). The pairing that
paid off in evaluation is `gemma4:31b-cloud` + `kimi-k2.6:cloud`: when they
disagree about whether a sentence needs changing at all, the more conservative
answer is usually right.

**4. Splice or keep.** On a clean gate, accept. Otherwise retry with a
failure-specific note (`--retry-note`, table in references/prompts.md) up to
N times (default 2), then **keep the original paragraph and record why**. A
kept original is a correct outcome; expect a meaningful reject rate from an 8B
model and do not assume success.

**5. Report.** A per-paragraph table: accepted / retried / kept-original, with
gate failures by category. Rewrites are proposed as a diff for review by
default; applying them directly is opt-in.

## Protected terms and canonical blocks

Two guards the per-paragraph gate cannot express on its own, because both
are properties of the article (GH-77).

**Protected terms** are the article's referent chain: words and phrases that
recur in three or more paragraphs, plus any sentence repeated verbatim across
paragraphs (a refrain). The largest failure class in the GH-189 measured run
was a term-of-art swap — exposure → justification, decision plane →
decision, detector → tool — that passed every per-paragraph check because
the chain it broke ran across paragraphs. On the first run the driver derives
the list to `<stem>.protected-terms.txt` beside the article and says so; on
every later run it reads that file and never overwrites it, so it is yours to
edit — one term per line, `#` comments. The rewrite model receives the terms
the current paragraph carries as a keep-verbatim rule, `verify.py` rejects a
candidate that loses one (`protected-term`, fatal), and the retry note names
the lost terms. `--protected-terms FILE` points at another list;
`--no-protected-terms` turns the guard off. The manifest records the path,
the count, and whether this run derived it.

```bash
python3 <skill>/scripts/protected_terms.py draft.md          # show what would be derived
python3 <skill>/scripts/protected_terms.py draft.md --write  # write it if absent
```

**Canonical blocks** are pasted, not written — an AI-disclosure line, a
subscribe line, a "Start Here" pointer — and are never sent to the model.
They are not span-locked because they are inserted at paste time, so the
registry lives beside the corpus at `writing-voice/canonical-blocks.txt`
(found by walking up from the article) or is passed with
`--canonical-blocks FILE`. One pattern per line: a plain case-insensitive
substring, or `re:<regex>`. Matching paragraphs get status `canonical`,
stay verbatim in the draft, and are counted in the manifest.

## Configuration

| Setting | Flag | Default |
|---|---|---|
| Endpoint | `--endpoint` / `OLLAMA_ENDPOINT` | `http://localhost:11434` |
| Model | `--model` / `MATCH_VOICE_MODEL` | `gemma4:12b` |
| Temperature | `--temperature` | 0.7 |
| Timeout (s) | `--timeout` / `MATCH_VOICE_TIMEOUT` | 300 (cold loads are slow) |
| Anchors per paragraph | `-k` | 3 |
| Max copied run (words) | `--max-shared-run` | 8 |
| Standing style directive | `--style-note` | off |
| Paragraph selection | `--paragraphs` | all rewritable paragraphs |
| Protected terms | `--protected-terms` / `--no-protected-terms` | `<stem>.protected-terms.txt`, derived on first run |
| Canonical blocks | `--canonical-blocks` | `writing-voice/canonical-blocks.txt` by walk-up |
| External check | `--pangram` | off (the flag is the consent) |

`--style-note "active voice, plain diction"` sends a standing directive to
the rewrite model on every attempt, first included; retries append their
failure-classified note after it. Use it when a run's register drifts in a
known direction — the measured case is gpt-oss `--no-anchors` doubling the
passive rate — and you want to push back without anchors. Recorded in the
provenance YAML as `style_note`.

`--paragraphs "3,7,12-15"` restricts the rewrite to the listed 1-based
paragraph indices; everything else passes through untouched (status
`unselected`). This is the second-pass workflow: a `--pangram` run ends its
still-flagged worklist with a ready-to-paste `next pass: --paragraphs "..."`
line, so the paragraphs that stayed flagged can be re-rolled without spending
model calls on — or risking regressions in — the ones that already cleared.
An invalid selection (malformed, out of range) exits 2 before any scan or
model call. The selection is recorded in the provenance YAML.

**Readability guard.** After the register-markers comparison (the `--pangram`
path), the run prints one WARN line per metric whose relative increase
crosses its ceiling — passive +50%, nominalization +25%, filler +50% on the
per-1,000-word rates — or `readability guard: clean`. Advisory only: the
gate governs fidelity and nothing hard-fails on style drift, but a doubling
passive rate should not look like a 0.1 uptick. Triggered warnings are
recorded in the provenance YAML under `guard:`.

## Did it work? (the --pangram measurement)

The gate proves a candidate preserved citations, numbers, and meaning. It
cannot tell you whether the prose stopped reading as machine-written, and
filter-tells cannot settle that either — its detectors are the denylist the
rewrite was steering around, so their silence is close to tautological. An
external detector answers from outside, and the driver runs it:

```bash
python3 <skill>/scripts/drive.py --article draft.md --pangram
```

It scans the article before touching a paragraph, scans the assembled draft at
the end, and reports `fraction_ai` before → after with the paragraphs that
moved. That ordering is why the measurement lives in the driver rather than in
a procedure to follow afterwards: **the baseline cannot be reconstructed once
the paragraphs are replaced**, so a run started without the flag has
nothing to compare against later. Decide before the run, not after reading the
draft.

**Passing the flag is the consent**, and it is asked for per document. The
scan uploads the article and the draft to a third party that retains both —
the opposite of the local-first reason this skill exists — so the driver never
uploads on its own, not even with a key sitting in the environment. See the
upload rule in the `writing-voice/` directory rule before answering. A full
comparison costs two scans. How much of an allowance that spends depends on the
account, and nothing here enforces a ceiling: run `pangram.py --check` first,
which confirms the key and the endpoint and spends nothing, and read the
account's own answer from the API — 402 for exhausted credits, 429 for too many
requests. Do not plan a session around a remembered daily number.

**It measures prose only.** Both scans submit the payload the shared extractor
builds, with front matter, tables, and code fences dropped — the text a rewrite
can change. Scanning the whole file by hand includes that machinery
and returns a different number, and the difference is not the rewrite. Two
readings of one document are comparable only when both cover the same text, so
the run manifest records `scope: prose-only` beside the pair.

Without the flag, or without a key, the driver runs unchanged and says the
check was skipped. That is the normal state, not a degraded one; if the
baseline scan fails the second one is not spent either.

The still-flagged paragraph list is the useful output: the worklist for
another pass, pointing at the passages the rewrite did not fix. Read it as
evidence and not a verdict — filter-tells's Verdict Validity Rules apply here
too, and a favourable number certifies nothing on its own.

The two scripts underneath, `<agent-dir>/scripts/pangram.py` and
`pangram_report.py`, sit at the shared scripts root. filter-tells invokes the
same pair for a point-in-time reading; neither skill owns them.

## Relationship to the other prose skills

- **filter-tells** detects the tells and, with `writing-voice/`, steers its own
  rewrites toward the same anchors. Use filter-tells when Claude should do the
  rewriting; use this skill when you want a different model's prose.
- **match-structure** owns voice profiling and the similarity guard this skill
  reuses for the copy check.
- Run filter-tells over the finished draft afterward regardless — a local model's
  output is not exempt from the tells.

## Dependencies

The pixi environment (PyYAML) plus a reachable Ollama. Retrieval and the
similarity guard import their implementations from the sibling filter-tells and
match-structure skills, which every agent surface carries.
