---
name: match-voice
description: >-
  Learn the writing voice of the papers in a research corpus and compare a
  draft against it. Uses the markdown papers fetched by update-references
  (papers/*.md, keyed by references.yaml). Computes quantitative style
  metrics (sentence/paragraph distributions, word/phrase/idiom frequencies,
  per-section profiles) and a qualitative voice profile (how intros open,
  methodology and results conventions, terminology). Produces a comparison
  report for the draft, extracts voice persona blueprints from exemplar
  papers, and can rewrite a draft to match a voice (opt-in, section by
  section, with a plagiarism similarity guard). Triggers: match voice, learn
  the voice, compare my writing, voice profile, style profile, does my draft
  sound like the field, analyze methodology section, results conventions,
  writing style comparison, mimic this paper, rewrite in the style of, apply
  the voice, voice persona, exemplar, plagiarism check, similarity check.
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
- **Exemplar blueprints:** `<db-dir>/voice-blueprint-<slug>.md`, extracted
  from chosen exemplar papers following `voice-analysis-instructions.md`
  Part 3 (consensus vs idiosyncrasy).
- **Rewritten drafts:** `<draft-stem>-rewritten.md` next to the draft. The
  draft itself is never modified.

## Running the scripts

The scripts run in the pixi-managed environment that ships beside the skill
(`pixi.toml` / `pixi.lock` at the agent-directory root). The agent provisions
it on repo open via `<agent-dir>/scripts/ensure-env.sh`; then the commands
below use `$RUN` for the wrapper:

```bash
RUN="pixi run --manifest-path <skill>/../../pixi.toml python"
```

This supplies PyYAML and the `anthropic` package, so no `pip install` is
needed. `match_voice.py` still needs `ANTHROPIC_API_KEY` (or an active
`ant auth login`) at run time — pixi manages packages, not secrets.

## The workflow (interactive)

### 1. Locate the corpus

Find `references.yaml` at or above the working directory. If it does not
exist, or no entries have `status: summarized` with an existing `md_path`
file, stop and tell the user to run `update-references` first (and `repair`
if PDFs exist without markdown).

### 2. Quantitative profiles

```bash
$RUN <skill>/scripts/style.py --db <db-path> corpus
```

This writes `voice-profile.json`: aggregated metrics (whole-paper and
per-section), ranked word/phrase/idiom frequency tables, and jargon (terms
frequent across multiple corpus papers). Skip if the existing profile's
recorded corpus files and mtimes are unchanged.

Useful inspection commands:

```bash
$RUN <skill>/scripts/style.py profile <paper.md>     # one paper, full JSON
$RUN <skill>/scripts/style.py freq <paper.md>        # frequency tables only
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
$RUN <skill>/scripts/style.py --db <db-path> compare <draft.md>
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

## Exemplar blueprints (mimic a specific paper or venue)

When the user wants to mimic specific papers rather than the corpus average
("mimic these two ICML papers"), extract a voice persona blueprint following
**Part 3** of `voice-analysis-instructions.md`: one mini-blueprint per
exemplar (sentence mechanics, lexicon and tone, signposting and transitions,
formatting quirks — every claim quoted, never summarizing content), then a
synthesis separating **Consensus** (shared across exemplars — venue
convention) from **Idiosyncrasy** (one author's habit, flagged per source).
Save as `voice-blueprint-<slug>.md`. A single exemplar skips synthesis and
is marked entirely single-source.

## Rewrite mode (opt-in)

The default behavior is to advise. When the user explicitly asks to rewrite
("apply this voice to my draft", "rewrite my intro in the corpus voice"),
follow `references/style-application-instructions.md` exactly: section by
section, few-shot exemplar excerpts of the same section type, consensus
patterns only unless the user asks to mimic an author, and the critical
rules — never touch data, equations, numbers, or citations; never copy
exemplar phrasing; output to `<draft-stem>-rewritten.md`.

After every rewrite run both checks from the instructions file:

1. Content preservation — citations and numbers, per section.
2. Similarity guard:

```bash
$RUN <skill>/scripts/style.py similarity <draft-stem>-rewritten.md \
  --against <exemplar1.md> <exemplar2.md> --baseline <draft.md>
```

Any flagged match is phrasing the rewrite lifted from a source — report it;
the author must rephrase or quote it. The similarity check is also useful
standalone when the user asks to "check my draft for plagiarism against the
corpus" (omit `--baseline`).

## Headless mode

`match_voice.py` runs every mode without an interactive session, assembling
prompts from this skill's own `references/` files (single source of truth)
and calling `claude-opus-4-8` with adaptive thinking and streaming. Stable
content blocks (corpus, blueprint) are prompt-cached.

```bash
# Compare a draft against the corpus profile (one API call)
$RUN <skill>/scripts/match_voice.py <draft.md> --db <db-path>

# Extract a blueprint from exemplars (one call each + synthesis)
$RUN <skill>/scripts/match_voice.py --db <db-path> \
  --exemplar lee-meta-harness-2026 --exemplar path/to/other.md --name icml

# Rewrite a draft with the latest blueprint (one call per section)
$RUN <skill>/scripts/match_voice.py <draft.md> --db <db-path> --rewrite

# Extract and rewrite in one run; --mimic also applies idiosyncrasies
$RUN <skill>/scripts/match_voice.py <draft.md> --exemplar <paper> --rewrite --mimic
```

Exemplars are file paths or citation ids resolved through `references.yaml`.
After a rewrite the script verifies content preservation (citations,
numbers, per section) and runs the similarity guard against every source
paper with the original draft as baseline; flagged passages are listed in
the JSON summary and a warning is printed. Reports land in
`<db-dir>/voice-reports/`; usage stats print to stdout.

Requires `ANTHROPIC_API_KEY` (or an active `ant auth login` profile) at run
time; the `anthropic` package itself comes from the pixi environment. Suitable
for CI, cron, or a mage target.

## Dependencies

Both scripts run in the pixi environment (see "Running the scripts"), which
supplies PyYAML and — for `match_voice.py` — the `anthropic` package;
`style.py` is otherwise pure stdlib. No `pip install` is needed. The corpus
must have been fetched by `update-references` with markdown conversion
(issue #37) — plain-text legacy corpora work but lose section detection
quality.
