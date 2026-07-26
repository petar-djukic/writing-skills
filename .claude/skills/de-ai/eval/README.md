# de-ai Eval Corpus and Calibration Harness

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
  python3 <de-ai>/eval/run_eval.py
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
