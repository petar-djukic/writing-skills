# The Style Rules

Our own catalog. It covers the ground Strunk covered and the ground he could
not: he wrote before the typewriter gave way to the screen, before markdown,
and before a machine could produce fluent prose with nothing behind it.

Every rule has a stable ID. Findings cite the ID, so a report reads as a
copyedit keyed to this file rather than a list of opinions.

Each rule states how it is **detected**, and that determines how far the skill
may go on its own:

| layer | meaning | licence |
|---|---|---|
| `deterministic` | a mechanical transform with one right answer | rewrite it |
| `lexical` | a word or phrase on a list | propose the swap; context can excuse it |
| `metric` | a measured distribution over the document | flag; a human or the semantic pass decides |
| `judgment` | only a reader can tell | flag and explain; never auto-fix |

## The floor, before any rule

**Tightening has a floor, and it is the author's own density.** The target is
never "as short as possible" — that direction manufactures the clipped,
aphoristic register that reads as machine-written. Where a `writing-voice/`
corpus exists, `match-structure` supplies the author's measured function-word
ratio and sentence-length distribution, and tightening stops there. Absent a
corpus, stop at the rule's stated threshold and no further.

Nothing in this catalog licenses touching a direct quotation, a normative
requirement ("the system shall…"), a citation, or a number.

---

## Sentence-level rules

### TS-01 — Omit needless words
**Detection:** lexical + metric.
Every word should carry weight. The usual offenders are phrases that announce
rather than say: *the fact that*, *in order to*, *it should be noted that*,
*there is/are … that*, *the question as to whether*, *owing to the fact that*.
**Fix:** delete or contract — *the fact that he failed* → *his failure*.
**Exception:** in normative text, *shall be required to* may carry contractual
weight that *must* does not.

### TS-02 — Prefer the active voice
**Detection:** metric (passive-density per 500 words, already measured).
Passive prose hides the actor, and hidden actors are how a claim avoids
ownership. *Errors were made* names nobody.
**Fix:** name the actor.
**Exception:** the actor is genuinely unknown, irrelevant, or the object is the
topic of the paragraph — *the samples were stored at 4 °C* is correct.

### TS-03 — Put statements in positive form
**Detection:** lexical.
*Did not remember* → *forgot*. *Not honest* → *dishonest*. *Not important* →
*trifling*. Negation asks the reader to compute a complement.
**Fix:** name the thing itself.
**Exception:** the negative is the point — *this is not a proof* denies
something the reader may assume.

### TS-04 — Use verbs, not nominalizations
**Detection:** metric (nominalization density, already measured).
*Performed an analysis of* → *analyzed*. *Made a decision* → *decided*. Chains
of *-tion*, *-ment*, *-ance* nouns bury every action in the sentence.
**Fix:** restore the verb.
**Exception:** the nominalization is the term of art — *classification* is a
thing in machine learning, not a buried verb.

### TS-05 — Delete intensifiers that intensify nothing
**Detection:** lexical.
*Very*, *really*, *quite*, *rather*, *extremely*, *significantly* (where no
significance was computed), *incredibly*, *truly*. They inflate without
measuring.
**Fix:** delete, or replace the weak word they prop up with a strong one.
**Exception:** *significant* with a statistic behind it.

### TS-06 — Keep related words together
**Detection:** judgment.
The subject belongs near its verb, the modifier near what it modifies. A
qualifier stranded from its target attaches to the wrong thing and the reader
back-tracks.
**Fix:** move the modifier.

### TS-07 — End the sentence on the emphatic word
**Detection:** judgment.
The last position carries weight; spending it on a trailing qualifier
(*…, in general*, *…, as noted above*) wastes it.
**Fix:** move the qualifier earlier or cut it.

### TS-08 — Do not hedge in stacks
**Detection:** lexical + metric.
One hedge is honest calibration. Three in a sentence — *may perhaps somewhat
suggest* — is an author declining to make a claim while appearing to.
**Fix:** keep the single hedge that carries the real uncertainty; cut the rest.
**Exception:** a genuinely layered claim ("we estimate, under assumptions that
may not hold, …") — but say which assumptions.

### TS-09 — Prefer the concrete to the abstract
**Detection:** judgment.
*A significant improvement in performance characteristics* says nothing;
*latency fell from 40 ms to 12 ms* says everything. Abstraction is where prose
goes to avoid being checkable.
**Fix:** substitute the specific thing, number, or name.

---

## Paragraph-level rules

### TS-10 — Make the paragraph the unit of composition
**Detection:** metric (topic overlap, cohesion, subject churn — measured by
`match-structure`).
One topic per paragraph, announced early enough that a reader skimming first
sentences gets the argument. A paragraph whose opening sentence shares little
with its body starts mid-thought.
**Fix:** write the topic sentence, or split the paragraph at the point where
the subject changes.
**Exception:** transitional and narrative paragraphs legitimately open
mid-motion. Convention, not law — the semantic pass adjudicates.

### TS-11 — Order sentences by consequence
**Detection:** judgment.
Each sentence should follow from the last. Where the order could be shuffled
without loss, the paragraph is a list wearing prose clothing.
**Fix:** restore the logical chain, or make it an actual list.

### TS-12 — Parallel form for parallel content
**Detection:** metric + judgment.
Coordinate ideas take coordinate form: *she likes running, swimming, and
cycling*, not *…and to cycle*.
**Boundary — read this before acting.** `filter-tells` flags *parallel cadence*
as an AI tell; this rule *requires* parallel form. They are not in conflict.
Parallelism earns its place when the content is genuinely coordinate; it is a
tell when the rhythm is imposed on content that is not. If both skills fire on
one passage, the question is whether the ideas are actually parallel — if they
are, keep the form and dismiss the tell; if they are not, the cadence is the
problem and this rule does not apply.

### TS-13 — Prose or list, not prose shaped like a list
**Detection:** metric (list ratio).
Bullets are for genuinely enumerable items. Prose broken into bullets to look
organized loses the connective tissue that carried the argument.
**Fix:** restore the prose, or commit to the list and cut the pseudo-sentences.

---

## Document-level rules

### TS-14 — Define an abbreviation once per document section
**Detection:** deterministic.
First use in a section spells it out. A reader who lands mid-document should
not have to search backwards.

### TS-15 — Do not use words that only signal importance
**Detection:** lexical.
*Critical*, *key*, *fundamental*, *strategic*, *breakthrough*, *at the heart
of*, *deliberate*, *principled*, *robust*, *seamless*, *leverage* (as a verb),
*delve*, *ripple*. They assert significance instead of demonstrating it, and
they are the most reliable single marker of machine-drafted prose.
**Fix:** state what makes the thing matter, or cut the adjective.
**Exception:** the term of art — *critical section*, *critical path*, *key* in
cryptography, *robust* in statistics. This exception is load-bearing; check it
before every change.

### TS-16 — One claim, stated once
**Detection:** metric (repeated formulae) + judgment.
Restating a claim in new words does not strengthen it. Prose that opens by
announcing what it will say, says it, then summarizes what it said, has spent
three passes on one idea.
**Fix:** keep the strongest statement; cut the announcement and the recap.

---

## Provenance

The rules descend from a long tradition of style advice — Strunk's *Elements
of Style* (1918) most obviously, and the general run of technical-writing
guidance since. They are written here in our own words and against our own
evidence: TS-15's list absorbs the forbidden terms from this repository's
documentation standards and the technical-register catalog from
`patent-disclosure`; the density floor and the TS-12 boundary come from what
`filter-tells` learned about overshoot, which is that prose corrected only
away from tells acquires a new set.
