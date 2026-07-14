# Failure Taxonomy (by linguistic level)

Every detector, prompt, and pattern class in this skill, placed at its
linguistic level — so gaps are visible by inspection instead of discovered by
the next reviewer. The historical trend runs upward: catches began lexical and
have climbed to discourse level; the pragmatic row is where the next wrinkles
will surface. **Classification rule: when a new tell is found, place it in
this table FIRST, then write its detector** (extend of banned-patterns.md
"Updating This List") — the cell tells you which instrument fits (script for
surface, prompt for meaning).

Instruments: `lex` = detect-lexical.sh, `str` = detect-structural.py,
`abs` = abstract-check.py, `P<n>` = perplexity-prompts.md prompt.

## Lexical (words and fixed phrases)

| Tell | Instrument | Reference |
|---|---|---|
| Chat-turn residue ("want me to…") | lex (Tier 0, tail-weighted) | banned-patterns: Tier 0 |
| Banned words (tiers 1–3) | lex | banned-patterns: Tiers 1–3 |
| Compound AI phrases, substack-rules phrases | lex | banned-patterns: Compound |
| Marketing/hype vocabulary | lex (venue-jargon) | banned-patterns: Marketing |
| Ornate register (density-scored) | lex | banned-patterns: Ornate Register |
| Editorializing adjectives ("sobering") | lex (candidates) | banned-patterns: Compressed Conversation |
| Technical-writing tells | lex | banned-patterns: Technical Tells |
| Vocabulary predictability | P1 | — |

## Syntactic (sentence and clause shape)

| Tell | Instrument | Reference |
|---|---|---|
| Low burstiness / uniform sentence length | str (`sentence_length_std`, two-sided) | — |
| Opening diversity / "The"-dominance / first-word class | str | opening-diversity-fixes |
| Opening parallelism runs | str (`detect_parallelism`) | — |
| Frame parallelism (varied surface, same frame) | str (`detect_frame_parallelism`) | — |
| Tail-echo (mirrored endings) | str (`detect_tail_echo`) | — |
| Dash density, question patterns, tricolons | str | — |
| Uniform paragraph lengths | str | — |

## Rhetorical (figures and performance)

| Tell | Instrument | Reference |
|---|---|---|
| Antithesis / negation-flip pairs | str regex + P6 (zero tolerance) | banned-patterns; P6 |
| Rhetorical set pieces (allegory sweep, anadiplosis, imperative closer…) | P6b | banned-patterns: Set Pieces |
| Punch clustering / epigram-closing paragraphs | str (`punch_*`) + P7 | rewrite-instructions §3b |
| Overshoot / uniform maximal polish ("LinkedIn voice") | str (two-sided metrics) + P0, P7 | SKILL: overshoot warnings |
| Word salad (jargon runs without joints) | str (`salad_*`) + P7 | — |
| Repeated formulae (coined 4-grams re-emitted) | str (`repeated_formulae`) | — |
| Over-compression / "too sleek" (texture removed) | rewrite §3b + Step 6 check | rewrite-instructions §3b |
| Cross-sentence surprise (maximum-likelihood continuation) | P3 | — |

## Discourse (paragraphs and document organization)

| Tell | Instrument | Reference |
|---|---|---|
| CoT leakage / bridge sentences | lex candidates + P4 | cot-leakage-patterns |
| Stage-setting frames ("One rule organizes it:") | lex (narrative-pivot candidates) | banned-patterns: Compressed Conversation |
| Recap-ballast paragraphs | P3 Part B | — |
| Paragraph schema / MEAL violations | str proxies + P9 | paragraph-schema |
| Abstract/introduction opener duplication | str (`opener_duplication`) | — |
| Abstract structure, number traceability, containedness | abs + P10/P11 | abstract-standards |
| Compressed-conversation empty phrases (coinage, metaphor-for-mechanism) | str (`coinage_candidates`) + lex + P8b | banned-patterns: Compressed Conversation |
| Definedness, circularity, quantity mismatch | P8 | — |

## Pragmatic (author–reader relationship) — the mostly-empty row

Covered today: quantity mismatch (P8c) is a narrow slice of evidence handling;
voice distance (`--voice-profile`, GH-121) is a coarse cross-level catch-all
that flags *unnamed* deviations at any level, including this one.

Known-empty territory. Candidates enumerated per the no-speculation rule —
**none has a documented corpus example yet, so none gets a detector**; the
first observed instance of each should be added here with its example, then
instrumented (almost certainly as a Step 3 prompt, not a script):

| Candidate tell | What it would look like | Status |
|---|---|---|
| Stance drift | the document's position on a claim shifts between sections without acknowledgment | speculative |
| Audience wobble | register alternates between expert-reader and lay-reader assumptions | speculative |
| Uniform certainty | no claim hedged more than any other; confidence is flat across strong and weak evidence | speculative |
| Uniform explanation depth | the obvious explained as thoroughly as the hard step (no reader model) | speculative |
| Limitations-triviality | the limitations section concedes only trivia, never a load-bearing weakness | speculative |
| Evidence-shape mismatch (general) | qualitative claim backed by quantitative citation or vice versa, beyond P8c's quantity case | speculative |

When one of these is observed in the wild: record the example in
banned-patterns.md, move the row out of this list, and extend P5 or add a
Prompt 12 with the forced-enumeration discipline.
