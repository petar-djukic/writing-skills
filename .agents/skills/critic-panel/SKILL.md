<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: critic-panel
description: >-
  Read-only critics for a finished draft, run before voice-critic. Two
  modes: panel — named persona critics read in parallel from fresh
  contexts and merge into one sheet with cross-critic convergence first;
  socratic — one critic interrogates the article with genuine questions
  anchored to sentences, and the author's written answers become the edit
  plan. Two critic kinds: suggest critics return line-level
  original/replacement edits, verdict critics quote the passage and state
  the finding without rewriting it. Named rosters: article (Levine,
  Didion, Hemingway) for essays, book (Fowler, Yegge, Deitel, Miller,
  Cook, Kreischer) for chapter drafts, or any ad-hoc mix. The skill never
  applies anything; the author picks, and the picks become an
  author-directed cycle. Triggers: critic panel, read it like Levine, pace
  critic, turn of phrase, it's only fine, socratic read, interrogate the
  draft, what would make this better, review chapter, critique my chapter,
  six critics, is this chapter any good, clarity test, bullshit test,
  pedagogy test, does this chapter work.
argument-hint: 'Path to the draft, plus optionally: --roster article | book | <names>'
---

# Critic Panel (read-only zone, before voice-critic)

A draft that has cleared every gate is clean, correct, and often only
fine — every pass was allowed to remove risk, none was hired to add. This
skill hires the adders, on a leash: critics read and propose, the author
chooses, and nothing reaches the text except through an author-directed
cycle. It sits in the read-only zone (GH-57: after the terminal stage,
models read but never write) ahead of voice-critic, because its picks
change what voice-critic would audit.

```
terminal stage (inject-vernacular)
  -> critic-panel (this)          read-only: diagnosis + suggestions
  -> author picks -> new author-directed cycle (the only way text changes)
  -> voice-critic                  read-only: stance, snark, ToM audit
  -> author gate
```

## Mode A: panel

1. Build the reading copy: `scripts/prepare_copy.py <article.md>` — front
   matter and REFERENCES stripped, figures collapsed, locked spans shown as
   `[[LOCKED: … :LOCKED]]`.
2. Spawn one fresh-context agent per **roster entry**, in parallel, each
   with its persona brief from
   [references/personas.md](./references/personas.md), the constraints its
   kind carries, and the report format its kind prescribes, writing to
   `<stem>.critic-<name>.md`. **The headings below are literal and the report
   is machine-read** — `## Suggestions`, not `## Ten line-level suggestions`.
   Step 3 refuses a report it cannot parse rather than merging it as empty.
3. Merge: `scripts/converge.py <reports…> --out <stem>.critic-sheet.md
   [--roster <names>]` — findings targeting the same passage across critics
   are listed first, whichever kind produced them; agreement between
   independent critics is the headline signal. `--roster` sets sheet order.
4. Hand the sheet to the author. Picks by critic and number become a
   loop-workflow issue; apply them as an author-directed cycle, then
   rescan and run voice-critic on the result.

### Rosters

Personas and their kinds live in
[references/personas.md](./references/personas.md). A roster is a list of
them.

| Roster | Personas | Kind |
|---|---|---|
| `article` (default) | Levine, Didion, Hemingway | `suggest` |
| `book` | Fowler, Yegge, Deitel, Miller, Cook, Kreischer | `verdict` |
| ad-hoc | any mix by name, e.g. `--roster levine,yegge,cook` | per persona |

Roster order is sheet order, never execution order. A chapter with a fuzzy
central concept cannot be fixed by a better opening, so clarity and honesty
render ahead of hook and story — but the critics still read in parallel from
fresh contexts, because convergence between critics who could not see each
other is the whole signal. Running them in sequence to get that ordering
would buy the reading order and sell the independence.

Swap or add personas by brief; the skill is the shape, not the names.

### The two report formats

A persona's kind decides its format. An adder proposes the replacement; a
diagnostician names the defect and leaves the prose to the author. Forcing
one into the other's shape yields a line edit for a conceptual problem.

**`suggest`** — what the article roster returns:

```
## Diagnosis
<three sentences on why it reads as only fine>
## Suggestions
### 1
Original: <the exact sentence, verbatim, so it can be found>
Replacement: <proposed sentence, or CUT>
Buys: <one line on what it buys>
…
## Paragraph move
<the single cut, reorder, or added scene, described — not rewritten>
```

**`verdict`** — what the book roster returns:

```
## Diagnosis
<three sentences on what the chapter is doing and where it strains>
## Findings
### 1
Passage: <the exact passage, verbatim, so it can be found>
Finding: <what is wrong with it, in this critic's terms>
Fix: <what would fix it, described — never written as replacement prose>
…
## Verdict
<the persona's own verdict format, from references/personas.md>
```

`converge.py` groups on the verbatim field — `Original` for suggest,
`Passage` for verdict — so two diagnosticians quoting one passage converge
exactly as two adders targeting one sentence do, and a diagnostician and an
adder converge on the same passage too.

**The section headings and field names are read literally, and a report that
does not carry them is refused.** The panel's first real run wrote
`## Ten line-level suggestions` and `1. **Original:**`; `converge.py` matched
nothing, reported `3 critics, 0 suggestions`, and wrote a sheet anyway, so the
sheet a human worked from that day was assembled by hand and nothing recorded
that the tool had contributed nothing (GH-107). A report parsing to nothing
now names itself and stops the merge.

A verdict critic with **no findings is not a failure** — that is what `Pass`
in the Summary block reports. Write `## Findings` with nothing under it.

### Constraints

**Every critic, both kinds, all hard.**

- `[[LOCKED … ]]` spans untouchable. Numbers, bracketed citations, and
  quoted phrases untouchable. Blockquoted specimens are exhibits.
- Quote what you judge. A finding the author cannot locate is a finding
  they cannot act on.
- Make no judgment a machine already makes. Forbidden terms, missing
  apparatus, unresolved citations, and figures never referenced from the
  prose belong to the repository's own checker, to
  [filter-tells](../filter-tells/SKILL.md), and to
  [tighten-style](../tighten-style/SKILL.md). Noticing one in passing,
  name the tool that owns it and move on.

**`suggest` critics only** — these bind replacement prose, and a verdict
critic writes none:

- No new "X, not Y" antitheses, tricolons, stacked em-dashes, or
  rhetorical-question openers — machine tells in this publication.
- The publication's banned-word list (critical, key, deliberate,
  strategic, precisely, absolutely, fundamental, breakthrough, principled,
  at the heart of, grounded, honest, structural, leverage, ecosystem, at
  scale, unlock, transformative, "real" as intensifier, "the question is").
- Deadpan register: the joke is in the flatness, never the wink.

**`verdict` critics only.** Be harsh. The critics exist to find problems,
not to validate — an author who wanted encouragement did not ask for a
six-critic review. A concern genuinely satisfied gets two sentences; spend
the words on problems.

### The draft's own rules

Where the repository states rules for the draft, the critics judge against
those rather than a generic standard. Look beside the draft for
`docs/constitutions/voice.yaml`, `docs/constitutions/argument.yaml`, and the
chapter's SRD under `docs/srd/`, walking up as voice-critic does for the
constitution. Present, they go into every critic's prompt; absent, the
critics stand alone. A chapter whose book has declared its goals is tested
against *those* goals.

## Mode B: socratic

No rewrites. One fresh-context critic reads the copy and returns a
question sheet — genuine questions, not rhetorical ones, each anchored to
a quoted sentence, in six kinds (after malkreide/socratic-method-skill):
clarification ("what does *value* refer to in this line?"), assumption
("what does this paragraph assume the reader already believes?"),
evidence ("what fact would embarrass this sentence?"), perspective ("who
is in the room when this is read aloud, and what do they hear?"),
implication ("if this is true, what does the next section owe the
reader?"), meta ("what does this sentence say that the exhibit before it
did not?"). Fifteen questions, ordered by where in the draft they bite.

The author answers in writing. The answers are the edit plan; the critic
never supplies one. Maieutic by design — maximize author output, minimize
system output — and the right mode when the author can feel a draft is
only fine but cannot yet say where.

## What the panel buys, measured

Strategy Theatre, 2026-08-22 (substack GH-181): three critics converged
independently on one diagnosis — the piece explained its receipts after
they landed — and caught two typos the gates had missed. Applying 27
suggestions plus three paragraph moves moved the prose-only Pangram figure
from 0.332 to 0.421 fraction_ai: persona suggestions are model prose, and
the detector reads them as such. The panel buys pace and phrase. Run it
for the writing, never for the number, and expect the author's own hand on
the accepted lines to be what brings the figure back.

**That cost is the `suggest` roster's.** A verdict critic proposes no
prose, so nothing it returns can reach the draft except through a sentence
the author writes. The book roster buys the same reading at none of the
detector cost, and pays for it in the author doing the writing.

## What the book roster buys, measured

`03-what-is-an-agent.md` from agentic-coding-book, 2,523 words, 2026-08-23
(GH-109). Six fresh-context critics in parallel, plus the retired
single-context `review-chapter` run recovered from git as a baseline.

Six of six reports parsed clean — `## Findings` with `Passage:` / `Finding:` /
`Fix:` on their own lines — and nothing was refused. That is the question the
run existed to answer: before it, every verdict report the tests had seen was
written by the test file, and the panel's one earlier article run had produced
three reports the parser matched nothing in (GH-107).

56 findings, 11 passages drawing two or more critics, one drawing three.
Roster order survived parallel execution into both the Diagnoses and the
single-critic sections. The convergence is signal rather than coincidence: the
deepest group is three critics who could not see each other landing on one
claim — that a workflow change is "a recompile of nothing" — which the
chapter's own printed runtime contradicts.

**Two things the run did not establish.** No critic passed, so `Pass` rendered
empty and that branch of the Summary is still unexercised on real verdicts.
And the Top 3 did not reproduce the baseline's first fix: the panel found it
(Cook and Kreischer, on the unclosed opening loop) and ranked it eleventh of
eleven, because Top fixes rank by how many critics agreed and those two sit
last in the roster. review-chapter ranked by "what most changes the chapter,
not by which critic spoke loudest"; a count is exactly the thing that rule
forbade. Nothing was lost — every baseline fix is somewhere in the sheet — but
what rises to the top is decided differently, and the difference is not
cosmetic. Tracked as GH-114.

## Calibration note on personas

Hemingway answered the choppiness question honestly ("cutting more clauses
will make it choppy; the fat is in the commentary that follows each
proof") and cut whole explaining sentences instead — the persona's value
was the verdict, not the pastiche. Levine's one factual slip ("the whole
article in one table" — there was no table) is why the author picks, and
why replacements are checked against the draft before they land.
