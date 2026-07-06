---
name: de-ai
description: 'Detect and fix AI writing patterns recursively. Use when: reviewing text for AI tells, cleaning AI-generated drafts, checking for CoT leakage, measuring text perplexity and burstiness, making text sound human, fixing opening diversity. Triggers: de-ai, ai detection, ai writing, perplexity, burstiness, CoT leakage, humanize text, opening diversity, sentence starts.'
argument-hint: 'Path to markdown file to analyze and fix'
---

# De-AI: Recursive AI Writing Detection and Correction

Detects AI writing patterns at three layers (lexical, structural, semantic) and recursively rewrites flagged passages until they pass all checks.

## Standing Warning: Scripts Are Blind to Rhetorical Patterns

The two scripts (`detect-lexical.sh`, `detect-structural.py`) measure surface metrics only — banned words, opening diversity, sentence length variance, dash density. They **cannot** detect the rhetorical patterns that constitute most of the AI signal in real prose:

- Declarative pairs ("X is Y. Z is W.")
- Definition-by-enumeration ("X extends in two ways")
- Meta-narrative bridges ("The analogy breaks in one place")
- Triple parallels ("clearer instructions, tighter constraints, fewer ambiguous cases")
- Comprehensive enumerated sweeps in parentheses

Partial exception: `detect-structural.py` now has a `detect_antithesis` check that catches the lexically-marked subset of negation-then-affirmation ("X is not Y. It is Z.", "The meter was.") and clipped antithesis fragments. It does not catch the purely semantic reversal ("Same quality out. Different bill." used without a negation word). Prompt 6 in Step 3 covers that remainder. Treat the regex as a recall aid, not full coverage of the pattern.

A `clean` or `minor-issues` verdict from the structural script means the surface checks passed. It does **not** mean the prose is in voice. Step 3 (semantic analysis by Opus) is the only layer that catches the rhetorical AI tells the scripts still miss. Skipping Step 3 produces false-negative reports.

The blindness runs in **both directions**. The scripts flag the bland AI direction (low burstiness, repetitive openings). Text iteratively rewritten against these very detectors overshoots into the opposite register — uniformly maximal polish, epigram-closing paragraphs, coined formulae, word salads — and passes every surface check while reading as obviously machine-made ("the LinkedIn voice"). The structural script now emits overshoot metrics (`plain_sentence_rate`, `punch_clustering`, `salad_rate`, repeated formulae, `suspicious-overshoot` verdict), but the judgment lives in Prompt 0 (cold read) and Prompt 7 (overshoot assessment). A `minor-issues` verdict on a document with prior de-ai history deserves MORE suspicion, not less.

**Do not infer voice quality from the structural script's verdict label.** Voice is a judgment, not a statistic.

## When to Use

- Before publishing any document drafted or edited by AI
- When reviewing a file for AI writing tells
- When a document "feels" AI-written but you can't pinpoint why
- After AI-assisted writing sessions to clean the output
- To check for CoT (chain-of-thought) leakage in final text

## Prerequisites

- Python 3.8+ available
- The target file is a markdown file
- The writing-style-guide.md is present in `templates/`

## Procedure

### Step 0: Cold Read (Model, BEFORE the scripts)

Run Prompt 0 from [perplexity-prompts.md](./references/perplexity-prompts.md) on the document before looking at any script output. The cold read answers what no metric can: could a plain reader follow this on one pass, and is the register appropriate for the venue? Record the COLD_VERDICT — it anchors nothing and is anchored by nothing.

### Step 1: Run Lexical Scan (No Model Required)

Run the lexical detection script to find banned words, AI clichés, false emphasis, narrative-pivot frames, and mechanical transitions:

```bash
bash .claude/skills/de-ai/scripts/detect-lexical.sh <file-or-dir> [file-or-dir ...]
```

Accepts a single file, multiple files, or directories (scans `*.md` recursively).

This produces line-numbered matches grouped by category. Zero-cost, instant results.

The script also flags **Marketing/Hype Vocabulary** (`venue-jargon`) — frontier models, cutting-edge, best-in-class, and friends. Calibration matters: these are human-register words, flagged as venue-inappropriate undefined jargon, not as AI tells. Do not flag quoted text or paraphrases of a source's own title.

The script also outputs **CoT candidates**, broad patterns that *may* be CoT scaffolding but also appear in legitimate prose. These include:
- "This/These/That ... is/are" (property announcements)
- "What X is/does/means is Y" (wh-cleft constructions)
- "Consider X" (imperative example introductions)
- "not only X but Y" (correlative conjunctions)
- "Two distinct X define..." (enumeration announcements)
- "This is where...", "That's where...", sentence-initial "Enter X" (bare stage-setting openers, `narrative-pivot-candidate` — the specific completions like "comes into play" and "here's the kicker" are hard flags)

Candidates do not fail the scan. Instead, carry them forward to Step 3 (semantic analysis) for LLM verification. For each candidate, the LLM applies the removal test: delete the sentence, re-read the paragraph. If no information is lost, it was scaffolding; if information is lost, it is genuine content and should be kept. Wh-clefts and "Consider" imperatives should usually be reworded even when they carry real content, because they read as AI regardless of intent.

### Step 2: Run Structural Analysis (No Model Required)

Run the structural detection script to measure burstiness, parallelism, paragraph uniformity, and density metrics:

```bash
python3 .claude/skills/de-ai/scripts/detect-structural.py <file-or-dir> [file-or-dir ...]
```

Accepts a single file, multiple files, or directories (scans `*.md` recursively).
Default threshold is `strict`. Use `--threshold=medium` for drafts, `--threshold=relaxed` for early notes.

Review the metrics output. Key signals:
- `sentence_length_std < 4.0` = unnaturally uniform (AI); `> ~40` = overshoot suspicion (tuned against this check)
- `opening_diversity < 0.6` = repetitive sentence starts (AI), typically "The" dominance
- `dash_density > 3.0` = em-dash overuse (AI)
- `plain_sentence_rate < 0.25` = almost no rest beats; every sentence performs (overshoot)
- `punch_clustering > 0.3` = paragraphs habitually close on a punch (overshoot)
- `salad_rate_per_100 > 10` = jargon-dense sentences without function-word joints
- repeated formulae listed = coined phrases re-emitted across the document
- `opener_duplication` reported = the abstract and introduction share their first sentence (cross-document check; a reviewer reads the same opener twice)
- `paragraph_schema` block = advisory Gopen & Swan / Williams proxies (topic_overlap, cohesion, subject_churn, anaphoric openers); low-topic paragraphs carry to Prompt 9
- `verdict: likely-ai`, `suspicious`, or `suspicious-overshoot` = proceed to Pass 3

If `opening_diversity` is flagged, load [opening-diversity-fixes.md](./references/opening-diversity-fixes.md) for six rewrite techniques (prepositional shift, gerund lead, infinitive purpose, subordinating conjunction, front-weighting, referential lead). This is the hardest issue to fix because it requires rewriting many sentences across the document.

### Step 3: Semantic Analysis (Requires Opus) — MANDATORY

If Pass 1 or Pass 2 found *any* issue, Step 3 is required, not optional. The scripts are blind to rhetorical patterns. Reporting a verdict without Step 3 is a procedural error and produces false negatives.

Step 3 may be skipped only when Pass 1 and Pass 2 both return zero matches and zero issues.

Load the prompts from [perplexity-prompts.md](./references/perplexity-prompts.md) and run against the target text:

1. **Vocabulary Predictability** (Prompt 1) — Score each sentence 1-5 for how "obvious" the word choices are
2. **Burstiness Assessment** (Prompt 2) — Confirm structural findings with semantic judgment
3. **Cross-Sentence Surprise** (Prompt 3) — Detect absence of genuine thought progression
4. **CoT Leakage Detection** (Prompt 4) — Find reasoning scaffolding that regex missed, including bridge sentences at paragraph boundaries. For each candidate, Prompt 4 applies the removal test: delete the sentence, check whether the paragraph loses information. True leaks are flagged for deletion; CoT-style wording on real content is flagged for rewording.
5. **Overshoot Assessment** (Prompt 7) — mandatory when the document has prior de-ai history, when Prompt 0 flags register, or when the structural verdict is `suspicious-overshoot`. Seeded with the script's performance/punch/salad/formulae outputs; applies the removal test to punch candidates and the second-read test to salad candidates.
6. **Antithesis / Negation-Flip Enumeration** (Prompt 6) — run with **Prompt 6b** (rhetorical set pieces).
7. **Definedness and Circularity** (Prompt 8) — mandatory for publication verdicts. Enumerates undefined substantive terms (marketing jargon like "frontier models" is human register — the cadence detectors cannot see it), circular opening claims (predicate restating premise), and quantity mismatches ("the costs compound" supported only by error-rate data). Runs on the abstract and section openers.
8. **Paragraph Schema and Claim Coherence** (Prompt 9) — MEAL classification per paragraph, adjudication of the structural script's low-topic candidates, and the nonsense check (can a cold reader evaluate each opening claim?). Grounded in references/paragraph-schema.md; composes with Prompt 8 rather than duplicating circularity. — Enumerate every adjacent-sentence antithesis pair and rule each ANCHOR or REFLEX. Catches the purely semantic reversals the `detect_antithesis` regex cannot. Honor the caller's tolerance: under zero tolerance, rewrite every pair.

Run Prompts 1-3 in parallel. Run Prompt 4 after reviewing lexical results (it needs that context). Run Prompt 6 after the structural scan (it extends `detect_antithesis`).

Finally, run **Prompt 5** (Overall Assessment) with all collected evidence to get an integrated judgment and rewrite priority list.

#### Required output of Step 3

The final report from Step 3 must follow [`assets/report-template.md`](./assets/report-template.md) and must include:

1. The rewrite priority list from Prompt 5's output, structured by issue with line references.
2. Explicit confirmation that Step 3 was run (which prompts were applied, summary findings from each).
3. An honest plain-language verdict. Options: "in voice — no rewrite needed", "isolated issues — spot edits only", "pervasive rhetorical patterns — section rewrite needed", "heavy AI fingerprints — paragraph-by-paragraph rewrite needed", "over-corrected — needs plain-prose rewrite toward the venue register".

Freeform summaries without these elements are not a valid Step 3 output.

### Step 4: Targeted Rewrite

For each flagged passage (in priority order from Prompt 5):

1. Load the [rewrite instructions](./references/rewrite-instructions.md)
2. Load the project's voice reference for this document type, if one exists — for example a `.claude/rules/<voice>.md` file the project provides (per-format voice guides are common: one for articles, one for long-form, etc.). If the project defines none, infer the target voice from existing published work in the same venue. Do not assume any specific file name.
3. For CoT leaks: remove the flagged sentence and re-read the paragraph. If no information is lost, the sentence is a true CoT leak — delete it. If information is lost, the sentence uses CoT-style wording on real content — reword to remove the scaffolding phrase while preserving the content.
4. Rewrite ONLY the flagged passage using the rewrite prompt template
5. Constraints: preserve meaning, match author voice, don't introduce new AI patterns

### Step 5: Recursive Validation

After each rewrite:

1. Re-run `detect-lexical.sh` on the rewritten section
2. Re-run `detect-structural.py` on the rewritten section
3. If issues remain AND count decreased: iterate (max 3 total passes)
4. If issues remain AND count same or increased: STOP, flag for human review
5. If clean on both scripts: accept the rewrite

### Step 6: Final Semantic Verification

After all passages are rewritten, run the full semantic analysis one more time on the complete document to check for:
- New patterns introduced by rewrites
- Consistency issues between rewritten and preserved sections
- Overall document flow after modifications

## Abstract Mode

Abstracts are read ~100x more than the body and have the most rigid,
best-documented structure — the easiest text to diagnose and repair.
Trigger: the user asks to check or fix an abstract, or a publication-verdict
run encounters one. Standards: `references/abstract-standards.md`.

**Analyze (default):**

1. Mechanical checks:
   ```bash
   python3 .claude/skills/de-ai/scripts/abstract-check.py <paper.md> \
     --body <results.md> <other-chapters.md...> --limit 200
   ```
   Locates the abstract (LaTeX environment, front matter, heading, or
   whole file), counts words against the venue limit (default 200), runs
   the number-traceability check against the body, and sweeps
   self-containedness (citations, section/figure references).
2. Run Prompt 10 (move map: one row per sentence — move, conforming,
   action), plus Prompt 8 and Prompt 9 Part B on the abstract's sentences.
3. Report the move map and verdict: conforming | repairable | rebuild.

**Fix (opt-in, only on a failing verdict):** run Prompt 11 — rebuild move
by move from body excerpts (written-last principle: intro -> moves 1-2,
results numbers verbatim -> move 3, conclusion -> move 4; never reuse
failed phrasing). Then verify: abstract-check.py traceability must pass
(any number absent from the body rejects the rewrite), re-run Prompt 10
(max 3 passes), and run the standard scans for register regressions.

## Convergence Rules

- Rewrites must never be validated by script metrics alone — that is how overshoot happens. After each rewrite pass, re-run Prompt 0 on the rewritten section; a rewrite that improves the metrics but worsens the cold read is a regression.
- Maximum 3 rewrite iterations per passage
- If iteration N finds >= issues as iteration N-1, stop immediately
- Never rewrite direct quotations
- Never rewrite formal specifications or requirement statements
- When in doubt, flag for human rather than risk meaning loss

## Verdict Validity Rules

- A "clean" or "in voice" verdict requires Step 3 to have been run and to have returned no high-priority issues. Verdicts issued without Step 3 are invalid.
- A `clean` or `minor-issues` label from the structural script is not a substitute for Step 3. The label is a surface-metric summary, not a voice assessment.
- "Looks mostly fine" / "largely in voice" / similar freeform softening language is not a valid verdict. Use one of the four plain-language options from Step 3's required output.
- If you anchor on the structural script's verdict and skip Step 3, the report is a procedural failure regardless of how the prose actually reads.

## Model Selection

**Use Opus for ALL passes.** Rationale:
- Detection requires deep model self-awareness (simpler models can't recognize their own patterns)
- Rewriting requires preserving technical meaning while transforming style
- Validation must be strict enough to achieve convergence
- Cost per document is low (sections are small, 3 iterations max)

## Reference Documents

- [Banned patterns database](./references/banned-patterns.md)
- [CoT leakage patterns](./references/cot-leakage-patterns.md)
- [Opening diversity fixes](./references/opening-diversity-fixes.md)
- [Perplexity proxy prompts](./references/perplexity-prompts.md)
- [Rewrite instructions](./references/rewrite-instructions.md)
- [Report template](./assets/report-template.md)

## Quick Mode (Lexical + Structural Only)

For in-progress drafts where you want a fast surface-pass without burning model calls:

```bash
bash .claude/skills/de-ai/scripts/detect-lexical.sh <file-or-dir>
python3 .claude/skills/de-ai/scripts/detect-structural.py <file-or-dir> --json
```

Quick Mode is for working drafts. It is **not** valid for a publication verdict. Quick Mode catches the surface-detectable patterns. The rhetorical patterns that account for most of the AI signal are invisible to the scripts and require Step 3. Do not report a verdict based on Quick Mode output alone.
