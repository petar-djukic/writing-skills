<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: stitch-flow
description: >-
  Repair discourse flow across paragraph boundaries after say-per-paragraph
  drafting: locate joints where a paragraph opens with a freestanding thesis
  instead of taking a handoff from the previous paragraph's close, then
  rewrite openings only — theme of the opener drawn from the rheme of the
  paragraph before, duplicate definitions merged, rhythm varied — leaving
  claims, citations, anchors, and rst markers untouched. Ships openers.py,
  which prints each section's joint chain with weak-joint and
  duplicate-definition flags. Triggers: stitch the flow, the paragraphs
  don't flow, written paragraph by paragraph, doesn't read as one piece,
  weak joints, paragraph openers, given-new.
argument-hint: '<chapter.md> [...] (detection); then the stitch pass by hand'
---

# Stitch Flow (discourse joints between paragraphs)

## The failure this fixes

SRD-first drafting writes one say per paragraph, and each say is written to
be complete in itself. The result reads correct and does not flow: nearly
every paragraph opens with a freestanding thesis sentence ("An agent is a
generic runtime." / "A role is a specification." / "Switching roles costs
no release."), takes no handoff from the paragraph before it, and could be
shuffled without breaking the text. Secondary symptoms of the same cause:
uniform paragraph rhythm (definition, elaboration, consequence, three to
five sentences, every time), section cross-references doing the work
transitions should ("the previous section's sense"), and the same thing
defined twice because each paragraph re-establishes its own context.

The failure has shipped twice (agent-dsl; autogenic-systems
roles-and-teams) because every existing gate reads one paragraph at a
time. reverse-outline checks that each satellite serves its section's
nucleus — logical coherence, not flow. tighten-style TS-10/TS-11 govern
the spine inside a paragraph, and its rewriter refuses to add transitions
by contract. Critic panels see passages. And match-structure's
paragraph_cohesion metric — tf-idf overlap between consecutive
paragraphs — scores the disease higher than the cure: the roles-and-teams
article measured 0.16 against 0.08-0.12 for its venue exemplars, because
re-establishing the same nouns in every paragraph is exactly what the
metric rewards. Do not gate this skill on that number.

## Detection

```bash
python3 scripts/openers.py chapter1.md chapter2.md ...
```

Per section, the script prints the joint chain — the last sentence of
paragraph N over the first sentence of paragraph N+1 — and flags:

- **WEAK**: the opener neither shares a content word with the previous
  paragraph's closing two sentences nor starts with a connective,
  demonstrative, or pronoun. A paragraph after an exhibit (table, figure,
  list) starts a fresh chain and is never flagged.
- **DUP**: two definitional sentences ("X is ...") whose content words
  overlap enough to be the same definition stated twice.
- The paragraph word-count spread, as a rhythm check.

The script locates; the reader decides. A hard cut at a genuine turn is
legitimate, and a section's first paragraph owes nothing to the heading.
Read the flagged joints in the full section before touching any of them.

## The stitch pass

Work one section at a time, with the whole section in view. For each weak
joint the reading confirms:

1. **Rewrite the opening only** — the first sentence, usually its first
   clause. Make the opener's theme the previous paragraph's rheme: the
   thing the last sentence left the reader holding is the thing the next
   sentence picks up. The claim the paragraph states does not change; the
   SRD say constrains content, not openings.
2. **Merge duplicates**: keep the definition at the anchor that governs
   it, and turn the other occurrence into a reference that carries new
   information instead of restating.
3. **Vary the rhythm** where two adjacent paragraphs share the same
   shape: fold a two-sentence satellite into its neighbor, or let one
   paragraph run long where the content carries it.
4. **No adverbial glue.** "Moreover", "Additionally", "In addition" are
   mechanical transitions filter-tells rightly flags; the handoff is
   thematic, not adverbial. If the only available link is an adverb, the
   paragraphs are in the wrong order — consider that before writing.

Never change: claims, numbers, quotations, citations, exhibit content,
anchor comments, rst markers, lock spans. If an opener rewrite makes an
anchor's one-line summary stale, update the anchor with it, in the same
commit.

## Gates after the pass

In order, all required where the repository has them:

1. `rst_markers.py check` per changed file, then the reverse-outline
   re-check of each paragraph against its marker — an opener rewrite must
   not change what the paragraph does for the argument.
2. **cold-review** screen, baseline vs candidate: a stitch pass is a
   rewrite pass, and entailment damage (inverted claims, reattached
   numbers) is exactly what it risks.
3. **filter-tells** on the changed files — the pass adds connective
   openers, which is where mechanical-transition tells would enter.
4. The repository's own build, census, and audit targets.

Re-run openers.py last and expect the weak count to fall, not to zero —
the residue should be the deliberate cuts.

## Boundaries

| Skill | Owns | Does not own |
|---|---|---|
| stitch-flow | the joints between paragraphs; duplicate definitions; rhythm | anything inside a paragraph's body |
| tighten-style | TS-10/TS-11 spine inside a paragraph | transitions (its rewriter refuses them) |
| reverse-outline | nuclearity: what each paragraph does for the argument | whether N+1 picks up where N left off |
| match-voice / humanize | register and diction per passage | discourse structure |
| cold-review | entailment between baseline and candidate | authoring any prose |

match-structure's paragraph_cohesion cannot gate or measure this skill;
see above. The only trustworthy detector is openers.py plus a human read
of the flagged joints.
