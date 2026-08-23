<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# The Relation Set and the Cut Order

The labels `annotate` may use, and the order `rank` deletes in. Definitions
follow Mann & Thompson's Rhetorical Structure Theory as published at
[sfu.ca/rst](https://www.sfu.ca/rst/01intro/definitions.html), restricted to
the paragraph grain and to the relations that earn their place in an argued
article.

Two things are being recorded per paragraph, and only two: **what it does**
(the relation) and **what it does it for** (the target). Together they are the
justification, which is why there is no separate justification field.

## Nuclearity, and why deletion is the test

RST joins spans in pairs. One span is the **nucleus** — what the author's
purpose depends on. The other is the **satellite** — what supports it. The
definitional test is deletion:

> Remove a satellite and the text still makes its point. Remove a nucleus and
> it does not.

That test is the whole skill. Everything below is bookkeeping on top of it.

**Depth** is the number of hops from a paragraph to its section's nucleus. A
satellite of a satellite is at depth 2, and it is further from the point than
anything at depth 1. Marcu (1997) found that ordering units by nuclearity
depth matches what human summarizers keep, which is the same ordering read
backwards: deepest goes first.

Depth is computed from the `-> n` targets, never written down. A stored depth
is a second source of truth, and `check --renumber` would have to keep it
honest after every edit.

## Presentational relations

The satellite acts on the reader's belief or readiness, not on the subject
matter.

| Relation | Definition | Effect on the reader |
|---|---|---|
| `evidence` | The satellite gives the reader grounds to believe the nucleus. | Belief in the nucleus rises. |
| `justify` | The satellite establishes the author's right to say the nucleus. | The reader accepts the author's standing to make the claim. |
| `concession` | The author admits something that appears to conflict with the nucleus. | Apparent incompatibility resolved; the nucleus survives it. |
| `antithesis` | Something is put in opposition to the nucleus, and rejected. | Positive regard for the nucleus rises by contrast. |
| `motivation` | The satellite makes the reader want to act on the nucleus. | Desire to act increases. |
| `preparation` | The satellite readies the reader for what follows. | The nucleus lands more easily when it arrives. |
| `background` | The satellite supplies what the reader must know first. | The nucleus becomes comprehensible. |
| `restatement` | The nucleus said again, in different words, at comparable bulk. | None the nucleus did not already produce. |
| `summary` | The nucleus said again, shorter. | None the nucleus did not already produce. |

## Subject-matter relations

The satellite says something about the nucleus's content; the reader is
expected to recognise the relation itself.

| Relation | Definition | Effect on the reader |
|---|---|---|
| `elaboration` | More detail about the nucleus — a member, a part, an instance, an attribute. | The reader knows the nucleus in more detail. |
| `interpretation` | The nucleus placed in a frame the nucleus itself does not supply. | The reader sees what the nucleus means. |
| `evaluation` | The author's assessment of the nucleus. | The reader learns the author's degree of positive regard. |
| `circumstance` | The frame — time, place, setting — in which the nucleus holds. | The reader can situate the nucleus. |
| `purpose` | The nucleus is undertaken in order to achieve the satellite. | The reader knows what the activity is for. |
| `solutionhood` | The nucleus answers a problem the satellite states. | The reader recognises the nucleus as the answer. |

## Multinuclear relations

No satellite: the spans are equals, and deleting any one of them removes
content nothing else carries.

| Relation | Definition |
|---|---|
| `contrast` | Two spans held against each other; neither is subordinate. |
| `sequence` | Spans in a succession that the order itself encodes. |
| `list` | Spans as comparable items, order not load-bearing. |
| `joint` | **No rhetorical relation holds.** |

`joint` is the orphan flag, and it comes free with the relation set. A
paragraph the labeller can attach to nothing is a paragraph the argument does
not reach, so `rank` lists it first among deletion candidates. It is the
cheapest finding the skill produces and often the most useful.

## Two labels that are not RST relations

| Label | Meaning |
|---|---|
| `nucleus` | This paragraph is what the section depends on. Exactly one per section. |
| `split` | The labeller could not state one function for this paragraph, because it does more than one thing. Not a deletion candidate — a rewrite candidate. |

`split` is a confession, and it is worth more than a bad label. A paragraph
carrying three functions is the monster paragraph an author cannot cut because
part of it is load-bearing; naming it is the first step to separating the
parts.

## On a heading

The same grammar labels a section's relation to the article's `thesis:` line.
A section marked `restatement` against the thesis is a section that repeats
one that came earlier, and it is a whole-section deletion candidate — the unit
the existing instruments cannot see.

## The cut order

**This is the skill's one judgment call, and it is stated here so it can be
argued with.** Marcu ranks by depth alone. Depth answers *how far from the
point* a paragraph sits; it does not answer *which of two paragraphs at the
same depth goes first*. The order below answers that, and it is derived from
the relation definitions above rather than measured.

Within a depth, cut in this order:

`joint` is ranked outside the depth ordering, ahead of it. Every other
relation is a satellite supporting something, and depth measures how far that
support sits from the point; `joint` says no relation holds at all. A
paragraph the argument never reaches beats a distant one that at least
supports something.

| Rank | Relations | Why here |
|---|---|---|
| 1 | `joint` | No relation holds. Sorted ahead of depth, not within it. |
| 2 | `restatement`, `summary` | Defined as adding nothing the nucleus lacks. Deleting one removes no content. |
| 3 | `elaboration` | More detail. The nucleus stands without it; the reader knows less. |
| 4 | `evaluation`, `interpretation` | The author's reading of a point already made. |
| 5 | `background`, `preparation`, `circumstance` | Orient the reader. Their cost depends entirely on who is reading. |
| 6 | `purpose`, `solutionhood` | Say what the nucleus is for. |
| 7 | `motivation`, `justify` | Move the reader to act, or establish standing. |
| 8 | `evidence`, `concession`, `antithesis` | Change what the reader believes. Cutting these is cutting the argument. |
| — | `contrast`, `sequence`, `list` | Multinuclear: each span carries content of its own, so they are not ranked as satellites. Cut one and something goes missing — but see **Runs** below, where the whole group goes at once. |
| — | `nucleus` | Never a deletion candidate. Cutting it is cutting the section. |

Two consequences worth stating plainly.

**Ranks 1 and 2 are close to mechanical.** A `restatement` at depth 3 is text
that repeats a point the reader has already had, two hops from anything the
section depends on. Authors rarely defend those once they are listed.

**Rank 8 is where the skill stops being useful and the author takes over.** A
sheet that recommends cutting evidence is a sheet describing an article with
nothing left to trim. The ranking is a reading order for a decision; the
skill never cuts anything.

## Runs

The exclusion above is right about one span and wrong about a passage, because
a multinuclear label is doing two jobs at once:

- **these spans are peers inside a structure the argument needs** — cut one and
  the remaining spans no longer make sense;
- **these paragraphs form a run** — a stay/leave/decide passage, a list of
  three examples, a pair of contrasted cases.

The second is exactly the shape an author cuts wholesale, and the exclusion hid
it. GH-88's acceptance run found the case: a five-paragraph run whose four
satellites came back at ranks 2, 6, 12 and 22 of 57, while the head that
governed all four was labelled `sequence` and left the sheet entirely. The
author was being shown the pieces of a passage and never the passage.

A **run** is one or more sibling paragraphs sharing a multinuclear relation and
the same target — the peer spans — plus every paragraph that transitively
targets one of them. Grouping follows the `-> n` targets rather than adjacency,
because paragraph numbers stop being contiguous the first time an
author-directed cycle lands.

`rank` lists a run as a single row when two conditions hold:

1. **Every member is otherwise deletable.** A `nucleus` cannot appear inside a
   run — it carries no target, so nothing attaches it — but a `split` can, and
   one inside the group means the passage is not a clean whole-run cut.
2. **At least one member carries a cut rank.** The run is ranked by its best
   member under the ordering above, so a group of bare peers with no satellites
   gives nothing to rank it by.

Members keep their individual rows. Both grains are findings: the run row says
the passage can go as one decision, the member row says which paragraph in it
is weakest, and the acceptance case needed both — the run was worth a second
look precisely because one member had ranked second of fifty-seven alone.

Anything multinuclear that no qualifying run accounts for is **named in the
sheet** rather than dropped, on a line under the candidates table. The original
failure was not the exclusion; it was the silence. A paragraph the ranking
declines to rank is a decision the author is entitled to see.

## Deliberate omissions

- **No new role vocabulary.** RST's set is closed, published, and defined by
  its effect on the reader. A house vocabulary would have to earn the same
  precision from scratch.
- **Nothing from Minto's pyramid.** It is RST restricted to question/answer,
  and `solutionhood` already carries that case.
- **No confidence score.** A labeller that is unsure emits `split` or `joint`,
  and both give the author something to do. A number between 0 and 1 leaves
  them holding a number.

## Sources

- Mann, W. C. and Thompson, S. A. (1988). *Rhetorical Structure Theory: Toward
  a functional theory of text organization.* Text 8(3), 243–281.
- RST relation definitions, Simon Fraser University:
  https://www.sfu.ca/rst/01intro/definitions.html
- Marcu, D. (1997). *From discourse structures to text summaries.*
  Intelligent Scalable Text Summarization, 82–88, ACL.
  https://aclanthology.org/W97-0713/
