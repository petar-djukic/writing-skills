# Reading the scan output

What the two scripts emit and how to read it. Kept out of SKILL.md because it
loads on every invocation and is needed only once a scan has run.

## Lexical: candidates versus hard flags

The script also outputs **CoT candidates**, broad patterns that *may* be CoT scaffolding but also appear in legitimate prose. These include:
- "This/These/That ... is/are" (property announcements)
- "What X is/does/means is Y" (wh-cleft constructions)
- "Consider X" (imperative example introductions)
- "not only X but Y" (correlative conjunctions)
- "Two distinct X define..." (enumeration announcements)
- "This is where...", "That's where...", sentence-initial "Enter X" (bare stage-setting openers, `narrative-pivot-candidate` — the specific completions like "comes into play" and "here's the kicker" are hard flags)

Candidates do not fail the scan. Instead, carry them forward to Step 3 (semantic analysis) for LLM verification. For each candidate, the LLM applies the removal test: delete the sentence, re-read the paragraph. If no information is lost, it was scaffolding; if information is lost, it is genuine content and should be kept. Wh-clefts and "Consider" imperatives should usually be reworded even when they carry real content, because they read as AI regardless of intent.

## Structural: which metrics mean what

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
