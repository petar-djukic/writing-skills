# Burstiness pass — validation on two fresh drafts

Date: 2026-08-28. Issue: GH-132, under GH-129. Model: `gemma4:31b-cloud` via
the Ollama HTTP API. Detector: Pangram, prose-only payloads, one scan per arm.
Artifacts (arm outputs, payloads, raw responses) live in the substack
repository under
`substack/2026/drafted/experiments/2026-08-28-burstiness-validation/`; the
prose stays there rather than in the shared skills tree.

## Question

The gain-article experiment moved Pangram 0.445 to 0.259 by raising
sentence-length variance, with a rhythm-held control ruling out the model
touch. Does that hold on drafts the pass has not seen, and does it hold on
drafts that start flatter?

## Design

Two drafts, chosen as the flattest in `drafted/` by prose-only CV, both below
the gain article's 0.654:

- **draft 1** — `2026-09-13-how-to-improve-code-quality-recursively` (CV 0.503,
  85 sentences, 2,151 words)
- **draft 2** — `2026-08-20-you-cant-edit-the-model` (CV 0.523, 64 sentences,
  1,675 words)

Three arms each: **A** baseline, **B** burstiness, **C** control (same model,
same settings, rhythm held). Six Pangram scans, consented per document.

## Result

| draft | arm | CV | Pangram AI | mean window |
|---|---|---:|---:|---:|
| 1 | A baseline | 0.503 | 74.4% | 0.789 |
| 1 | B burstiness | **0.592** | **32.4%** | **0.517** |
| 1 | C control | 0.502 | 100.0% | 0.914 |
| 2 | A baseline | 0.523 | 100.0% | 0.993 |
| 2 | B burstiness | **0.591** | 100.0% | 0.993 |
| 2 | C control | 0.521 | 100.0% | 0.993 |

**The mechanism is controllable on both drafts.** Arm B raised CV by 0.088 and
0.068; arm C held it to within 0.002 in both directions. The instruction does
what it says, and the control is a real control.

**The Pangram effect replicated on one draft of two.** Draft 1 fell 74.4% to
32.4%, mean window 0.789 to 0.517 — the same direction and a larger move than
the gain article. Draft 2 did not move at all: 100% before, 100% after, mean
window 0.9929 to 0.9927 against a CV rise of comparable size.

**The control got worse on draft 1.** A gemma pass that held rhythm took the
score from 74.4% to 100% and the mean window from 0.789 to 0.914. On the gain
article the same arm sat within noise (0.445 to 0.436). So a model pass is not
neutral: its own diction can add detector signal, and on this draft it did.
Read against that, draft 1's burstiness arm did not beat a null intervention by
0.42 — it beat a harmful one, which is a weaker claim than the headline row
suggests.

## Three-criteria verdict

1. **Pangram delta — FAIL as stated.** The criterion was "does CV rise and
   Pangram fall" on both drafts. It rose on both and fell on one.
2. **Burstiness metric — PASS.** CV moved in arm B and held in arm C on both
   drafts, so the tool is controllable and the control attributes cleanly.
3. **Author's ear — PENDING, with concerns listed below.** Not
   self-adjudicable, and the concerns are the reason to read arm B closely
   rather than skim it.

## Why draft 2 did not move (a hypothesis, not a finding)

Draft 2 started saturated: 100% AI, mean window 0.9929. There is no room in
that number for a single-feature edit to show. The gain article started at
0.445 and draft 1 at 74.4%, both mid-range, and both moved.

If that is right, burstiness is a **finishing lever, not a first one**: it
would run late in the pipeline, after filter-tells and match-voice have brought
a document off the ceiling, and it would do nothing measurable when run first.
One draft is not enough to establish this. It is the cheapest next experiment —
run the pass on a document that has already been through the chain.

## Prose regressions found by reading arm B

The mechanical gate passed all of these. It checks citations, numbers, markup,
terms of art, word band, and the banned constructions; none of it sees meaning
or rhetorical structure.

- **Meaning drift.** "In most harnesses I have read, the answer is to edit the
  code" became "Most harnesses I have read suggest editing the code." A harness
  does not suggest anything.
- **A destroyed parallel series.** Four rhetorical questions in a row —
  "Is every state reachable? Can every run reach a terminal state? Is there
  exactly one transition for each state and signal? Does every signal a tool
  emits have a handler?" — came back as two questions and two statements. The
  parallelism was the device.
- **A colon that led into a code block, gone.** "...written down where you can
  see it:" became "It is written down where you can see it." The fragment it
  introduced is still there, now unintroduced.
- **Added formal connectives.** "consequently", "Yet a question remains open",
  "For example, you might" — register moving toward the formal, which is the
  direction the pipeline spends its effort moving away from.
- **Contractions lost.** Draft 1 went from 6 to 3. Arm C lost the same three,
  so this is an artifact of the gemma pass rather than of the burstiness
  instruction, and any stage built on this model needs a gate for it.
- **Invented micro-sentences.** "I waited." appears in arm B and nowhere in the
  original. It is small, it reads fine, and it is content the author did not
  write.

Some splits are good. "Model providers ship a sealed function. The terms of
access forbid opening it; the weights would not help you if you could" is
better than the original. "For an agent, that surface is the harness. All of
it." earns its short sentence. The pass is not uniformly bad — it is
unsupervised, and roughly one edit in five needs reverting.

## Two defects this run found in the pass itself

Both fixed before the numbers above were taken; both are in the test suite.

- The system prompt named the `[[LOCK-n]]` anchor token whether or not the
  paragraph carried one, and the model obliged by inventing tokens. Six of 21
  paragraphs were rejected on a draft with zero locked spans. The rule is now
  appended per paragraph, with a count, only when tokens are present, and
  rejections fell to one.
- Reported CV was computed over the raw file, counting headings, code fences,
  and table rows as sentences: 1.399 whole-file against 0.503 over the prose.
  It is now measured over the paragraphs the pass can touch.

## Recommendation

**Do not promote this to an always-on pipeline stage on this evidence.** One
replication of two, a control that harmed the score on the draft where the
burstiness helped, and a prose defect rate around one edit in five is not the
profile of a stage that runs unattended.

What the evidence does support:

- Keep the tool. The mechanism is real and controllable, and the measurement
  is now in place.
- Run it **late and by hand**, on documents already off the detector ceiling,
  with the control arm alongside and the diff read before acceptance.
- Add a contraction gate before any further use, since the loss is a property
  of the model pass rather than of the instruction.
- Test the saturation hypothesis before deciding placement. That experiment
  costs one document and two scans.

Standing caveat carried from GH-129: 32.4% is "Mixed", not "Human", the venue's
detector is not Pangram, and the durable reason to want burstiness is that
prose alternating long and short reads better. Nothing here should be tuned to
the score past the point the author's ear approves.
