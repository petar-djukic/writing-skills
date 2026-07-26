# Prompt catalog (Step 3)

Which semantic prompt does what, and when each becomes mandatory. The prompts
themselves live in [perplexity-prompts.md](./perplexity-prompts.md); this is
the index to them, kept out of SKILL.md because it loads on every invocation
and is needed only once Step 3 is actually running.

1. **Vocabulary Predictability** (Prompt 1) — Score each sentence 1-5 for how "obvious" the word choices are
2. **Burstiness Assessment** (Prompt 2) — Confirm structural findings with semantic judgment
3. **Cross-Sentence Surprise** (Prompt 3) — Detect absence of genuine thought progression
4. **CoT Leakage Detection** (Prompt 4) — Find reasoning scaffolding that regex missed, including bridge sentences at paragraph boundaries. For each candidate, Prompt 4 applies the removal test: delete the sentence, check whether the paragraph loses information. True leaks are flagged for deletion; CoT-style wording on real content is flagged for rewording.
5. **Overshoot Assessment** (Prompt 7) — mandatory when the document has prior filter-tells history, when Prompt 0 flags register, or when the structural verdict is `suspicious-overshoot`. Seeded with the script's performance/punch/salad/formulae outputs; applies the removal test to punch candidates and the second-read test to salad candidates.
6. **Antithesis / Negation-Flip Enumeration** (Prompt 6) — run with **Prompt 6b** (rhetorical set pieces).
7. **Definedness and Circularity** (Prompt 8) — mandatory for publication verdicts. Enumerates undefined substantive terms (marketing jargon like "frontier models" is human register — the cadence detectors cannot see it), circular opening claims (predicate restating premise), and quantity mismatches ("the costs compound" supported only by error-rate data). Runs on the abstract and section openers — but widens to the whole document and becomes mandatory for a working or specification document another session will execute.
7b. **Empty-Phrase Enumeration** (Prompt 8b) — the compressed-conversation class: coined bigrams used as if defined, metaphors substituting for a mechanism, editorializing adjectives, slogans standing in for claims. Seed with the structural script's `coinage_candidates` and the lexical `editorializing`, `reader-directive` (invented discourse / reader-mind narration), and `meta-narration` (self-referential layout clauses) hits, then apply the cold-reader test. Documented in banned-patterns.md. Note: these classes live in short units (leads, goal statements, captions) that fall under detect-structural.py's too-short floor, so lexical owns them — a `too-short` structural verdict is not a clean bill.
8. **Paragraph Schema and Claim Coherence** (Prompt 9) — MEAL classification per paragraph, adjudication of the structural script's low-topic candidates, and the nonsense check (can a cold reader evaluate each opening claim?). Grounded in references/paragraph-schema.md; composes with Prompt 8 rather than duplicating circularity. — Enumerate every adjacent-sentence antithesis pair and rule each ANCHOR or REFLEX. Catches the purely semantic reversals the `detect_antithesis` regex cannot. Honor the caller's tolerance: under zero tolerance, rewrite every pair.

## Order

Run Prompts 1-3 in parallel. Run Prompt 4 after reviewing lexical results — it
needs that context. Run Prompt 6 after the structural scan, which it extends.
Finish with Prompt 5 (Overall Assessment) over all collected evidence, for the
integrated judgment and the rewrite priority list.
