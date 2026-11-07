<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: polish-prose
description: >-
  Improve, polish, tighten, or make better any prose a person reads end
  to end — an essay, post, paper section, README, or book chapter. The
  default for any request to improve a whole piece of writing ("can you
  improve this", "make this better", "polish this", "this is meh", "it
  reads flat", "clean this up"), ahead of the single-stage skills it
  runs. One multi-agent Workflow: the humanize chain once (filter-tells,
  seeded match-voice, tighten-style, terminal inject-vernacular), then
  the review loop — reverse-outline, a length pre-check, a critic panel
  answering the caller's focus brief by name, critic-apply, cold review,
  ross read, voice-critic — re-reading until a panel read of the final
  text changes nothing. Line and paragraph work; restructuring a piece
  is a separate refine pass. Invoking this skill is the opt-in to the
  Workflow run. Triggers: improve this, polish this, make it better,
  tighten this, it's meh, it reads flat, clean up this draft, rewrite
  this, full rewrite, humanize and review, run the whole pipeline.
argument-hint: '<file.md> [--skip-humanize] [--max-rounds N] [--roster name] [--focus-file path] [--venue name]'
---

# Polish Prose (humanize, then review until stable)

The pipeline used to live only as prose in the caller's workflow
command, executed by hand one stage at a time. Prose rules get skipped:
on the article that prompted this skill, the panel read a draft on
2026-10-21, two later cycles added prose, and nothing re-read it — the
author found the result flat on his own read. This skill moves the
order, the parallel critics, and the re-read into a Workflow script,
where a skipped step is impossible rather than unlikely.

**It owns order and the loop, nothing else.** Every stage is one agent
that reads the owning skill's SKILL.md and follows it. No stage command,
model name, or threshold is restated here or in the script; when a
stage changes, its own skill changes and this pipeline picks it up.

**Polish, not refine.** This pass works on lines and paragraphs: cuts,
splits, diction, the announcing clause, the paragraph that restates the
lede. It will report that a piece wants splitting in two or a section
reordered, but it does not do that work; structure is a refine pass
(match-outline, reverse-outline's cut list) the caller runs first.

## Launch

Run the bundled script with the Workflow tool, from the repository that
holds the file:

```
Workflow({
  scriptPath: "<this skill's directory>/workflow.js",
  args: { article: "<path/to/file.md>" }
})
```

In a repository that composes skills under `.opencode/skills/`, the
script path is `.opencode/skills/polish-prose/workflow.js`. When the run
returns, relay its report to the author in plain prose: the roster
used, rounds, what each round applied, the last panel read's convergent
findings and focus answers, which optional stages were skipped and why,
and the residue still open. The report is the record; nothing is
written to a sheet.

| arg | default | meaning |
|---|---|---|
| `article` (or `file`) | required | the markdown file to polish |
| `skills_dir` | `.claude/skills` | where the owning skills live |
| `roster` | by form | a critic-panel roster name or a list of persona names |
| `skip_humanize` | false | review only: the text already went through the chain |
| `max_rounds` | 3 | review rounds before the read-only final pass |
| `focus_file` | discovered | path to the caller's `critic-focus.md` |
| `form` | inferred | the file's form; selects its constitution and voice-critic caps |
| `venue` | none | passed to humanize's venue mode |
| `validate_only` | false | preflight only: reports roster, focus file and skipped stages, changes nothing |

Run `validate_only` first in a repository the skill has not run in.

## Any prose, not just articles

| what preflight finds | what changes |
|---|---|
| a book chapter | the `book` roster (verdict critics) instead of `article` |
| `docs/constitutions/*.yaml`, an SRD, a form constitution | every critic judges against those rules first (critic-panel's "The draft's own rules") |
| no `writing-voice/` corpus | humanize is skipped: match-voice needs the exemplars |
| no voice constitution | voice-critic is skipped: it refuses without one |
| no YAML front matter | no generation note; the report is the record |

Every skip is named in the report, never silent.

## The stages

| phase | stage | owning skill | writes |
|---|---|---|---|
| Preflight | branch check, skill paths, focus file, form, roster, the draft's rules, protected spans, baseline commit | — | baseline commit only |
| Humanize | the chain, once, one commit per stage | humanize | yes |
| Review, each round | annotate or audit, rank | reverse-outline | markers only |
| | length pre-check | the focus file's command | no |
| | the roster in parallel, fresh contexts, focus brief answered by name | critic-panel Mode A | reports |
| | merge | critic-panel `converge.py` | sheet |
| | rule-based application | critic-apply | candidate |
| | fresh-context entailment, reverts only | cold-review | yes |
| | CoT warrant tails removed by deletion only, two fresh legs | critic-panel `iceberg` roster + critic-apply | yes |
| | cross-family comprehension read | critic-panel Mode C | rounds 1–2 only |
| | voice audit | voice-critic | no |
| Final read | read-only panel on the shipping text, when the round cap stopped the loop | critic-panel Mode A | no |
| Record | generation-note entry when there is front matter, sidecar sweep | — | yes |

The persona critics run on the session model; the ross read adds two
Ollama models from different families, and only its cross-family
convergence gets fixed.

## The stopping rule

A panel read binds only the text it read (critic-panel Mode A). Each
round reads the current text; if the round changed the prose (markers
excluded), the next round re-reads it, carrying this round's unapplied
convergent targets and paragraph moves as residue the critics must
check by name. The loop ends when a round changes nothing: that round
was a read of the final text. At the round cap, one read-only panel
pass runs on the final text, so the report always describes what ships.

The ross read fixes cross-family convergent findings in round 1,
repairs regressions in round 2, then only reads (the batch cap).
Humanize runs once: re-running the chain on gated prose degraded it in
measurement (0.621 to 0.579 human, 2026-08-22), and the caller decides
any further cycle from the seed-reach report.

## The focus brief

Generic persona briefs miss what the author already knows to look for;
briefed with his standing complaints, the panel converged in one pass on
classes a generic read had surfaced none of. The list belongs to the
caller. Put a `critic-focus.md` at or above the file — the skill walks
up from the file to find the nearest — naming each check as one item,
plus one deterministic pre-check command with `{article}` as the
placeholder. Absent, the panel gives its free read and the report says
so.

## Contracts it inherits

- **Worktree branches only.** Preflight refuses on `main`; every stage
  commits.
- **No hand-written prose.** Agents analyse and choose; text changes
  only through the rewrite transport, mechanical deletions, and
  verbatim reverts.
- **Protected spans hold.** Constitution-required spans, locked spans,
  numbers, citations and quotations pass through every stage untouched.
- **Sidecars die in the step that consumed them**, and the Record stage
  sweeps anything left (critic-panel's Artifact hygiene).

## Position

It is the caller's whole review pipeline in one call: what a
workflow command runs after a draft exists, and what "improve this"
means for any finished piece of prose. The caller still owns structure,
publication decisions, and the author's read; this skill hands the
author a stable text and an honest residue list.
