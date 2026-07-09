# Rewrite Instructions

Guidelines for the Opus rewrite pass. The goal is to fix detected AI patterns WITHOUT introducing new ones.

## Core Principle

The rewrite is TARGETED, not wholesale. Only touch flagged passages. Preserve everything that scanned clean.

## Rewrite Rules

### 1. Preserve Meaning Exactly

Every rewrite must convey identical technical content. If you can't rewrite without losing meaning, flag for human review rather than attempting a lossy fix.

### 2. Match the Author's Voice

Reference the writing-style-guide.md and any sample files from the author's corpus. The rewrite should sound like the author wrote it, not like a different AI wrote it.

Key voice characteristics to target:
- Declarative, direct sentences
- Active voice preferred
- Concrete specifics over abstract claims
- Willingness to take positions (no hedging)
- Varied sentence rhythm
- Occasional short sentences for emphasis
- Technical precision without jargon inflation

### 3. Anti-Patterns to Avoid in Rewrites

The rewrite itself must not introduce:

- New banned words (check against banned-patterns.md)
- New parallelism (don't replace one pattern with another pattern)
- Uniform sentence length (deliberately vary)
- Mechanical transitions (don't replace "moreover" with "furthermore")
- CoT leakage (don't explain what you're about to say)
- Hedging language (take positions)
- Em-dashes (the author's style avoids them)

### 3b. Do Not Over-Compress — Texture Is Not Fat

The rewrite optimizes in one direction: remove AI patterns, omit needless words. Pushed too far, it produces the opposite tell — prose where every sentence is load-bearing, every paragraph snaps shut, and no aside or hedge survives. Over-polished text reads machine-made too. Human writing keeps slack. "Too sleek" is a failure verdict, not a compliment.

**Preserve texture. Do not remove:**
- Dated or personal asides ("around twenty-nine Canadian the day I am writing this")
- First-person hedges that are voice, not weakness ("I think", "I have not decided yet")
- Parenthetical wobbles and small digressions that add personality
- Deliberate two-beat rhythms ("You are not paying a frontier subscription to write your code. You are paying it, briefly, to set up the thing that will.")
- Conversational gestures ("Here is…", "The thing is…") in coaching-voice or first-person pieces

"Omit needless words" applies to self-narration and filler — not to slack. Slack is what makes prose sound written by a person. When in doubt, keep it.

**Fragment-adjacency check.** After rewriting, scan for clipped fragments (under ~5 words). If two of them land in adjacent paragraphs or at consecutive section boundaries ("Five commands, installed once." / "One task, start to finish."), restore breath to one — expand it back into a full sentence. Stacked snaps are their own machine signature.

**Burstiness floor.** Track `sentence_length_std` (the structural script reports it) across passes. If a rewrite pass *lowers* it, treat that as a warning, not progress — you have flattened rhythm toward uniformity, the exact tell the scan flags in the other direction. The metric should hold or rise through de-ai passes; a drop means you compressed texture the author wanted.

### 4. Specific Fix Strategies

| Detected Issue | Fix Strategy |
|---|---|
| Banned word | Replace with specific, concrete language. "Robust" → describe what makes it resilient. "Leverage" → "use". |
| AI cliché phrase | Delete entirely or restructure the sentence. Most clichés carry zero information. |
| False emphasis adverb | Delete. If the point needs emphasis, restructure to put it at sentence end. |
| Mechanical transition | Delete or replace with a content-bearing connection. Instead of "Furthermore, X" → just state X, or connect via shared concept. |
| Low burstiness | Vary sentence length deliberately. Split long sentences. Combine short ones. Add one punchy short sentence per paragraph. |
| Uniform paragraphs | Vary paragraph length. Some paragraphs can be 2 sentences. Some can be 6. |
| Parallelism | Restructure openings. Use different syntactic patterns: questions, conditional, relative clause, participial phrase. |
| Low opening diversity | Apply front-loading and grammatical inversion. See [opening-diversity-fixes.md](./opening-diversity-fixes.md) for the six techniques. Target: < 15% "The"-initial sentences. Mix prepositional shifts, gerund leads, infinitive purpose, subordinating conjunctions, front-weighting, and referential leads. Do NOT apply one technique uniformly. |
| CoT leakage (any category) | True CoT leak (exists only for the model's benefit): delete. CoT-style wording on real content: reword to remove the scaffolding phrase while preserving the content. See decision rule below. |
| CoT leakage (balanced hedging) | Take a position. State your view, then acknowledge limitations specifically. |
| CoT leakage (enumeration) | Fold into prose paragraphs unless genuinely procedural. |
| High predictability | Replace obvious word choices with more specific alternatives. Use the author's vocabulary. |
| Low cross-sentence surprise | Add one unexpected connection, analogy, or perspective shift per paragraph. |

### CoT Leakage Decision Rule

A CoT leak is text that exists only to help the model generate subsequent text. It serves the model, not the reader. By definition it is superfluous.

When a CoT-pattern phrase is detected, apply this test:

1. **Remove the sentence entirely.** Read the surrounding paragraph without it.
2. **If the paragraph still makes sense and loses no information:** the sentence was a true CoT leak. Delete it.
3. **If information is lost:** the sentence carries real content but uses CoT-style wording. Reword the sentence to remove the scaffolding phrase while keeping the content.

Examples:

| Flagged Sentence | Leak or Wording? | Action |
|---|---|---|
| "It is worth noting what the framework is and what it is not." | Leak — the next sentence says what it is. | Delete. |
| "In other words, agents are software factories." | Leak — the prior sentence already states this. | Delete. |
| "In other words, intent must be translated into software artifacts." | CoT-style wording — "artifacts" adds specificity the prior sentence lacks. | Reword: "Intent must therefore be translated into..." or fold "artifacts" into the prior sentence. |
| "One might argue that all such software could be written in advance." | CoT-style wording — it introduces a counterargument the paragraph then refutes. | Reword: "Could all such software simply be written in advance?" |

The default action is deletion. Most flagged phrases are true leaks with no informational payload.

### 5. Convergence Requirements

A rewrite is DONE when:
- Zero Tier 1 banned words remain
- Sentence length std > 5.0 — and it did not *drop* from the previous pass (see §3b burstiness floor; a falling std means you flattened rhythm, even while above the floor)
- No parallelism runs > 2 sentences
- Opening diversity > 0.6 (or "The"-initial sentences < 15%)
- CoT leakage density < 1 per 1000 words
- Vocabulary predictability score < 3.5 average
- Cross-sentence surprise mean < 3.5

### 6. When to Stop and Flag for Human

Stop rewriting and flag for human review when:
- Third iteration still produces new issues
- Meaning preservation becomes uncertain
- Technical accuracy might be compromised
- The passage is a direct quotation (never rewrite quotes)
- The passage is a formal specification or requirement statement

## Rewrite Prompt Template

```
You are rewriting a passage to remove AI writing patterns while preserving exact meaning and matching the author's voice.

DETECTED ISSUES IN THIS PASSAGE:
{issue_report}

AUTHOR'S STYLE (from writing-style-guide.md):
- Concise, active voice, Strunk & White style
- Specific and concrete, no vague qualifiers
- Takes positions, avoids hedging
- Varied sentence rhythm
- No dashes, no bold, no colons unless introducing a list
- Technical precision without jargon inflation

PASSAGE TO REWRITE:
{passage}

CONSTRAINTS:
1. Fix ONLY the flagged issues
2. Preserve all technical meaning
3. Do NOT introduce any patterns from the banned list
4. Vary sentence length (target std > 5)
5. Do NOT use mechanical transitions
6. Do NOT hedge or both-sides
7. Sound like a human expert wrote this in one draft

ANTI-OVERSHOOT CONSTRAINTS (the inverse failure — do not polish past human):
8. Plain sentences are allowed and required. A fact stated flatly is not a
   defect. Aim for a plain declarative in most paragraphs.
9. Do NOT close every paragraph on a flourish. Most paragraphs should end
   where the content ends.
10. STARVE LIST: never use the ornate-register words (banned-patterns.md,
    "Ornate Register" section) — pick the literal verb and the concrete
    noun. Also forbidden: this document's own repeated formulae as detected
    by detect-structural.py; each coined phrase keeps exactly one home,
    every other occurrence is paraphrased.
11. Prefer the boring accurate sentence over the clever compressed one.

UNPACKING RULES (for flagged word-salad sentences):
- One idea per sentence; split any sentence carrying two coined compounds.
- Reintroduce function words — they are the joints of the sentence.
- Expand hyphen compounds into relative clauses ("count-violating answer" ->
  "an answer that contradicts the count").
- Expand nominalizations back into verbs ("the elimination of X" ->
  "eliminating X" or "X was eliminated").
- A technical term earns its place only if it is defined or standard in the
  venue.

OUTPUT: The rewritten passage only. No commentary.
```

## Recursive Pass Protocol

1. Rewrite the flagged passage
2. Run detect-lexical.sh on the rewrite
3. Run detect-structural.py on the rewrite
3b. Re-run Prompt 0 (cold read) on the rewrite — a rewrite that improves the
    metrics but reads worse to a plain reader is a regression; script metrics
    alone never validate a rewrite
4. If new issues found AND issue count decreased: iterate (max 3 times)
5. If new issues found AND issue count same or increased: stop, flag for human
6. If clean: accept rewrite
