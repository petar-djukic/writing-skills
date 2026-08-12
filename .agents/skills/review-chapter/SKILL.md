---
name: review-chapter
description: >-
  Critique a book chapter draft through six critics, each testing something a
  checker cannot: whether concepts are defined precisely, whether the claims
  survive someone who has done the work, whether a working programmer can
  follow it, whether the logic holds for a skeptical outsider, whether the
  opening earns the next page, and whether the real-world grounding is told as
  a story. Produces per-critic verdicts quoting the passages they judge, then
  the top three fixes in priority order. Triggers: review chapter, critique my
  chapter, chapter review, six critics, is this chapter any good, book chapter
  feedback, clarity test, bullshit test, pedagogy test, does this chapter work.
argument-hint: 'Path to the chapter draft'
---

# review-chapter

Six critics read the draft. The first three test whether it works as a
technical book — clarity, honesty, pedagogy. The second three test whether it
works as writing — logic, hook, story. Each returns a verdict in its own
format, quoting the passage it is judging, so the author can argue with a
specific line rather than a mood.

The critics are defined in [references/critics.md](./references/critics.md).

## What this skill is not

It makes no judgment a machine can already make. Do not report forbidden
terms, missing chapter apparatus, unresolved citations, or figures that are
never referenced from the prose — those belong to the book's own checker
(`mage audit` in a repository that has one) and to
[filter-tells](../filter-tells/SKILL.md) and
[tighten-style](../tighten-style/SKILL.md) here. If you notice one in passing,
name the tool that owns it and move on.

What is left is the part that needs a reader: whether the chapter is any good.

## Process

1. **Read the draft in full** before judging any part of it. A hook verdict
   written from the first page and a pedagogy verdict written from the
   headings are both worthless.

2. **Read the book's own rules, if the repository has them.** Look for
   `docs/constitutions/voice.yaml` and `docs/constitutions/argument.yaml`
   alongside the draft, and for the chapter's SRD under `docs/srd/`. A chapter
   is judged against the register and the claim discipline its own book
   declared — not against a generic standard. Where a book has stated its
   goals for a chapter, the critics test whether the draft meets *those*.
   Absent such files, the critics stand alone.

3. **Run the critics in order.** Clarity and honesty first, hook and story
   last, so structural problems surface before stylistic ones. A critic whose
   concern is genuinely satisfied gets two sentences; spend the words on
   problems.

4. **Quote what you judge.** Every verdict cites the passage behind it. A
   finding the author cannot locate is a finding they cannot act on.

## Output

Per critic:

```
## [Critic Name] — [Test Name]

[Answer that critic's specific questions from references/critics.md, quoting
the passages at issue.]

**Verdict**: [in that critic's verdict format]
```

Then:

```
## Summary

**Pass**: [critics with no material objection]
**Needs work**: [critics that flagged something]

**Top 3 fixes** (in priority order):
1. [The fix, and where in the chapter]
2. …
3. …
```

Rank the three by what most changes the chapter, not by which critic spoke
loudest. A clarity defect that makes a later section unreadable outranks a
weak opening.

## Notes

- Be harsh. The critics exist to find problems, not to validate. An author who
  wanted encouragement did not run a six-critic review.
- The verdict is advice for the drafter. This skill does not edit the draft
  and does not gate a build.
- The critics are lenses, not impersonations: each is a way of reading, named
  for someone known for reading that way.
