---
name: tighten-style
description: >-
  Tighten prose against a rule catalog: cut needless words, restore buried
  verbs and the active voice, and give paragraphs a spine. Checks sentence-level
  rules (needless words, intensifiers, hedge stacks, negative form,
  nominalizations) and paragraph-level structure (topic sentence, one topic,
  consequent order), citing rule IDs. Tightens toward the author's measured
  density, never past it. Triggers: tighten, tighten style, omit needless words,
  wordy, too wordy, cut the fat, edit for concision, copyedit, style rules,
  paragraph structure, active voice.
argument-hint: 'Path to the markdown or LaTeX file to tighten'
---

# tighten-style

Cuts what does not earn its place and gives paragraphs a spine, against the
catalog in [references/style-rules.md](./references/style-rules.md). Every
finding cites a rule ID, so the report reads as a copyedit keyed to a document
you can argue with rather than a list of opinions.

The rules are ours. They cover the ground Strunk covered and the ground he
could not — he wrote before markdown and before a machine could produce fluent
prose with nothing behind it.

## The floor

**Tightening stops at the author's own density.** Shorter is not the target.
Cutting past the author's measured function-word ratio manufactures the
clipped, aphoristic register that reads as machine-written — the failure
`filter-tells` calls overshoot. Where a `writing-voice/` corpus exists,
`match-structure` supplies that floor; without one, stop at each rule's stated
threshold.

Never touch a direct quotation, a normative requirement, a citation, or a
number.

## Procedure

```bash
python3 <tighten-style>/scripts/check_style.py <file> [--json] [--rule TS-01,TS-05]
```

1. **Run the checker.** It covers the layers a script can honestly carry:
   deterministic transforms, lexical lists, measured densities.
2. **Read for the judgment rules it cannot see** — TS-06 (related words
   together), TS-07 (emphatic end position), TS-09 (concrete over abstract),
   TS-11 (sentences in consequent order). These are most of the value on prose
   that is already lexically clean.
3. **Check each rule's exception before changing anything.** A finding is a
   prompt to look. TS-15's term-of-art exception is load-bearing: `critical
   section` and `key exchange` stay.
4. **Rewrite**, then re-run. Stop when findings stop falling, or at the density
   floor, whichever comes first.
5. **Gate the result.** Compression is where meaning goes missing, so run
   `match-voice`'s verify step: citations, numbers, terms, and meaning must
   survive.

## Where the rules are enforced

| layer | rules | licence |
|---|---|---|
| deterministic | TS-14 | rewrite it |
| lexical | TS-01, TS-03, TS-05, TS-08, TS-15 | propose; context can excuse |
| metric | TS-02, TS-04, TS-10, TS-12, TS-13, TS-16 | flag; a reader decides |
| judgment | TS-06, TS-07, TS-09, TS-11 | flag and explain; never auto-fix |

Metric rules delegate to `match-structure`, which already measures passive
density, nominalization density, list ratio, and the paragraph-schema signals
(topic overlap, cohesion, subject churn) that TS-10 is built on. Those signals
were first written to detect an AI tell; what they actually measure is whether
a paragraph has a spine, which is why they serve here too.

## Boundary with filter-tells

`filter-tells` removes what should not be there. `tighten-style` compresses
what remains and structures it. `match-voice` restores how it should sound.
Run tighten-style *before* match-voice — tightening changes sentence shapes,
and there is no point matching voice on prose about to be rewritten.

**The parallelism collision, explicitly:** `filter-tells` flags parallel
*cadence* as an AI tell; TS-12 requires parallel *form* for coordinate
content. If both fire on one passage, ask whether the ideas are genuinely
coordinate. If they are, keep the form and dismiss the tell. If they are not,
the cadence is the problem and TS-12 does not apply.

## What the checker will not tell you

It reads lists and densities. It cannot tell whether a paragraph earns its
place in the argument, whether the concrete detail is the *right* detail, or
whether a hedge is honest calibration or evasion. On prose that is already
lexically clean — which the author's own tends to be — nearly all the
remaining work is the reading pass, and the script's silence is not a verdict.

## Dependencies

`match-structure` for the metric rules and the density floor, `match-voice`'s
verify step for the gate, and the shared paragraph extractor. The checker
itself is stdlib.
