# Authorship is the lever (2026-07-26, how-to-loop-engineering)

Evidence re-homed from write-article step 6g (GH-214/substack#297): same
four stages, same anchors throughout — only the model family that wrote
the shipping words changed.

| Pipeline | Pangram AI |
|---|---|
| The published article (baseline) | 0.676 |
| match-structure via `claude-opus-4-8` | 0.753 |
| ...then filter-tells repairs by hand (Claude) | **0.775** |
| match-structure → voice → tighten, all gemma4 | 0.249 |
| ...then gemma dissolves the assertion ladder | 0.163 |
| ...then gemma removes the flagged filler | 0.161 |
| ...then gemma rebuilds the argument tail | **0.146** |

Both Claude passes moved the score *up*, and every span Claude authored
scored 0.96–0.99 on its own. The gemma chain took the same article to
0.146 with 85% of it reading human. Findings from the same run:

- **Anchors matter far less than authorship.** A Krugman-only pool, a
  Krugman+Evans pool, and the full corpus all landed within a few points
  of each other while Claude was still writing. Choosing anchors is
  tuning; choosing the model family is the decision.
- **Watch for measurement artifacts.** match-voice rule 3 preserved bold
  lead-ins and over-applied it, inflating bold openers 11 → 26 on one
  draft; `detect-structural.py` treats bold spans differently, which
  showed up as a fake `sentence_length_std` gain of 9.0 → 11.1 that
  vanished once the bold was stripped. Strip added bold mechanically (it
  is formatting, not prose, so it costs no score) before believing a
  rhythm number.
- **Know when to stop.** Pangram scores a sliding window, not a
  paragraph. On the final draft the five still-flagged paragraphs
  included the author's own untouched closer, sitting at 0.95 because of
  the company it keeps. When the residual block contains text a human
  actually wrote, further passes are optimizing against a windowing
  artifact and will be paid for in prose.
- **A favourable score is the weakest evidence in the pipeline.** The
  rewrite was steering around detectors; that a detector then stays quiet
  is close to tautological. filter-tells cannot settle the question
  either — its denylist is what the rewrite was avoiding.

Rankings are model × pipeline and rot when either changes; date any reuse
and re-measure (the GH-194 re-pin superseded this run's recipe while
confirming its authorship finding).
