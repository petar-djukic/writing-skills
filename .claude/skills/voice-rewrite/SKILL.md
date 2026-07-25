---
name: voice-rewrite
description: >-
  Rewrite paragraphs of a draft in the author's voice using a second model
  family served by Ollama, with a verification gate before any text is spliced
  back. Retrieves voice anchors from the repository's writing-voice/ exemplars,
  sends paragraph plus anchors to a local (or cloud) Ollama model, then gates
  the result on citation/number preservation, meaning entailment, anchor
  similarity, and register. Triggers: voice rewrite, rewrite in my voice,
  ollama rewrite, rewrite paragraphs, local model rewrite, sound like my
  earlier papers, rewrite against writing-voice.
---

# voice-rewrite (Ollama rewrites, Claude judges)

The rewriting model is deliberately **not** Claude. de-ai detects and steers
within the Claude loop (GH-156); this skill hands the rewrite itself to a
different model family so the prose decorrelates from Claude's own lexical
fingerprints, instead of Claude grading its own homework. Claude keeps the
job it is good at: judging whether the result is faithful.

That division is the point. **Verification is not optional** — an 8B model
rewriting technical prose will drop a citation, round a number, or quietly
strengthen a claim. Nothing is spliced into a draft until the gate passes.

## Prerequisites

- A `writing-voice/` directory of exemplars (contract: the repository's
  writing-voice rule; roles `author-voice` / `venue-voice`). Without it this
  skill has no target and should not run — use plain de-ai instead.
- A reachable Ollama endpoint with the model pulled, at
  `http://localhost:11434` by default.

**Model choice (GH-163 bake-off, 10 models on one paragraph with identical
anchors, judged on voice fidelity plus the full gate):**

| Use | Model | Why |
|---|---|---|
| Local default | `gemma4:12b` | best local everywhere: faithful near-verbatim pass, no term or claim damage |
| Local, 32 GB Apple Silicon | `gemma4:31b-mlx` | the 31b tier without egress (inferred from the cloud row, not separately bake-offed) |
| Cloud, best overall | `gemma4:31b-cloud` | restructures naturally, preserves every term and claim, no flags |
| Cloud, second opinion | `kimi-k2.6:cloud` | minimal and judicious — edits least, damages nothing |

**Prefer local when the machine can hold the model.** Rewriting operates on
unpublished draft prose, and the cloud rows send every paragraph off the
machine to buy quality that a big-memory Mac already has locally. Reach for
cloud when the memory is not there, or for the second opinion.

The 31b row wants roughly 32 GB of unified memory: an mlx build of that tier
is a ~20 GB weight file, and context and the rest of the system go on top.
Measured on an M2 Max with 32 GB, where the comparable `qwen3.6:35b-mlx`
occupies 21 GB and runs. At 16 GB, stay on `gemma4:12b` (7.6 GB); a model that
does not fit swaps, and a rewrite that takes minutes per paragraph is a
rewrite nobody runs. `ollama list` shows the size before you commit to it.

The two cloud models are complementary: one rewrites well, the other knows
when not to. `mistral-large-3` editorializes (trips the register scan);
`glm-5.2` and `deepseek-v4-flash` are safe but flatten deliberate rhythm.
**`llama3.1:8b` ranked last** — it destroyed a term of art and weakened a
claim while passing the mechanical gate, which is precisely why the semantic
half of the gate is not optional.

A first `ollama pull` of a cloud model can fail transiently; an immediate
retry succeeds.

```bash
python3 <skill>/scripts/rewrite.py --check --text /dev/null
```

If this fails, **report it and stop**. The skill never falls back to a Claude
rewrite: that would defeat the decorrelation it exists for.

## Driver (whole-article orchestration)

`scripts/drive.py` runs the per-paragraph pipeline over a full article and
assembles the gate-passing rewrites into a sibling `<article>.vr-draft.md`:

```bash
python3 <skill>/scripts/drive.py --article <path.md> --model gemma4:31b-cloud
python3 <skill>/scripts/drive.py --article <path.md> --coverage-only   # no model calls
```

- **Coverage audit is mandatory output.** Every body line is classified
  (prose / heading / figure / table / code / reference / blockquote / list /
  rule / blank); any unclassifiable line is reported as a WARNING and
  `--coverage-only` exits nonzero. Added after a real question — "did the
  driver skip the first paragraphs?" — that an ad-hoc driver could not answer.
  Run `--coverage-only` first when in doubt; the paragraph map is the answer.
- Retries are failure-classified automatically (copy → anti-copy note,
  number/citation loss → preserve-numbers note, register → banned-vocab note).
- The driver applies the MECHANICAL gate only. The emitted draft is a set of
  candidates: run the meaning-entailment review (references/prompts.md) on each
  accepted paragraph, and de-ai over the assembled file, before treating the
  draft as accepted.
- Kept-original paragraphs are listed with their failure category. A kept
  original is a correct outcome, and the keeps double as an internal control
  in redistribution experiments (the 2026-07 Pangram run: flagged residue
  mapped to the kept paragraphs).

## The pipeline (per paragraph)

Paragraph is the unit of work. The skill never restructures across
paragraphs.

**1. Retrieve anchors.**

```bash
python3 <skill>/scripts/retrieve.py --text <paragraph-file> --for <draft> -k 3 --json > anchors.json
python3 <skill>/scripts/retrieve.py --text <paragraph-file> --for <draft> -k 3 > anchors.txt
```

Top-k topically nearest exemplar passages, `author-voice` preferred.
**Retrieval is lexical (tf-idf), so anchors match the author's vocabulary, not
necessarily the paragraph's subject** — a meta-paragraph about fragmented
literatures may pull scheduling papers. That is fine and often correct: the
anchors exist to carry register, not content. Do not treat an off-topic anchor
as a retrieval failure.
Retrieval is the de-ai `voice_anchors` implementation imported from the
sibling skill — built once, imported twice, so the two skills cannot drift.

**2. Rewrite.**

```bash
python3 <skill>/scripts/rewrite.py --text <paragraph-file> --anchors anchors.txt \
  [--model gemma4:12b] [--endpoint http://localhost:11434] [--temperature 0.7] [--timeout 300]
```

**3. Gate — all four checks, fail closed.**

```bash
python3 <skill>/scripts/verify.py --original <paragraph-file> --rewrite <candidate> \
  --anchors-json anchors.json
```

| Check | Who | Fails on |
|---|---|---|
| Citations, numbers, terms | `verify.py` | a key or figure lost, altered, or invented |
| Citation syntax family | `verify.py` | `[@key]` silently rewritten as `\citep{key}` — the key survives but the build breaks |
| Anchor similarity | `verify.py` (match-voice shingles) | a long verbatim run copied from an exemplar |
| Meaning entailment | **Claude**, per references/prompts.md | any claim weakened, added, or re-scoped |
| Register | de-ai lexical scan on the candidate | banned words — one machine register traded for another |

`verify.py` exits nonzero on violation so the loop can gate on it directly.
It is the *mechanical* half only; a clean exit is necessary, not sufficient —
run the entailment judgment and the de-ai scan before accepting.

**3b. Two-model mode (optional).** Run the same paragraph and anchors through
both cloud models, gate both candidates, and have the Claude judge pick the
better rewrite (or keep the original if neither is faithful). The pairing that
paid off in evaluation is `gemma4:31b-cloud` + `kimi-k2.6:cloud`: when they
disagree about whether a sentence needs changing at all, the more conservative
answer is usually right.

**4. Splice or keep.** On a clean gate, accept. Otherwise retry with a
failure-specific note (`--retry-note`, table in references/prompts.md) up to
N times (default 2), then **keep the original paragraph and record why**. A
kept original is a correct outcome; expect a meaningful reject rate from an 8B
model and do not assume success.

**5. Report.** A per-paragraph table: accepted / retried / kept-original, with
gate failures by category. Rewrites are proposed as a diff for review by
default; applying them directly is opt-in.

## Configuration

| Setting | Flag | Default |
|---|---|---|
| Endpoint | `--endpoint` / `OLLAMA_ENDPOINT` | `http://localhost:11434` |
| Model | `--model` / `VOICE_REWRITE_MODEL` | `gemma4:12b` |
| Temperature | `--temperature` | 0.7 |
| Timeout (s) | `--timeout` / `VOICE_REWRITE_TIMEOUT` | 300 (cold loads are slow) |
| Anchors per paragraph | `-k` | 3 |
| Max copied run (words) | `--max-shared-run` | 8 |

## Did it work? (optional external check)

This skill has had no outcome measure. The gate proves a candidate preserved
citations, numbers, and meaning; it cannot tell you whether the prose stopped
reading as machine-written. de-ai's detectors cannot settle it either — they
are the denylist the rewrite was steering around, so their silence is close to
tautological.

An external detector answers it from outside. Scan, rewrite, scan again:

```bash
python3 <de-ai>/scripts/pangram_report.py payload --article draft.md
python3 <de-ai>/scripts/pangram.py --text draft.payload.txt --json > before.json
# ... run the rewrite ...
python3 <de-ai>/scripts/pangram_report.py payload --article draft.md
python3 <de-ai>/scripts/pangram.py --text draft.payload.txt --json > after.json
python3 <de-ai>/scripts/pangram_report.py report --response after.json \
    --spans draft.payload.spans.json --baseline before.json
```

Two things to know before starting. The baseline must be captured **before**
the rewrite — there is no reconstructing it afterwards, and discovering that
later means the comparison is simply unavailable. And a full comparison costs
two scans against a free tier of four a day.

This uploads the draft to a third party that retains it, which is the opposite
of the local-first reason this skill exists. It asks per document, every time;
see the upload rule in the `writing-voice/` directory rule. Without a key, skip
it — the pipeline is unchanged and still worth running.

The still-flagged paragraph list is the useful output: it is the worklist for
another pass, pointing at the passages the rewrite did not fix.

## Relationship to the other prose skills

- **de-ai** detects the tells and, with `writing-voice/`, steers its own
  rewrites toward the same anchors. Use de-ai when Claude should do the
  rewriting; use this skill when you want a different model's prose.
- **match-voice** owns voice profiling and the similarity guard this skill
  reuses for the copy check.
- Run de-ai over the finished draft afterward regardless — a local model's
  output is not exempt from the tells.

## Dependencies

The pixi environment (PyYAML) plus a reachable Ollama. Retrieval and the
similarity guard import their implementations from the sibling de-ai and
match-voice skills, which every agent surface carries.
