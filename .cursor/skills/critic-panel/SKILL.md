<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: critic-panel
description: >-
  Read-only critics for a finished draft, run before voice-critic. Two
  modes: panel — named persona critics (Levine for pace through
  escalation, Didion for turn of phrase, Hemingway for pace by omission)
  read in parallel and return line-level original/replacement suggestions
  merged into one sheet with cross-critic convergence first; socratic — no
  rewrites, one critic interrogates the article with genuine questions
  anchored to sentences, and the author's written answers become the edit
  plan. The skill never applies anything; the author picks, and the picks
  become an author-directed cycle. Triggers: critic panel, read it like
  Levine, pace critic, turn of phrase, it's only fine, socratic read,
  interrogate the draft, what would make this better.
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
2. Spawn one fresh-context agent per critic, in parallel, each with the
   persona brief below plus the shared constraints, writing its report in
   the fixed format to `<stem>.critic-<name>.md`.
3. Merge: `scripts/converge.py <reports…> --out <stem>.critic-sheet.md` —
   suggestions targeting the same sentence across critics are listed
   first; agreement between independent critics is the headline signal.
4. Hand the sheet to the author. Picks by critic and number become a
   loop-workflow issue; apply them as an author-directed cycle, then
   rescan and run voice-critic on the result.

### Persona briefs (default panel)

- **Levine** (Matt Levine, Money Stuff): deadpan corporate absurdity, pace
  through escalation, the parenthetical that lands the joke, receipt-first
  irony — the fact before the quip, never after. Targets: section openers,
  paragraph closers, transitions between exhibits.
- **Didion** (Joan Didion): cool detachment, the sentence whose rhythm does
  the arguing, the concrete object replacing an abstraction, the closer
  that withholds. Targets: abstractions that could become images; closers
  that trail off; one place a scene could replace a page of explanation.
- **Hemingway** (Ernest Hemingway): omission, the declarative, the
  iceberg. Told explicitly that the draft has already been cut to flat
  declaratives and to say so if more cutting would chop rather than
  quicken. Targets: sentences that explain what the previous sentence
  already showed; the one paragraph the piece is faster without.

Swap or add personas by brief; the skill is the shape, not the names.

### Fixed report format (what converge.py parses)

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

### Shared constraints (sent to every critic, all hard)

- `[[LOCKED … ]]` spans untouchable. Numbers, bracketed citations, and
  quoted phrases untouchable. Blockquoted specimens are exhibits.
- No new "X, not Y" antitheses, tricolons, stacked em-dashes, or
  rhetorical-question openers — machine tells in this publication.
- The publication's banned-word list (critical, key, deliberate,
  strategic, precisely, absolutely, fundamental, breakthrough, principled,
  at the heart of, grounded, honest, structural, leverage, ecosystem, at
  scale, unlock, transformative, "real" as intensifier, "the question is").
- Deadpan register: the joke is in the flatness, never the wink.

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

## Calibration note on personas

Hemingway answered the choppiness question honestly ("cutting more clauses
will make it choppy; the fat is in the commentary that follows each
proof") and cut whole explaining sentences instead — the persona's value
was the verdict, not the pastiche. Levine's one factual slip ("the whole
article in one table" — there was no table) is why the author picks, and
why replacements are checked against the draft before they land.
