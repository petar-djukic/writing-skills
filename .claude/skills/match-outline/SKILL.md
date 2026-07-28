---
name: match-outline
description: >-
  Section-level voice analysis: compare a draft's outline against a corpus
  profile, extract voice persona blueprints from exemplar papers, and
  rewrite a draft section by section to match a voice. Uses match-structure
  for quantitative metrics and similarity checks. Triggers: compare my
  outline, section analysis, does my intro match the field, methodology
  conventions, results conventions, rewrite in the style of, apply the
  voice, voice persona, exemplar, blueprint extraction, mimic this paper,
  rewrite my intro, section-by-section rewrite.
---

# Match outline (section-level voice analysis)

This skill answers "does my draft's structure and section-level voice match
the field?" It detects sections (intro, methodology, results, conclusion),
compares their metrics and conventions against a corpus profile, extracts
voice persona blueprints from exemplar papers, and rewrites drafts section
by section with a plagiarism guard.

It complements `match-structure` (which provides the quantitative metrics,
frequency tables, and similarity math this skill imports) and `filter-tells`
(which detects generic AI-writing patterns at the paragraph level).

## Where things live

- **Quantitative profile:** `<db-dir>/voice-profile.json`, written by
  `match-structure`'s `style.py corpus`.
- **Qualitative profile:** `<db-dir>/voice-profile.md`, written by the model
  following `references/voice-analysis-instructions.md` Part 1.
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

## The workflow (interactive)

### 1. Locate the corpus

Find `references.yaml` at or above the working directory. If it does not
exist, or no entries have `status: summarized` with an existing `md_path`
file, stop and tell the user to run `update-references` first.

### 2. Quantitative profiles

```bash
$RUN <match-structure>/scripts/style.py --db <db-path> corpus
```

This writes `voice-profile.json`. Skip if the existing profile is unchanged.

### 3. Qualitative profile

Read the corpus papers and write `voice-profile.md` following **Part 1** of
`references/voice-analysis-instructions.md`. Every claim carries a quote.

### 4. Compare the draft

```bash
$RUN <match-structure>/scripts/style.py --db <db-path> compare <draft.md>
```

Then write the comparison report following **Part 2** of
`voice-analysis-instructions.md` and the structure of
`comparison-report-template.md`.

### 5. Report back

Summarize: the verdict (close match / partial / divergent), the two or
three highest-impact changes, and the report path.

## Exemplar blueprints (mimic a specific paper or venue)

When the user wants to mimic specific papers, extract a voice persona
blueprint following **Part 3** of `voice-analysis-instructions.md`.

## Rewrite mode (opt-in)

Section by section, following `references/style-application-instructions.md`.
After every rewrite: content preservation check (citations, numbers) and
similarity guard via `match-structure`'s `style.py similarity`.

## Headless mode

`match_outline.py` runs every mode without an interactive session.

```bash
# Compare a draft
$RUN <skill>/scripts/match_outline.py <draft.md> --db <db-path>

# Extract a blueprint
$RUN <skill>/scripts/match_outline.py --db <db-path> \
  --exemplar paper1 --exemplar paper2 --name icml

# Rewrite a draft
$RUN <skill>/scripts/match_outline.py <draft.md> --db <db-path> --rewrite
```

## Exemplar sources

Two sources of exemplars are accepted:

- **`references.yaml` corpus** (default) — the papers fetched by
  `update-references`, selected with `--db`.
- **`writing-voice/manifest.yaml`** — a curated exemplar directory. Pass
  `--voice-dir <path>` with optional `--role`, `--anchor-tags`, `--stratum`.

## Dependencies

Both scripts run in the pixi environment. `match_outline.py` imports
`style` from `match-structure/scripts/` for section detection, corpus
selection, and the similarity guard. The `anthropic` package is needed only
for `--model claude-*`.
