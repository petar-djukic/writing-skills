<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# reverse-outline Prompts

Two model-driven runs, `annotate` and `audit`. Both go to the **session
model** — Claude, one fresh-context agent per run, as critic-panel spawns its
critics. Neither writes prose.

## Why not the second family

Every other prose skill sends its generation to a different model family than
the one drafting, so the draft's diction is not judged by the model that
produced it. That rule governs **prose**, and this skill writes none. What it
writes is a label. A wrong label is not a stylistic blemish; it ranks the
wrong paragraph for deletion, and the author cuts a load-bearing one. The
labelling is the whole value of the skill, so it goes to the strongest model
available (author decision, 2026-08-22).

Maekawa et al. (EACL 2024) reach state-of-the-art RST parsing with a 70B model
at the harder clause level. Paragraph grain with ~20 relations is well inside
that, which is why no parser is built.

## Shared constraints

Both prompts carry these, and every one of them is hard.

- **Never modify a prose line.** The runs emit marker lines and reports. A
  diff that touches prose is a failed run.
- **Locked spans are untouchable.** Text between `<!-- lock -->` and
  `<!-- /lock -->` is read for context and never annotated inside. A marker
  goes above the paragraph containing the lock, never within it.
- **Exactly one `nucleus` per section.** If two paragraphs both look like the
  point, the section is doing two jobs; pick the one the other supports and
  label the loser with its actual relation.
- **`split` when no single function can be stated.** A paragraph doing three
  things gets `split`. Guessing which of the three dominates loses the
  finding.
- **`joint` when nothing attaches.** A paragraph the argument does not reach
  is a finding in its own right.
- **One-liners are direction, not prose.** They say what the paragraph does
  for its target — "a bank's loan form enforces the same three blanks daily",
  not a summary of its content and not a rewrite of its first sentence. They
  are read as a list, so they are written to be read as a list.
- **Relations come from the closed set** in
  [relations.md](./relations.md). A label outside it is a failed run.

## `annotate`

One fresh-context agent, given the article and the shared constraints.

**Input.** The whole article, and its front-matter `thesis:` line. When there
is no `thesis:`, the agent proposes one and the author confirms before
labelling starts — that is a decision about the article's direction, and it
belongs to the author. The proposal is one sentence naming what the article
claims, for whom, and what would falsify it.

**Task.** Emit one marker per heading and per prose paragraph:

```
<!-- rst: <relation>[ -> <n>] | <one line: what it does for its target> -->
```

`-> n` is the 1-indexed paragraph **within the section** that this satellite
attaches to. Omit it and the target is the section nucleus. On a heading, the
relation is the section's relation to the `thesis:` line.

**Order of work**, and it matters:

1. Read the whole article before labelling anything. A paragraph's function is
   defined by what surrounds it, so a first-pass label written while reading
   forward is a guess about text not yet seen.
2. Per section, find the nucleus first. Every other label in the section is
   relative to it.
3. Label the remaining paragraphs against the nucleus or against each other.
4. Label the headings against the thesis, last, when the sections are known.

**Output.** The marker lines with the paragraph each belongs above, for
`rst_markers.py` to write in. The script validates before writing: one nucleus
per section, every target present, no cycles, every prose paragraph labelled.
A tree that fails validation is returned to the agent with the specific
violation, not written and not repaired by hand.

**The failure to watch for.** A labeller under pressure to produce a clean
tree will label a repetitive paragraph `elaboration` rather than
`restatement`, because `elaboration` is always defensible. That single
substitution moves the paragraph three ranks down the cut order and hides the
finding the author ran the skill for. When a paragraph says a thing the
article has already said, the label is `restatement` even when the wording is
entirely new.

## `audit`

One fresh-context agent per run, after any rewrite pass.

**Input.** Each paragraph paired with its own existing marker. The agent does
not see the ranking and is not asked to improve anything.

**Task.** For each pair, answer one question: **does this paragraph still do
what its marker says it does?** Three verdicts.

| Verdict | Meaning |
|---|---|
| `holds` | The paragraph still performs the labelled function for its target. |
| `eroded` | It still gestures at the function but no longer performs it — the evidence lost its figure, the concession lost what it conceded. |
| `changed` | It now does something else, and the marker names what it used to do. |

**Report.** Paragraph number, verdict, and for anything other than `holds`,
one line on what is missing. Nothing is repaired and nothing is relabelled;
the author decides whether the pass or the marker was wrong.

**What this is for.** The erosion defect from the socratic run (substack
GH-185): real points compressed by successive passes into residue, each pass
defensible on its own and the sequence destructive. No other gate catches it,
because every other gate reads a paragraph against its previous version rather
than against its purpose. The marker is a statement of purpose written before
the passes ran, which is why it can catch this and a diff cannot.

## Sources

- Maekawa, Hirao, Kamigaito, Okumura (2024). *Can we obtain significant
  success in RST discourse parsing by using Large Language Models?* EACL 2024.
  https://aclanthology.org/2024.eacl-long.171/
