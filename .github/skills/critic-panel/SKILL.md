<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->
---
name: critic-panel
description: >-
  Read-only critics for a finished draft, run before voice-critic. Four
  modes: panel — named persona critics read in parallel from fresh
  contexts and merge into one sheet with cross-critic convergence first;
  socratic — one critic interrogates the article with genuine questions
  anchored to sentences, and the author's written answers become the edit
  plan; ross — the standing cold-reader comprehension read, one
  fresh-context session agent plus two cross-family Ollama models running
  a forward-only protocol, convergence across model families the
  actionable signal. title desk — Evans and Kilgore judge
  front-matter title+subtitle pairs against the article's claim from a
  per-article digest, retitles always routed to the author gate. Two critic kinds: suggest critics return line-level
  original/replacement edits, verdict critics quote the passage and state
  the finding without rewriting it. Named rosters: article (Levine,
  Didion, Hemingway) for essays, book (Fowler, Yegge, Deitel, Miller,
  Cook, Kreischer) for chapter drafts, or any ad-hoc mix. The skill never
  applies anything; the author picks, and the picks become an
  author-directed cycle. Triggers: critic panel, read it like Levine, pace
  critic, turn of phrase, it's only fine, socratic read, interrogate the
  draft, what would make this better, review chapter, critique my chapter,
  six critics, is this chapter any good, clarity test, bullshit test,
  pedagogy test, flow test, ross read, comprehension read, cold reader
  test, can a stranger follow this, title desk, title critic, retitle,
  are my titles any good, fix the headline, does it
  read as one piece, does this chapter work.
argument-hint: 'Path to the draft, plus optionally: --roster article | book | <names>'
---

# Critic Panel (caller's review phase, before voice-critic)

A draft that has cleared every gate is clean, correct, and often only
fine — every pass was allowed to remove risk, none was hired to add. This
skill hires the adders, on a leash: critics read and propose, the author
chooses, and nothing reaches the text except through an author-directed
cycle. Its home is the caller's review phase (GH-208), not the humanize
chain: a workflow command runs it after the chain's terminal stage
(GH-57: after the terminal stage, models read but never write), ahead of
voice-critic, because its picks change what voice-critic would audit.
Rule-based application of the merged sheet is
[critic-apply](../critic-apply/SKILL.md)'s job.

```
terminal stage (inject-vernacular)
  -> critic-panel (this)          read-only: diagnosis + suggestions
  -> class sweep                  read-only: every instance of a named class
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
4. **Sweep the classes.** The sheet's `## Defect classes` section marks each
   declared instance covered or `NOT COVERED` against the numbered
   suggestions. Read the class lines first and merge the ones that name one
   pattern in different words — the script never does this, see
   [Why classes are not merged](#why-classes-are-not-merged). Then spawn one
   fresh-context agent per merged class, each given the class line, its sweep
   scope, and the full draft, returning **every** instance in that scope as
   `Original:` / `Replacement:` blocks in the suggest format. Merge those into
   the sheet with `converge.py` alongside the critic reports. Skip only when
   no class was declared, and note that the summary line says so.
5. Hand the sheet to the author. Picks by critic and number become a
   loop-workflow issue; apply them as an author-directed cycle, then
   rescan and run voice-critic on the result.

With a verdict critic in the run the sheet ends in a Summary, and its
**Most agreed** list ranks convergent passages by how many critics landed
on them, then by roster order. That is the whole of the ranking, and the
label says so: agreement is objective and `converge.py` computes it without
a model call, which is what lets an author argue with the sheet. Which fix
most changes the draft is a judgment, and the list does not make it — a
passage two critics agreed on may matter more than one three agreed on, and
the author ranks by consequence themselves. The old label, "Top fixes (in
priority order)", claimed otherwise (GH-114).

### Focus brief (optional caller input)

The caller may pass a focus list into every critic's prompt alongside
the persona brief: named checks each critic must answer explicitly in
its Diagnosis — addressed by name, answered rather than considered —
before its free read begins. The list's content belongs to the caller
(venue thresholds, the author's standing complaints, residue carried
from a prior round); this skill specifies only the mechanism, and a
report that skips a named item is incomplete the way an unparseable one
is. A run with no list is the default, not a degraded one. The
mechanism exists because a generic brief misses what the author already
knows to look for: briefed with the author's verdict, a panel converged
in one pass on three defect classes the same roster's generic read had
surfaced none of (substack GH-634/GH-636).

### A read binds only the text it read

Same rule as Mode C's re-run position: a panel read is evidence about
the bytes the critics saw, so any later cycle that adds or changes
prose invalidates it. A caller that declares a pipeline complete must
have run the panel on the final text — when to re-run is the caller's
workflow; what this mode states is that a stale read does not count as
a read of the article that ships.

### Rosters

Personas and their kinds live in
[references/personas.md](./references/personas.md). A roster is a list of
them.

| Roster | Personas | Kind |
|---|---|---|
| `article` (default) | Levine, Didion, Hemingway | `suggest` |
| `book` | Fowler, Yegge, Deitel, Miller, Cook, Kreischer | `verdict` |
| `line` | Ross | `verdict` |
| `titles` | Evans, Kilgore | `suggest` (Mode D: front-matter unit) |
| `iceberg` | Iceberg ×2 legs | `suggest`, deletions only: CoT warrant tails |
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
## Defect classes
### A
Class: <the pattern, named once — not the sentence>
Instance: <verbatim quote>
Instance: <verbatim quote>
Sweep: <the scope the author must check for more>
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
## Defect classes
### A
Class: <the pattern, named once — not the passage>
Instance: <verbatim quote>
Sweep: <the scope the author must check for more>
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
- **Name a pattern, declare it.** A diagnosis that says "every", "three
  times", "throughout", or otherwise describes a class rather than a sentence
  must carry that class in `## Defect classes`, with every instance you can
  find and the scope you did not have room to check. A class named only in
  the diagnosis is prose nothing reads; the numbered suggestions are what get
  applied, and whatever the class covers beyond them stays in the draft.
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

## Mode C: ross (the cold-reader comprehension read)

The failure this mode exists for: a model reading normally resolves a
referent forty words back, fills a skipped step, and supplies a coined
phrase's meaning from pattern, all without noticing — so every other
critic reads straight past the places a person stops. The instrument is a
protocol, not the persona: read strictly forward with one sentence of
lookback, and report every inference you had to make even when confident
of it, because your confidence is not evidence the reader followed. The
protocol text lives in `scripts/ross_read.py` and is the same for every
leg; the persona is Harold Ross from
[references/personas.md](./references/personas.md).

**The roster is model families, not personas.** One fresh-context session
agent plus two Ollama models from different families per round, because a
single model's taste is unreliable in both directions — on the run that
built this mode, one model praised the exact sentence the author called
stupid and another flagged. Only findings convergent ACROSS FAMILIES get
fixed on the author's say-so; single-model findings, the author's own
sentences, locked spans, and rule tensions go to the author gate. The
cross-family rule for prose diction does not apply: this is a read, no
model writes a word, and different families are the point.

```bash
# the reading copy for the session-agent leg (figures carry their alt text)
python3 scripts/ross_read.py article.md --copy-only

# one Ollama leg; writes <stem>.critic-ross-<model>.md (verdict format)
python3 scripts/ross_read.py article.md --model mistral-large-4:cloud
```

The reading copy injects each figure's alt text as `[CHART THE READER
SEES: ...]` — critics judge what a reader actually sees, and a bare
`[figure]` hides exactly the numbers the surrounding prose refers to. A
thinking model that spends its whole budget before the report is a hard
error naming `--num-predict`, not an empty file. Reports are verdict-kind,
so `converge.py` merges them with any other roster's.

**Position and stopping rule.** After cold-review, and again after ANY
post-pipeline hand-edit round — metric refreshes, author edits, applied
fixes — because accumulated edits are exactly where unreviewed referents
come from, and a read-only mode may run after the terminal stage as often
as the text changes. Stop when a fresh family yields no new convergent
finding on non-reserved prose; measured on the article that built this
mode, that took four author-directed fix rounds (48 findings to 7 across
six families), with every fix holding on re-read. Fixes are the author's
cycle, never this mode's: it writes reports and nothing else.

## Mode D: title desk

The unit is the front-matter title+subtitle pair, judged against the
article's claim — so the reading copy is a per-article digest, not
`prepare_copy`. For each article the digest carries: filename, the FULL
YAML `title:` and `subtitle:` values (full values, not first lines — a
wrapped multi-line subtitle read as its first line produced a convergent
"subtitle breaks off mid-sentence" phantom on the desk's first run,
2026-11-06), the headings, the first two prose paragraphs, and the closing
paragraph. A batch of articles goes in one digest; the desk judges each
title against the claim its own lede and closer make.

The two desks (Evans, Kilgore — personas in
[references/personas.md](./references/personas.md)) read the same digest in
parallel from fresh contexts, each with the publication's title rules in
the prompt (banned shapes, banned words, plain-claim title, subtitle =
mechanism + receipts). Titles the author has locked in a titles workshop
are passed in as LOCKED: the desk may flag that article's subtitle but
proposes no retitle.

Per-article report block, both desks:

```
### <filename>
Verdict: KEEP | RETITLE | SUBTITLE ONLY | LOCKED
Why: <one sentence naming the defect, or what the title does right>
Candidates: <up to 2 proposed titles, pipe-separated; omitted for KEEP/LOCKED>
Subtitle: <one sentence only if the subtitle fails as mechanism+receipts>
```

Each report ends with a worst-ten ranking. `converge.py` is not used — the
unit is the article, not a quoted passage, so convergence is read directly:
both desks RETITLE (or both flag the subtitle) is the convergent signal,
one desk alone is a single-critic finding. Either way **every retitle is
the author's gate**: the titles-workshop precedent is that retitles are
proposed on a sheet and locked by author decision, never applied by the
desk. Candidate titles are checked against the article before the sheet
ships — a candidate that states a claim the piece does not make is the
defect Evans exists to catch, not a suggestion.

## Artifact hygiene (all modes)

Every file a round writes beside the article — the reading copy, each
leg's report, the merged sheet — is a working file, not a record. The
round's durable trace is wherever its outcome landed: the fix issue, the
article's `generation:` note, or the author's verdict in conversation.
Once that trace exists, delete every sidecar in the same step, without
being asked — a published article's directory holding six `.critic-*.md`
files is the operator's mess, not the author's to notice. That includes
sheets with findings the author has not adjudicated: those findings live
in the report the operator gives in conversation and in the fix issue or
`generation:` note, never as files waiting on disk (a sheet left "for the
author gate" is a decision queue, which this publication's author has
banned). One exception: sidecars under an `experiments/` directory are
frozen measurements and stay forever. A sheet the author explicitly asks
to keep on disk is kept by that instruction, not by default. Consuming
repos gitignore `*.critic-*.md`, so the deletion is `rm`, never a commit.

## Why classes are not merged

`converge.py` lists classes as declared and never merges them, which is a
choice and not an omission. Two critics naming one pattern write two
paraphrases, not one quote, so the quote matcher does not apply. Measured on
real class lines, content-word overlap gives 0.29 to a matching pair
("paragraph opens by labelling its own content" against "a paragraph opener
that labels the paragraph's content") and 0.29 to a non-matching one ("a
sentence that announces its paragraph" against "a paragraph closer that
restates its first sentence"). No threshold separates those, and a false
merge hides a class — the exact failure the section exists to prevent.

So the script computes only what is objective: does this instance match a
numbered suggestion, yes or no. Recognising that two class lines are one
class is a semantic judgment and belongs to the sweep, which has a model in
it. The script stays deterministic so an author can argue with it.

## What the sweep buys, measured

substack GH-235, 2026-08-23. The article roster ran on a how-to draft and
Didion's diagnosis read: "Every opening paragraph closes by restating its
first sentence... the reader is told three times that the agent must be
told." Hemingway, independently, cut `They point in different directions.`
because "the next sentence shows the two directions; this one announces
them." One class, named twice: **a sentence that announces its paragraph
instead of being it.**

Their numbered suggestions quoted the closing halves. The author said "use
all of it", every suggestion was applied, and the class survived in the two
paragraph openers nobody had quoted — one of them the article's first
sentence. The author found them by reading, which is what the panel is meant
to save. Under this section those two render as `NOT COVERED` under the class
that named them, and the summary line counts them.

`filter-tells` does not cover this class and points the other way: its
`topic-sentence-weak` check flags paragraphs whose opener has *low* overlap
with the body, so a sentence that labels its own paragraph scores well.
Critics defer to the machine on machine-owned judgments (see Constraints), so
nothing else in the pipeline was looking.

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
And the Summary's top three did not reproduce the baseline's first fix: the
panel found it (Cook and Kreischer, on the unclosed opening loop) and ranked
it eleventh of eleven, because the list ranks by how many critics agreed and
those two sit last in the roster. review-chapter ranked by "what most changes
the chapter, not by which critic spoke loudest"; a count is exactly the thing
that rule forbade. Nothing was lost — every baseline fix is somewhere in the
sheet — but what rises to the top is decided differently, and the difference
is not cosmetic. GH-114 settled it by naming the axis rather than changing
it: the list is **Most agreed**, the sheet says agreement is not consequence,
and ranking by consequence stays with the author. Weighting by critic kind,
or letting a model rank the top three, would compose with that relabel and
remain open.

## Calibration note on personas

Hemingway answered the choppiness question honestly ("cutting more clauses
will make it choppy; the fat is in the commentary that follows each
proof") and cut whole explaining sentences instead — the persona's value
was the verdict, not the pastiche. Levine's one factual slip ("the whole
article in one table" — there was no table) is why the author picks, and
why replacements are checked against the draft before they land.
