# Perplexity Proxy Prompts

Since Claude does not expose token-level log probabilities, we use Opus as a perplexity judge.
These prompts are used in Pass 3 of the detection pipeline.

## Prompt 0: Cold Read (run BEFORE the scripts)

Run this before any script output exists, so the judgment is not anchored by
metrics or verdict labels. It is the only pass that reads the document the
way its audience will.

```
Read the following document once, as a plain reader — a tired colleague
seeing it for the first time. Do not count anything. Answer:

1. FOLLOWABLE: Could you follow the argument on a single pass? Where did
   you have to re-read?
2. REGISTER: Is the voice appropriate for the stated venue, or does it
   perform — mannered, oracular, epigrammatic, compressed past clarity?
3. HARDEST_SENTENCES: Quote the three hardest-to-parse sentences.
4. COLD_VERDICT: one of "reads naturally", "polished but readable",
   "mannered — the style calls attention to itself", "opaque — meaning is
   lost to compression".

---
TEXT:
{text}
```

## Prompt 1: Vocabulary Predictability Score

Use this to score how "expected" the word choices are at the sentence level.

```
You are an AI writing detector. Your task is to score each sentence in the following text on a scale of 1-5 for VOCABULARY PREDICTABILITY:

1 = Surprising, idiosyncratic word choices that reflect personal style
2 = Somewhat distinctive, mixes common and uncommon phrasing
3 = Standard academic/technical writing, neither distinctive nor generic
4 = Highly predictable word choices, the "obvious" way to phrase each idea
5 = Maximum likelihood output — exactly what a language model would generate token-by-token

Score each sentence. Focus on:
- Whether word choices feel selected from a narrow beam (AI) or from broader vocabulary (human)
- Whether modifiers are the "default" ones (comprehensive, robust, significant) or specific
- Whether transitions are mechanical (moreover, furthermore, additionally) or organic

Output format (one per line):
S<number>: <score> | <brief reason>

Then provide:
OVERALL_SCORE: <weighted average>
HIGH_PREDICTABILITY_SENTENCES: <list of sentence numbers scoring 4+>
LOW_SCORE_CAUTION: if the overall score is below 2.5, state whether the surprising vocabulary is bursty (occasional, human) or uniform (every sentence surprising — which is itself a machine signature; see Prompt 7).

---
TEXT TO ANALYZE:
{text}
```

## Prompt 2: Burstiness Assessment

Use this when the structural script flags low sentence-length variance, for semantic confirmation.

```
You are analyzing text for BURSTINESS — the natural variation in complexity that characterizes human writing.

Human writers alternate between:
- Long, complex sentences with embedded clauses
- Short punchy statements
- Medium explanatory sentences
- Occasional fragments for emphasis

AI writing tends toward uniform medium-length sentences with consistent clause depth.

Analyze the following text and report:

1. RHYTHM SCORE (1-5):
   1 = Highly varied, clear human rhythm
   5 = Monotonously uniform, typical AI output

2. INFORMATION DENSITY UNIFORMITY (1-5):
   1 = Ideas cluster naturally (dense passages then breather sentences)
   5 = Information spread unnaturally evenly across all sentences

3. TRANSITION PREDICTABILITY (1-5):
   1 = Surprising connections, associative thinking
   5 = Each sentence follows the "obvious next" sentence

4. Identify specific passages (by sentence number) that feel machine-generated and explain why.

---
TEXT TO ANALYZE:
{text}
```

## Prompt 3: Cross-Sentence Surprise

Use this to detect the absence of genuine thought progression.

```
You are measuring CROSS-SENTENCE SURPRISE in a text. For each consecutive pair of sentences, assess how surprising the second sentence is given the first.

Human writing characteristics:
- Occasional topic jumps within a paragraph (associative thinking)
- Digressions that add personality
- Connections that aren't immediately obvious
- Varying levels of abstraction (concrete → abstract → concrete)

AI writing characteristics:
- Each sentence follows the "most likely next sentence"
- Information unfolds in the most orderly possible way
- No digressions or personality
- Consistent level of abstraction throughout

For each transition between sentences, score 1-5:
1 = Genuinely surprising, creative connection
2 = Somewhat unexpected but interesting
3 = Natural, neutral progression
4 = Predictable, obvious next step
5 = Maximum likelihood continuation

Output:
- Transition scores: T1(S1→S2): <score>, T2(S2→S3): <score>, ...
- MEAN_SURPRISE: <average>
- LONGEST_PREDICTABLE_RUN: <number of consecutive transitions scoring 4+>
- VERDICT: If mean > 3.5 or longest run > 5, flag as AI-like

---
TEXT TO ANALYZE:
{text}
```

## Prompt 4: CoT Leakage Detection (Semantic)

Use this after the lexical scan to catch subtle CoT leakage that regex misses.

```
You are detecting CHAIN-OF-THOUGHT LEAKAGE — instances where a language model's internal reasoning process has leaked into the output text.

A CoT leak is text that exists only to help the model generate subsequent text. It serves the model's reasoning process, not the reader. By definition it is superfluous and should be deleted. A separate case is CoT-style wording: genuine content expressed using scaffolding phrases. The content is real but the phrasing is a tell. These should be reworded, not deleted.

This is NOT about whether the text was written by AI. It's specifically about whether the text contains traces of the model's PLANNING, SELF-MONITORING, or REASONING SCAFFOLDING.

Types of CoT leakage:

1. META-DISCOURSE: Text that narrates what the text is about to do ("In this section we will...")
2. REASONING CONNECTIVES: Phrases that show the model connecting its own thoughts ("This means that...", "In other words...")
3. BALANCED HEDGING: Artificial both-sides framing from uncertainty ("While X, it's also worth noting Y")
4. ENUMERATION SCAFFOLDING: Explicit numbering that reveals list-generation ("There are three reasons...")
5. FALSE EMPHASIS: Adverbial importance markers ("Crucially,", "Notably,")
6. COMPLETION ARTIFACTS: References to the model's own prior output ("As mentioned earlier...")
7. BRIDGE SENTENCES: Sentences at paragraph boundaries that exist only to steer the model from one topic to the next. They look like conclusions or implications but carry no information the reader needs — the paragraph already made the point. Common at ends of example paragraphs where the model needs to reconnect to the main argument.

BRIDGE SENTENCE DETECTION PROCEDURE:
For the last sentence of every paragraph and the first sentence of the next paragraph, apply this test:
a) Read the paragraph WITHOUT the candidate sentence.
b) Does the paragraph lose any fact, claim, or technical detail? If not, it is a bridge sentence (true CoT leak) — flag it for deletion.
c) If information would be lost, check whether the sentence uses CoT-style wording. If so, flag it for rewording.

Examples of bridge sentences:
- "A network management system that achieves L4 or higher must exhibit all three." (after a paragraph about OpenClaw — restates what the paragraph already showed)
- "This has direct implications for how we design autonomous systems." (no new information — the implications are in the next paragraph)
- "It needs a software factory that can generate new execution logic at runtime." (restates what the paragraph already established and previews the answer Section 3 delivers)

For each instance found, report:
- Line/sentence location
- Category (1-7 above)
- The offending phrase
- Classification: TRUE LEAK (delete) or COT-STYLE WORDING (reword)
- Severity: SUBTLE (could be human), MODERATE (suspicious), OBVIOUS (definitely CoT leak)

Then:
TOTAL_LEAKS: <count>
DENSITY: <leaks per 500 words>
VERDICT: clean / minor / moderate / severe

---
TEXT TO ANALYZE:
{text}
```

## Prompt 5: Overall AI Probability Assessment

Use as a final integrative judgment after all other signals are collected.

```
You are providing a FINAL ASSESSMENT of whether a text was AI-generated. You have access to the following evidence from prior detection passes:

LEXICAL SCAN RESULTS:
{lexical_results}

STRUCTURAL ANALYSIS:
{structural_results}

PERPLEXITY PROXY SCORES:
{perplexity_results}

COT LEAKAGE DETECTION:
{cot_results}

OVERSHOOT ASSESSMENT (Prompt 7):
{overshoot_results}

Now read the text itself and provide your integrated judgment. AI failure
has two directions: bland (predictable vocabulary, uniform rhythm) and
ornate (every sentence performing, epigram density, Goodharted metrics).
A low predictability score is NOT evidence of human writing when polish
intensity is uniform. Judge both directions:

1. AI_PROBABILITY: <0-100%>
2. CONFIDENCE: <low/medium/high>
3. PRIMARY_SIGNALS: <top 3 reasons for your assessment>
4. PASSAGES_OF_CONCERN: <specific passages with highest AI probability>
5. PASSAGES_THAT_SEEM_HUMAN: <any passages that feel genuinely human>
6. REWRITE_PRIORITY: <which passages should be rewritten first, ranked>

---
TEXT:
{text}
```

## Prompt 6: Antithesis / Negation-Flip Enumeration

Use after the structural scan. The `detect_antithesis` check in
detect-structural.py catches the lexically-marked cases (a negation in the
first sentence, an elliptical copula or bare negation ending the second, two
clipped fragments). It cannot catch a pure SEMANTIC antithesis — two sentences
that reverse each other with no negation word and no elided verb ("Same quality
out. Different bill.", "Planning costs more. Coding costs less."). This prompt
catches those, and adjudicates every candidate.

Forced enumeration is the point. A diffuse "find AI patterns" pass skips these
because a single antithesis pair looks like deliberate craft (Strunk & White
endorse the short contrasting sentence). Listing EVERY candidate first, then
ruling on each, defeats the skim.

```
You are detecting the NEGATION-THEN-AFFIRMATION / ANTITHESIS reflex — a pair of
adjacent sentences where the second reverses, negates, or completes the first
in a clipped, punchy cadence. It is one of the most recognizable AI tells.

Examples of the pattern:
- "The model was never the expensive part. The meter was."
- "The number that matters is not the dollars. It is the ceiling."
- "Same quality out. Different bill."
- "Planning costs more than coding. Coding is the cheap part."

STEP 1 — ENUMERATE. List EVERY pair of consecutive sentences where ANY of these
holds. Do not skip any; do not pre-judge quality yet.
  a) the first sentence negates and the second re-asserts (not X — it is Y)
  b) the second sentence is short (< 7 words) and mirrors the first's structure
  c) the two sentences are antonymic (same frame, opposite content), even with
     no negation word and no shared opening
  d) the second sentence ends on a bare verb or "not", its complement elided

STEP 2 — ADJUDICATE each enumerated pair:
  - ANCHOR: a single, deliberate contrast doing real rhetorical work at a
    section boundary. At most one or two per piece may legitimately be anchors.
  - REFLEX: the cadence used as default punctuation — filler antithesis. Any
    instance beyond the first one or two, or any that merely restates the prior
    sentence, is a reflex.

For each pair report:
- Location (quote both sentences)
- Which trigger (a/b/c/d)
- Verdict: ANCHOR or REFLEX
- If REFLEX: a one-line rewrite that makes the point in plain declarative prose

Then:
TOTAL_PAIRS: <count>
REFLEX_COUNT: <count>
VERDICT: clean (0 reflex) / minor (1-2 reflex) / pervasive (3+ reflex)

Note on calibration: if the caller has set ZERO TOLERANCE for this pattern,
treat every pair as REFLEX and rewrite all of them, including anchors.

---
TEXT TO ANALYZE:
{text}
```

## Prompt 7: Overshoot / Uniform Maximal Polish (run AFTER the scripts)

Detects the high-perplexity failure direction: text tuned against AI
detectors until every surface metric looks human while the prose reads as
mannered and machine-uniform. Any single clever sentence is legitimate; the
tell is constant intensity. Judge the distribution, not individual
sentences.

```
You are assessing a text for OVERSHOOT — the inverse AI failure, where prose
is uniformly, maximally polished. You have the structural script's metrics:

PERFORMANCE INTENSITY:
{performance_metrics}   # plain_sentence_rate, intensity_variance, mean score

PUNCH CANDIDATES:
{punch_candidates}      # short contrast sentences in positions of emphasis

WORD SALAD CANDIDATES:
{salad_candidates}      # low function-word ratio / long content runs

REPEATED FORMULAE:
{repeated_formulae}     # coined phrases recurring across the document

ORNATE-REGISTER HITS:
{ornate_hits}           # overshoot-lexicon words and their density

Assess each dimension:

(a) INTENSITY_VARIANCE: Are there plain declarative sentences that state a
    fact and stop, or does every sentence perform (pivot, antithesis,
    fragment, reversal)? Quote three plain sentences if they exist.
(b) EPIGRAM_RATE: What fraction of paragraphs close on an aphorism — a
    short, present-tense, abstract claim carrying no data?
(c) ENGINE_UNIFORMITY: Is there one construction template (claim, colon or
    dash, qualification) regardless of sentence length?
(d) COMPRESSION_DAMAGE: Quote sentences requiring a second read — missing
    subjects, noun pileups, cryptic verb choices.
(e) FORMULA_REPETITION: For each repeated formula, is it a defined technical
    term (legitimate) or a coined flourish being re-emitted?
(f) SALAD_VERIFICATION: For each word-salad candidate, apply the second-read
    test: can it be parsed in one pass? Mark for unpacking if not. Also list
    salads the regex missed (center embeddings parse fine by function-word
    ratio but still force a re-read).
(g) PUNCH_VERIFICATION: For each punch candidate, apply the removal test:
    delete the sentence and re-read the paragraph. If nothing is lost, it
    was rhetoric (confirmed punch). If information is lost, it is a plain
    short sentence (clear it).

Output:
OVERSHOOT_SCORE: <0-100>
CONFIRMED_PUNCHES: <list>
SENTENCES_TO_UNPACK: <list with reasons>
FORMULAE_TO_CONSOLIDATE: <phrase -> which single location keeps it>
VERDICT: one of "no overshoot", "occasional flourish (human range)",
"uniform polish — overshoot", "opaque — heavy overshoot"

---
TEXT:
{text}
```

## Usage Notes

- Process text in sections of 500-1500 words for best results
- Always run Prompts 1-3 in parallel (independent assessments)
- Prompt 4 runs after lexical scan (needs context of what regex missed)
- Prompt 6 runs after the structural scan (catches the semantic antithesis pairs the `detect_antithesis` regex cannot)
- Prompt 0 runs FIRST, before any script — its cold-read verdict must not be anchored by metrics
- Prompt 7 runs after the structural scan, seeded with the performance/punch/salad/formulae outputs; mandatory when the document has prior de-ai history or Prompt 0 flags register
- Prompt 5 is the integrator — runs last with all evidence, including Prompt 0 and Prompt 7
- Cache results: if a section scores clean on all prompts, skip it in recursive passes
