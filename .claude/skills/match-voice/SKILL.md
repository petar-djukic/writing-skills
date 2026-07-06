---
name: match-voice
description: >-
  Learn the writing voice of the papers in a research corpus and compare a
  draft against it. Uses the markdown papers fetched by update-references
  (papers/*.md, keyed by references.yaml). Computes quantitative style
  metrics (sentence/paragraph distributions, word/phrase/idiom frequencies,
  per-section profiles) and a qualitative voice profile (how intros open,
  methodology and results conventions, terminology). Produces a comparison
  report for the draft. Triggers: match voice, learn the voice, compare my
  writing, voice profile, style profile, does my draft sound like the field,
  analyze methodology section, results conventions, writing style comparison.
---

# Match voice (corpus style analysis)

This skill answers "does my draft read like the field I'm writing for?" It
learns the voice of the corpus papers — vocabulary, sentence and paragraph
structure, section structure, common themes, jargon, methodology and results
conventions — and compares a draft against that profile with evidence.

It complements `update-references` (which builds the corpus) and `de-ai`
(which detects generic AI-writing patterns). `match-voice` defines what this
field's human writing looks like; do not duplicate de-ai's detectors.

## Where things live

- **Corpus:** `<db-dir>/papers/*.md` — the markdown conversions fetched by
  `update-references`, selected via entries in `references.yaml`. Default
  selection is entries with `status: summarized` (papers the user actually
  engaged with); pass `--all` to `style.py corpus` to include every entry
  with an `md_path`.
- **Quantitative profile:** `<db-dir>/voice-profile.json`, written by
  `style.py corpus`. Regenerate only when the corpus changes (the profile
  records corpus file paths and mtimes — compare before recomputing).
- **Qualitative profile:** `<db-dir>/voice-profile.md`, written by the model
  following `references/voice-analysis-instructions.md` Part 1. Same
  regeneration rule.
- **Comparison reports:** `<db-dir>/voice-reports/<draft-stem>-voice.md`,
  following `references/comparison-report-template.md`.

## The workflow (interactive)

### 1. Locate the corpus

Find `references.yaml` at or above the working directory. If it does not
exist, or no entries have `status: summarized` with an existing `md_path`
file, stop and tell the user to run `update-references` first (and `repair`
if PDFs exist without markdown).

### 2. Quantitative profiles

```bash
python3 <skill>/scripts/style.py --db <db-path> corpus
```

This writes `voice-profile.json`: aggregated metrics (whole-paper and
per-section), ranked word/phrase/idiom frequency tables, and jargon (terms
frequent across multiple corpus papers). Skip if the existing profile's
recorded corpus files and mtimes are unchanged.

Useful inspection commands:

```bash
python3 <skill>/scripts/style.py profile <paper.md>     # one paper, full JSON
python3 <skill>/scripts/style.py freq <paper.md>        # frequency tables only
```

### 3. Qualitative profile

Read the corpus papers (their `md_path` files) and write `voice-profile.md`
following **Part 1** of `references/voice-analysis-instructions.md`. Every
claim carries a quote. The Methodology Conventions and Results Conventions
sections carry particular weight — they are what a draft's corresponding
sections get checked against.

Skip if the profile exists and the corpus is unchanged.

### 4. Compare the draft

```bash
python3 <skill>/scripts/style.py --db <db-path> compare <draft.md>
```

This emits the quantitative diff: metric deltas (whole-paper and
per-section, methodology and results included), over/underused terms
relative to corpus rates, idiom usage differences, and missing sections.

Then write the comparison report following **Part 2** of
`voice-analysis-instructions.md` and the structure of
`comparison-report-template.md`. Interpret the numbers, quote draft and
corpus side by side, check methodology/results conventions one by one, and
give directions rather than rewritten text.

### 5. Report back

Summarize: the verdict (close match / partial / divergent), the two or
three highest-impact changes, and the report path.

## Headless mode

`match_voice.py` runs steps 2-4 end-to-end without an interactive session —
one Anthropic API call for the qualitative layer:

```bash
python3 <skill>/scripts/match_voice.py <draft.md> --db <db-path>
```

It refreshes the quantitative profile, excerpts corpus papers (intro,
methodology, results, conclusion — capped at ~100K tokens), assembles the
prompt from this skill's own `references/` files (single source of truth),
and calls `claude-opus-4-8` with adaptive thinking and streaming. The corpus
block is prompt-cached, so repeated comparisons against the same corpus hit
the cache. The report lands in `<db-dir>/voice-reports/` and usage stats
print to stdout.

Requires `ANTHROPIC_API_KEY` (or an active `ant auth login` profile) and
`pip install anthropic`. Suitable for CI, cron, or a mage target.

## Dependencies

PyYAML is required for both scripts. `style.py` is otherwise pure stdlib.
`match_voice.py` additionally requires the `anthropic` package. The corpus
must have been fetched by `update-references` with markdown conversion
(issue #37) — plain-text legacy corpora work but lose section detection
quality.
