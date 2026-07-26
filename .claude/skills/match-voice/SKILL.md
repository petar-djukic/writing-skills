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
prints the exemplar mix before it starts.

There is deliberately **no automatic quality gate on the Pangram number**. One
run is not a threshold, and inventing one from it would be the overfitting
GH-188 warned about.

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

## Steering the anchors

The driver prints the exemplar mix **before** rewriting anything:

```
anchors: 52 exemplars from .../writing-voice
         {'author-voice': 24, 'venue-voice': 28}
```

Read that line. An all-`author-voice` mix behind a draft that wants punch is
the GH-215 failure, and it costs a whole rewrite to discover afterwards.

| you want | flags |
|---|---|
| default — nearest passages, author-voice weighted | none |
| diction-safe only (exclude AI-era samples) | `--stratum pre-ai` |
| **punch: the pre-AI peer essays** | `--role venue-voice --stratum pre-ai` |
| **register that topic will not find** | `--anchor-tags economics` |
| shape references, deliberately | `--anchor-tags structure-only` |
| a specific corpus | `--voice-dir <path>` |

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

## Configuration

| Setting | Flag | Default |
|---|---|---|
| Endpoint | `--endpoint` / `OLLAMA_ENDPOINT` | `http://localhost:11434` |
| Model | `--model` / `MATCH_VOICE_MODEL` | `gemma4:12b` |
| Temperature | `--temperature` | 0.7 |
| Timeout (s) | `--timeout` / `MATCH_VOICE_TIMEOUT` | 300 (cold loads are slow) |
| Anchors per paragraph | `-k` | 3 |
| Max copied run (words) | `--max-shared-run` | 8 |
| External check | `--pangram` | off (the flag is the consent) |

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
