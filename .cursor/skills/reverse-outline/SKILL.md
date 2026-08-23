<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: reverse-outline
description: >-
  Decompose an article into its argument structure, persist that structure as
  HTML-comment markers in the text, and rank every paragraph and section by
  what the argument loses if it is cut. RST nuclearity at paragraph grain run
  as a reverse outline: one line per paragraph saying what it does for which
  other paragraph, then a deletion sheet ordered by distance from the point.
  Also re-checks each paragraph against its own marker after a rewrite pass,
  which is how compression damage becomes visible. Never rewrites prose.
  Triggers: reverse outline, decompose the argument, what can I cut, rank
  paragraphs, rst map, does this section earn its place, erosion check.
argument-hint: 'Path to the markdown article, plus one of: annotate | rank | audit | strip'
---

# reverse-outline

Answers one question the other instruments cannot: **what does this section
say that an earlier one did not?**

Every existing tool works on a unit smaller than the problem. `tighten-style`
tightens sentences. `critic-panel` nominates one paragraph per critic. The
polemic blueprint budgets one structure in one form. AI-drafted text goes on
at the section as readily as at the sentence, and nothing asks a section to
justify its existence.

This skill labels the argument, then ranks by what deletion would cost. The
author cuts from the bottom. **No prose is written, at any point**, which is
why it can run after the terminal stage that forbids a generative pass.

## Method

Three published pieces, one procedure.

- **Reverse outlining** (writing-centre practice; the Waterloo handout) is the
  procedure: write one sentence per paragraph saying what it *does*, then read
  the sentences against the thesis and look for repetition, drift, and gaps.
  Done by hand it works and nobody does it, because it is tedious at article
  length and has to be redone after every revision.
- **Rhetorical Structure Theory** (Mann & Thompson 1988) is the labelling.
  Spans join in pairs: a **nucleus** the author's purpose depends on, and a
  **satellite** supporting it. The definitional test is deletion — remove a
  satellite and the text still makes its point; remove a nucleus and it does
  not. RST's relation set is closed and each relation states its intended
  effect on the reader, which is exactly the "why is this paragraph here" line
  a reverse outline asks for.
- **Marcu (1997)** is the ranking: units ordered by nuclearity depth match
  what human summarizers keep. Read backwards, that is a deletion order.

See [references/relations.md](./references/relations.md) for the relation set,
the definitions, and the cut order.

### What this adds to the methods

Three additions, and each one is load-bearing.

1. **Paragraph grain, not clause.** RST parsers work on elementary discourse
   units, roughly clauses. The paragraph is the unit an author actually cuts,
   so it is the unit labelled.
2. **Markers persisted in the text.** The structure is written into the
   article as HTML comments, so it survives every rewrite pass and can be
   re-checked after each one. A reverse outline in a separate file is stale
   the moment the author edits, which is the reason the hand method does not
   survive contact with revision.
3. **A cut order among satellites at equal depth.** Marcu ranks by depth
   alone. The order in `relations.md` breaks those ties, derived from the
   relation definitions — and it is flagged there as the skill's one judgment
   call.

## Marker grammar

One comment line per unit: immediately **above** each paragraph, and
immediately **below** each heading — a marker above a heading sits at the
end of the previous section and reads as though it belongs there.

```
<!-- rst: <relation>[ -> <n>] | <one line: what it does for its target> -->
```

- **relation** — from the closed set in
  [references/relations.md](./references/relations.md): `nucleus`;
  presentational (`evidence`, `justify`, `concession`, `antithesis`,
  `motivation`, `preparation`, `background`, `restatement`, `summary`);
  subject-matter (`elaboration`, `interpretation`, `evaluation`,
  `circumstance`, `purpose`, `solutionhood`); multinuclear (`contrast`,
  `sequence`, `list`, `joint`); plus `split` when no single function can be
  stated.
- **`-> n`** — the 1-indexed paragraph *within the section* this satellite
  attaches to. Omitted means the section nucleus. Depth is the number of hops
  to that nucleus, computed rather than stored.
- **On a heading** — the same grammar, on the line below the heading, gives
  the section's relation to the `thesis:` line in front matter.
- **Exactly one `nucleus` per section.**

```markdown
---
title: Strategy Theatre
thesis: a document that cannot say what, for whom, and for how much is not a strategy, and the machine makes such documents free
---

## The Three Questions
<!-- rst: evidence | the three blanks every lender already enforces -->

<!-- rst: nucleus | a strategy answers what / who pays / how much -->
The difference between a real strategy and a document that looks like one…

<!-- rst: evidence | a bank's loan form enforces the same three blanks daily -->
A plumber financing a second truck…

<!-- rst: elaboration -> 2 | unpacks the loan-form analogy -->
The form has no box for a diagram…

<!-- rst: restatement | says the three questions again -->
These questions are boring, which is the point.
```

### Why comments, and why they survive

The markers ride rails that already exist. `<!-- lock -->` has travelled the
whole pipeline as a comment since GH-57. `md_paragraphs.parse` classifies
comment lines as non-prose and, since GH-86, does so by content and state
rather than by how a line starts. The replacement drivers splice prose line
ranges only, so a marker line is never inside a range a rewrite can touch.
`critic-panel/scripts/prepare_copy.py` already drops comments before a critic
reads.

Nothing new had to be built to make the structure persist, which is the whole
argument for putting it in comments.

## Runs

### `annotate <article.md>`

Model run. A fresh-context agent reads the article and its `thesis:` line —
proposing one if absent, for the author to confirm, since that is a decision
about direction rather than prose — and emits one marker per heading and
paragraph. `rst_markers.py` validates the tree before writing: one nucleus per
section, every `-> n` target present, no cycles, every prose paragraph
labelled. Locked spans are never annotated inside.

A tree that fails validation goes back to the agent with the violation named.
Hand-repairing it would produce a tree nobody can reproduce.

### `rank <article.md>`

Deterministic from the markers alone. No model call. Writes
`<stem>.outline.md` with four sections:

1. **The reverse outline** — the one-liners in document order. Read together
   they should tell the article's story; where they do not, the article does
   not either.
2. **Deletion candidates** — `joint` first, since a paragraph the argument
   never reaches beats a distant one that at least supports something; then
   by depth descending, then by cut order. Sections ranked against the
   thesis. Every row carries its paragraph number.

   Beneath the table, **runs that can be cut whole**: a `contrast`, `sequence`
   or `list` group whose every member is otherwise deletable, ranked by its
   best member and listed as one row, because cutting a stay/leave/decide
   passage is one decision rather than five. Members keep their own rows —
   whether the run goes and which paragraph in it is weakest are different
   questions. Any multinuclear paragraph no run accounts for is **named**
   under the table rather than dropped; see
   [references/relations.md](./references/relations.md).
3. **Repetition pairs** — same relation, same target, near-duplicate
   one-liners, by `difflib` as `converge.py` does it.
4. **`split` paragraphs** — the monster-paragraph list. These are rewrite
   candidates rather than deletions.

The run is read-only: the author picks by number, and the picks go in as an
author-directed cycle.

### `audit <article.md>`

Model run, after any rewrite pass. Each paragraph is read against its own
marker and answered in one question: does it still do what the marker says?
Verdicts are `holds`, `eroded`, or `changed`; mismatches are listed and
nothing is repaired.

**This is the erosion detector.** The socratic run (substack GH-185) found
real points compressed by successive passes into residue — each pass
defensible alone, the sequence destructive. No other gate catches it, because
every other gate compares a paragraph to its previous version. The marker
states the paragraph's purpose, written before the passes ran, so it can catch
what a diff cannot.

### `strip <article.md>`

Removes every `rst:` marker and nothing else. Belongs on the paste checklist
beside the SUBSCRIBE BLOCK comment.

### `check [--renumber] <article.md>`

Validation on its own, and `--renumber` repairs `-> n` targets after the
author adds or deletes paragraphs. A target whose referent was itself deleted
is reported rather than guessed at.

## Placement

```
draft → annotate → rank → author cuts → cycle
      → humanize stages (markers ride along) → audit
      → critic-panel / voice-critic → strip at paste
```

The skill writes only comments, never prose, so running `audit` late does not
violate the GH-57 read-only-after-terminal contract. That contract exists
because a generative pass after the terminal stage regresses the text toward a
model's centre; a run that cannot write prose cannot do that.

## Model

`annotate` and `audit` run on the **session model** (Claude), one fresh-context
agent per run, not on the Ollama second family. The cross-family rule protects
prose diction, and this skill writes no prose. A weak labeller produces a wrong
tree, and a wrong tree ranks the wrong paragraph for deletion — the labelling
is the entire value of the skill. Author decision, 2026-08-22; the reasoning is
in [references/prompts.md](./references/prompts.md).

`rank`, `check`, `renumber`, and `strip` make no model call at all.

## What this skill will not tell you

- **Whether a paragraph is any good.** It reports function and distance from
  the point. A well-written `restatement` at depth 3 ranks exactly where a
  badly-written one does.
- **What to cut.** The sheet is a reading order for a decision. Nothing is
  deleted, and a ranking that reaches `evidence` is describing an article with
  nothing left to trim rather than recommending a cut.
- **Whether the thesis is right.** It measures the article against the thesis
  it was given. A coherent article arguing the wrong thing passes cleanly.

## Dependencies

- `.claude/scripts/md_paragraphs.py` — paragraph extraction and line
  classification.
- `.claude/scripts/prose_document.py` — the document model markers survive.
- `.claude/scripts/span_locks.py` — the lock contract `annotate` respects.

## Sources

- Mann, W. C. and Thompson, S. A. (1988). *Rhetorical Structure Theory: Toward
  a functional theory of text organization.* Text 8(3), 243–281.
- Marcu, D. (1997). *From discourse structures to text summaries.* ACL.
  https://aclanthology.org/W97-0713/
- Maekawa et al. (2024). *Can we obtain significant success in RST discourse
  parsing by using Large Language Models?* EACL 2024.
  https://aclanthology.org/2024.eacl-long.171/
- Waterloo Writing and Communication Centre, *Reverse Outline.*
  https://uwaterloo.ca/writing-and-communication-centre/reverse-outline
