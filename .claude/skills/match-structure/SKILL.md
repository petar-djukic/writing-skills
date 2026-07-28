---
name: match-structure
description: >-
  Paragraph and sentence-level style metrics for a research corpus.
  Computes quantitative profiles (sentence/paragraph distributions,
  passive voice, hedging, word/phrase/idiom frequencies, per-section
  metrics), corpus aggregation, term over/underuse comparison, and a
  plagiarism similarity guard (n-gram shingling with baseline exclusion).
  Provides voice anchor retrieval from writing-voice exemplars via tf-idf.
  The section-level driver (compare, blueprint, rewrite) moved to
  match-outline. Triggers: style profile, quantitative metrics, sentence
  stats, frequency tables, plagiarism check, similarity check, voice
  anchors, corpus profile, word frequency.
---

*Split from the original match-structure (GH-291, 2026-07): the
section-level driver (compare, blueprint extraction, section-by-section
rewrite) moved to `match-outline`. This skill retains the quantitative
metrics engine, corpus aggregation, frequency analysis, and the similarity
guard that other prose skills import.*

# Match structure (paragraph/sentence-level metrics)

This skill provides the quantitative style measurement layer that other
prose skills depend on. It profiles markdown papers at the sentence and
paragraph level — distributions, passive voice, hedging, citation density,
word and phrase frequencies, stock idiom usage — and aggregates those into
a corpus profile. It also provides the similarity plagiarism guard used by
`match-outline`'s rewrite mode and `match-voice`'s verify step.

## Where things live

- **Corpus:** `<db-dir>/papers/*.md` — the markdown conversions fetched by
  `update-references`, selected via entries in `references.yaml`. Default
  selection is entries with `status: summarized`; pass `--all` to `style.py
  corpus` to include every entry with an `md_path`.
- **Quantitative profile:** `<db-dir>/voice-profile.json`, written by
  `style.py corpus`. Regenerate only when the corpus changes.
- **Voice anchors:** passage-level tf-idf retrieval from `writing-voice/`
  exemplars, via `voice_anchors.py`.

## Running the scripts

```bash
RUN="pixi run --manifest-path <skill>/../../pixi.toml python"
```

## style.py subcommands

```bash
$RUN <skill>/scripts/style.py --db <db-path> profile <paper.md>   # one paper, full JSON
$RUN <skill>/scripts/style.py --db <db-path> corpus                # aggregate, write voice-profile.json
$RUN <skill>/scripts/style.py --db <db-path> compare <draft.md>    # metric deltas vs corpus
$RUN <skill>/scripts/style.py freq <paper.md>                      # frequency tables only
$RUN <skill>/scripts/style.py similarity <file> --against <sources> [--baseline <draft>]
```

## voice_anchors.py subcommands

```bash
$RUN <skill>/scripts/voice_anchors.py discover <file>
$RUN <skill>/scripts/voice_anchors.py profile [--voice-dir D | --for file] [--force]
$RUN <skill>/scripts/voice_anchors.py anchors --text <file>|- [--for file] [-k N] [--role R]
```

## Consumers

- **match-outline** — imports `style` for corpus selection, the similarity
  guard, and the `CITATION_RE` pattern. Uses `gpt-oss:120b-cloud` via
  Ollama for whole-document structural rewriting.
- **match-voice** — imports `style.similarity_report` for the rewrite
  verification gate; imports `voice_anchors` for anchor retrieval.
- **filter-tells** — consumes `voice-profile.json` as a detector input
  (`--voice-profile=<path>`); uses `voice_anchors.py` for anchor retrieval
  and baseline profiling.
- **tighten-style** — imports `style` for nominalization density metrics.
- **tune-anchors** — imports `voice_anchors` for the anchor tuning workflow.

## Dependencies

`style.py` is stdlib-only except PyYAML. `voice_anchors.py` uses PyYAML.
No model calls — this is the deterministic half of the analysis pipeline.
