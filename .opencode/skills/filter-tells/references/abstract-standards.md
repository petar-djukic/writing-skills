# Abstract standards

The single in-repo citation target for abstract mode. Sources: Simon Peyton
Jones, "How to write a great research paper"; Kent Beck's four-sentence
abstract; Nature's annotated abstract template; Justin Zobel, "Writing for
Computer Science" (self-containedness).

## The four moves

| Move | Content | Typical source in the body |
|---|---|---|
| 1. Problem | What problem, why the reader should care — in terms a non-specialist in the subfield can evaluate | introduction ¶1 |
| 2. Gap | What existing work does not do; why the problem is open | introduction / related work |
| 3. Approach + results | What we did and what we found, with the paper's headline numbers | methodology + results, numbers verbatim |
| 4. Implication | What follows if the reader believes move 3 | conclusion |

Conforming abstracts make the four moves in order. Defects: a missing move
(most often gap or implication), out-of-order moves (results before the
problem), and sentences assignable to no move (throat-clearing, scope
disclaimers, coinage definitions that belong in the body).

## Self-containedness (Zobel)

The abstract is read without the paper — often instead of it. It must not
contain:

- citations (the abstract cannot lean on sources the reader has not seen)
- section, figure, or table references
- unglossed coinages: any term the paper invented must be glossed inline
  or replaced with plain language
- numbers without in-abstract referents: "74%" is meaningless unless the
  abstract itself says 74% of what, measured how

## Written-last principle

The abstract derives from the current body text — moves 1-2 compressed from
the introduction, move 3's numbers pulled verbatim from results, move 4 from
the conclusion. When an existing abstract's phrasing failed the checks, the
rewrite must not inherit that phrasing: rebuild from the body, do not polish
the failure.

## Verification

Every number and claim in a rewritten abstract must appear in the body
(`scripts/abstract-check.py` enforces the number half mechanically; the
claim half is the model's traceability pass). A rewrite that introduces a
new claim is wrong even if the claim is true.
