<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: rewrite-pipeline
description: >-
  End-to-end rewrite of one markdown article as a multi-agent Workflow:
  the humanize chain once (filter-tells, seeded match-voice,
  tighten-style, terminal inject-vernacular), then the review phase in a
  loop — reverse-outline, a deterministic length pre-check, the
  three-critic panel answering the caller's focus brief by name,
  critic-apply, cold review, ross read, voice-critic — re-reading until a
  panel read of the final text changes nothing. Ends in one report and a
  generation-note entry; residue is reported, never parked. Invoking
  this skill is the opt-in to the Workflow run. Triggers: rewrite
  pipeline, full rewrite, humanize and review, run the whole pipeline,
  rewrite this article, humanize it and run the critics.
argument-hint: '<article.md> [--skip-humanize] [--max-rounds N] [--focus-file path] [--venue name]'
---

# Rewrite Pipeline (humanize, then review until stable)

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

## Launch

Run the bundled script with the Workflow tool, from the repository that
holds the article:

```
Workflow({
  scriptPath: "<this skill's directory>/workflow.js",
  args: { article: "<path/to/article.md>" }
})
```

In a repository that composes skills under `.cursor/skills/`, the
script path is `.cursor/skills/rewrite-pipeline/workflow.js`. When the
run returns, relay its report to the author in plain prose: rounds,
what each round applied, the last panel read's convergent findings and
focus answers, and the residue still open. The report is the record;
nothing is written to a sheet.

| arg | default | meaning |
|---|---|---|
| `article` | required | the markdown file to rewrite |
| `skills_dir` | `.claude/skills` | where the owning skills live |
| `skip_humanize` | false | review only: the text already went through the chain |
| `max_rounds` | 3 | review rounds before the read-only final pass |
| `focus_file` | discovered | path to the caller's `critic-focus.md` |
| `form` | inferred | article form; selects the constitution and voice-critic caps |
| `venue` | none | passed to humanize's venue mode |
| `validate_only` | false | preflight only: checks paths and focus file, changes nothing |

Run `validate_only` first in a repository the skill has not run in.

## The stages

| phase | stage | owning skill | writes |
|---|---|---|---|
| Preflight | branch check, skill paths, focus file, form, protected spans, baseline commit | — | baseline commit only |
| Humanize | the chain, once, one commit per stage | humanize | yes |
| Review, each round | annotate or audit, rank | reverse-outline | markers only |
| | length pre-check | the focus file's command | no |
| | three critics in parallel, fresh contexts, focus brief answered by name | critic-panel Mode A | reports |
| | merge | critic-panel `converge.py` | sheet |
| | rule-based application | critic-apply | candidate |
| | fresh-context entailment, reverts only | cold-review | yes |
| | cross-family comprehension read | critic-panel Mode C | rounds 1–2 only |
| | voice audit | voice-critic | no |
| Final read | read-only panel on the shipping text, when the round cap stopped the loop | critic-panel Mode A | no |
| Record | generation-note entry, sidecar sweep | — | yes |

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
caller. Put a `critic-focus.md` at or above the article — the skill
walks up from the article to find the nearest — naming each check as one
item, plus one deterministic pre-check command with `{article}` as the
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

It is the caller's step 6 in one call: what `write-article` runs after
the draft exists, and what "rewrite this article" means. The caller
still owns structure (match-outline before the chain), publication
decisions, and the author's read; this skill hands the author a stable
text and an honest residue list.
