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

**The Pangram effect showed on draft 1 and could not show on draft 2.** Draft 1
fell 74.4% to 32.4%, mean window 0.789 to 0.517 — the same direction as the
gain article and a larger move. Draft 2 was already at 100% and a 0.9929 mean
window before the pass ran. At that ceiling the fraction cannot fall and the
windows barely can: each sits near 0.99, where even a real shift in the
underlying signal moves the score by almost nothing. The arm carries almost no
information either way; see the selection note below, which is a flaw in this
experiment rather than a property of the pass.

**The control made draft 1 worse, and that strengthens the attribution.** A
gemma pass holding rhythm took the score from 74.4% to 100% and the mean window
from 0.789 to 0.914. On the gain article the same arm sat within noise (0.445
to 0.436).

Two questions come apart here, and the first draft of this report ran them
together:

- *Does the pass help?* Arm B against arm A, which is the do-nothing
  alternative: 42.0 points down. What arm C did leaves that untouched, and it
  is the number a placement decision turns on.
- *Is the gain the burstiness or the model touch?* Arm C against arm A: the
  touch alone is 25.6 points **up**. So the touch is not what helped. The
  attribution is cleaner than the gain article's, where it rested on the
  control being null.

The subtraction B minus C (67.6 points here, 17.7 on the gain article) is
worth writing down and not worth trusting. It assumes the touch's effect adds
the same way in both arms, and it rests on one document with no error bars —
while the control's own effect swung from -0.9 on the gain article to +25.6
here, a 26-point spread across two documents. A gemma pass does very different
things to different prose. What the control supports is the qualitative claim
only: the touch is not where the gain came from. The magnitude of "burstiness
alone" is not measurable at n=1.

## Three-criteria verdict

1. **Pangram delta — PASS on the one draft that could test it.** 42.0 points
   down against do-nothing, with the control ruling out the model touch as the
   source. Draft 2 began at the ceiling and carries almost no information
   either way.
2. **Burstiness metric — PASS.** CV moved in arm B and held in arm C on both
   drafts, so the tool is controllable and the control attributes cleanly.
3. **Author's ear — PENDING, with concerns listed below.** Not
   self-adjudicable, and the concerns are the reason to read arm B closely
   rather than skim it.

**The two-draft requirement is not met.** One informative document is what this
run produced, and the reason is the selection below, not the result.

## The selection was wrong twice, and it cost the second data point

Both drafts were chosen as the flattest in `drafted/` by prose-only CV, on the
reasoning that a flatter draft has more rhythm to gain. That criterion is
unrelated to the one that decides whether an arm can be measured: the baseline
detector score. Draft 2 came in at 100% and 0.9929, and a score at the ceiling
cannot fall. The arm ran, the CV rose as instructed, and the measurement was
uninformative before the first paragraph was sent.

The deeper version of the same mistake: the proposed placement is
**pre-terminal**, and a document reaching that slot has already been through
the structural step, filter-tells, and seeded match-voice — it is off the
ceiling by construction. The gain article was exactly such a document: gated
prose, baseline 0.445. Raw drafts are not; 100% is what a raw draft looks
like. So this run tested the pass in a position nobody proposed for it, and
the one draft that happened to resemble the intended input (draft 1, 74.4%)
is the one where the effect showed. The experiment disagreed with its own
question.

The next run should select for the intended condition directly: a document
that has been through the chain, screened with one baseline scan, arms only
if it has room to move.

A tempting story is that flat rhythm is itself an AI signal, so selecting on
flatness selects for saturation. These two points run the other way: draft 1 at
CV 0.503 scored 74.4%, draft 2 at CV 0.523 scored 100%. Two points support
nothing, and the story is left here as the guess it is rather than carried into
the recommendation.

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

For scale: match-voice, the sitting tenant of the pre-terminal slot, survives
cold review at 51% on mid-edit text and 33-35% on well-edited text — half to
two-thirds of its rewrites get reverted, and the pipeline absorbs that by
design, because the GH-57 cycle puts a read-only zone and the author's picks
after every generative chain. One-in-five is in family, on the better end of
it. The regressions above are an argument for keeping the pass inside that
cycle, not an argument that it fails a bar the existing stages meet.

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

**The evidence is consistent with the proposed placement.** Where the pass was
measured in something like its intended condition, the effect was large and
the control attributed it to burstiness rather than to the model touch. The
prose regression rate sits inside what the pipeline's existing generative
stages produce and what its cycle exists to absorb. The first version of this
report recommended against an "unattended stage"; no such stage exists in this
pipeline, and judging the pass against one was a category error.

What remains before the decision is closed rather than conditional:

- **One run in the true slot.** A document that has been through the chain,
  baseline-screened, three arms. The gain article was one such document and it
  worked there; this run adds a raw-ish second (draft 1). A pipeline-state
  third makes the placement claim on its own terms. Three or four scans.
- **The author's read of arm B.** Criterion 3 is not self-adjudicable, and
  the regression list above is the reason to read closely.
- **A contraction gate.** The loss belongs to the model pass, not the
  instruction, so any stage on this model needs one.

On the GH-133 question as posed — filter-tells sub-check or standalone stage —
this evidence points at the split that in fact already happened: the
*measurement* became a filter-tells/humanize report line (GH-130), and the
*generation* cannot live in filter-tells at all, because filter-tells is
Claude-side detection and generation is cross-family by the pipeline's own
rule. The generation half is a standalone pre-terminal pass or it is nothing.

Standing caveat carried from GH-129: 32.4% is "Mixed", not "Human", the venue's
detector is not Pangram, and the durable reason to want burstiness is that
prose alternating long and short reads better. Nothing here should be tuned to
the score past the point the author's ear approves.
