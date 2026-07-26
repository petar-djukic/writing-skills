# filter-tells Eval Corpus and Calibration Harness

Ground truth for the two detection scripts. Without labels, the suite is
unfalsifiable: we cannot measure false-positive rates on human writing or tell
whether discrimination improves as detectors accumulate. This directory makes
detector changes measurable.

## Layout

- **Human samples come from the repository you run in, not from this
  directory.** `run_eval.py` walks up from the working directory to find
  `writing-voice/` and uses its `author-voice` exemplars as the human class —
  the same discovery rule the rest of the prose skills use. Run the harness
  from a repository that carries one:

  ```bash
  cd ~/GITHUB/<a-writing-repo>
  python3 <filter-tells>/eval/run_eval.py
  ```

  This matters because `.claude/` is a symlink into the shared skills repo. A
  sample dropped into `eval/human/` does not land in your project — it lands in
  the public skills repo, alongside everyone else's. Reading from
  `writing-voice/` keeps a private corpus private: the harness reads the files
  and records provenance, never the text.

- `human/` — an optional local override, used only when it contains files. Left
  empty on purpose. Anything placed here is published with the skills, so use
  it only for prose you would publish anyway.
- `ai/` — unedited model drafts, each labeled in a header comment (generator,
  date, register, "never edited"). Seeded with three Claude-generated samples
  covering the known registers: bland assistant, overshoot ("LinkedIn voice"),
  and compressed-conversation spec prose.
- `run_eval.py` — runs `detect-lexical.sh` + `detect-structural.py` over both
  classes; reports per-detector fire rates per class and suite verdict
  accuracy (ai files must not scan clean; human files must not scan
  likely-ai); diffs against `baseline.json` and exits 1 on regression.
- `baseline.json` — committed snapshot of the current rates. Regenerate with
  `python3 run_eval.py --update-baseline` after an intentional change.

## Labeling rules

- Human samples: written before model assistance, or verifiably hand-written.
  When in doubt, leave it out — a mislabeled sample poisons every rate.
  Curating `writing-voice/` is the curator's job, not the harness's; the
  harness uses what the manifest lists. It does warn about any exemplar dated
  after 2022, because prose written once generative AI was available may carry
  AI diction, and that is circular as ground truth for what human prose looks
  like. The warning does not drop the sample — that call is the curator's.
- `ai/`: raw model output only. An edited draft is neither class.
- Every file carries a header comment stating its provenance and label
  rationale.

## Length bands — read these before believing a fire rate

```bash
python3 run_eval.py --bands
```

The overall per-detector rates compare whatever is in each class. When the two
classes differ in length, those rates partly measure length rather than
authorship, and the report says so: a `length_mismatch` block appears whenever
the class medians differ by 2x or more.

That is not hypothetical. The first honest run compared a human class with a
5,889-word median against an ai class at 332 words and reported the difference
as a false-positive rate. Twenty detectors appeared to exceed the gate. Most
were measuring length — `topic-sentence-weak` fires on 96% of full papers and
on 0% of 400-word excerpts of those same papers.

`--bands` samples every document down to 400, 800, 1500, and 2500 words —
consecutive whole paragraphs, deterministic, skipping documents too short for a
band rather than padding them — and reports rates per band. Comparing like with
like is the only way these numbers mean anything.

Read `avg_detectors_fired` across the bands first. If it climbs with length,
the detectors are counting opportunity rather than evidence, and the
per-detector rates in the wider bands are inflated. Then read `non_clean_rate`
per band: that is the fraction of genuinely human prose the skill would flag at
that length, which is the number a writer actually experiences.

## Detectors vs candidates

The report carries two tables. `detectors` are issue-emitting checks — they
drive verdicts, and `HUMAN_FIRE_GATE` governs them. `candidate_rates` are
advisory signals: lexical grep categories and the `*_candidates` blocks, which
are prompts for the semantic pass by contract and never touch a verdict. They
get no gate; a candidate at 1.00 on human prose is a statement about the
corpus register, not a broken detector. Counting the two together is how the
harness once reported 20 detectors "over the gate" (GH-182/GH-188).

## The new-detector gate

Before merging a new detector:

1. Run `python3 run_eval.py`. The new detector must fire on at least one `ai/`
   sample (or add a sample exhibiting the tell — seed list discipline).
2. It must fire on at most 20% of `human/` files (`HUMAN_FIRE_GATE`). Above
   that, retune it or demote it to advisory (candidates, not issues).
3. No existing detector's human-class rate may rise (the harness exits 1).
4. Regenerate the baseline in the same change and say why in the commit.

Scope: the harness covers the two scripts only. Semantic prompts (Step 3)
need a model and are evaluated by their motivating examples in
banned-patterns.md, not here.
