# Detector Thresholds and Boundaries

Every numeric threshold in the detection scripts, with its justification or an
explicit **uncalibrated** marker, plus the documented boundaries between
overlapping detectors, and the GH-123 noise-audit results. Calibration status
resolves against the eval corpus (see `../eval/README.md`); "uncalibrated —
pending eval corpus" means the value was hand-picked from motivating examples
and awaits measurement against labeled human prose.

## detect-structural.py — THRESHOLDS dict (per strict/medium/relaxed)

| Threshold | strict / medium / relaxed | Justification |
|---|---|---|
| sentence_length_std_min | 5.0 / 4.0 / 3.0 | classic low-burstiness AI floor; uncalibrated — pending eval corpus |
| sentence_length_std_max | 35 / 40 / 50 | overshoot ceiling (two-sided, GH-43 era); uncalibrated |
| paragraph_length_std_min | 20 / 15 / 10 | uniform-paragraph floor; uncalibrated |
| parallelism_max_repeats | 2 / 2 / 3 | >2 consecutive same openings reads mechanical; uncalibrated |
| list_ratio_max | .25 / .30 / .40 | prose docs; specs legitimately exceed — use relaxed there; uncalibrated |
| colon_density_max (/500w) | 3 / 4 / 5 | colon-engine tell; fired 7/8 on proxy papers — see audit; uncalibrated |
| dash_density_max (/500w) | 2 / 3 / 4 | em-dash overuse; uncalibrated |
| opening_diversity_min | .7 / .6 / .5 | "The"-dominance floor; uncalibrated |
| plain_sentence_rate_min | .30 / .25 / .20 | overshoot: every sentence performs; uncalibrated |
| punch_clustering_max | .25 / .30 / .40 | paragraphs habitually closing on a punch; uncalibrated |
| salad_rate_max (/100 sents) | 8 / 10 / 15 | jargon runs without function-word joints; fires on standards prose (audit) — treat hits on spec register as candidates; uncalibrated |
| hyphen_compound_max (/500w) | 5 / 6 / 8 | coined-compound density; uncalibrated |

## detect-structural.py — fixed constants

| Constant | Value | Where | Justification |
|---|---|---|---|
| short-fragment floor | <4 words dropped | split_sentences | burstiness stability; uncalibrated |
| question volley run | ≥3 consecutive | question patterns | checklist-as-questions move; uncalibrated |
| Q/A template pairs | ≥2 adjacent, answer ≤4w | question patterns | uncalibrated |
| tail-echo window | last 4 tokens, ≥2 shared, ≥1 non-trivial | detect_tail_echo | sized to the GH-104 motivating pair; **advisory since GH-123** (see audit) |
| punch skeleton run | ≥3 consecutive ≤10w | detect_punch runs | uncalibrated |
| formulae min_count | ≥3 uses, 4-grams, ≥2 content words | repeated_formulae | coined-phrase re-emission; uncalibrated |
| coinage min_count | ≥2 uses, 2–3-grams, no definition marker | detect_coinage | advisory by design; terms-of-art fire it (audit) |
| voice-distance flag | \|z\| ≥ 2.0 (rel ≥ .5 fallback) | voice_distance | conventional 2-sigma; uncalibrated |
| density tells (/500w) | tricolon <3, paren-def <4, passive-enabling <2, rather-than <2, contrast-flip <2, both-and <1.5 | analyze | GH-45..52 era motivating docs; uncalibrated |
| verdict ladder | ≥2 high, or 1 high + 2 med → likely-ai; 1 high or 2 med → suspicious | analyze | severity aggregation; uncalibrated |

## detect-lexical.sh

| Gate | Value | Justification |
|---|---|---|
| chat-residue tail window | last 3 lines → CRITICAL | trailing sign-off position; by construction |
| ornate-register density | >4.0 per 500w | density-scored, single hits allowed; uncalibrated |
| editorializing / narrative-pivot / CoT lists | n/a (candidates) | advisory by design — semantic pass rules |

## Overlap boundaries (documented, deliberately not merged)

- **repeated_formulae vs detect_coinage.** Formulae: 4-grams, ≥3 uses —
  catches a *re-emitted phrase* regardless of definedness ("each coined phrase
  gets one home"). Coinage: 2–3-grams, ≥2 uses, only when *never defined* —
  catches private vocabulary. A defined term repeated 5× trips neither wrongly;
  an undefined bigram used twice only trips coinage; a slogan re-emitted 3×
  trips formulae. Merging would lose the definition-marker semantics.
- **detect_parallelism vs detect_frame_parallelism vs detect_tail_echo.**
  Position and shape differ: openings (first 2 words, consecutive runs) vs
  syntactic frame (varied surface, repeated skeleton) vs endings (last 4
  tokens, adjacent pairs). Each catches rewrites that dodge the others —
  GH-104 exists precisely because fixing openings pushed the pattern to tails.
- **analyze_punch vs analyze_performance.** Punch: paragraph-final position
  (clustering of closers). Performance: sentence-level rhetoric-marker rate
  (plain_sentence_rate). A document can fail either alone.

## GH-123 noise audit (2026-07-14)

Proxy corpus: 8 published arXiv papers as PDF→markdown conversions
(`autogenic-systems/papers/`). **Caveat: authorship unverified and conversion
artifacts (broken paragraphs, reference lists, table debris) inflate several
metrics — indicative, not authoritative. The authoritative rerun happens when
`eval/human/` is populated (GH-120).**

Findings and actions:

- `tail_echo` fired 8/8, mostly ordinary domain repetition (shared
  ['an','element']). **Demoted to advisory** (`tail_echo_candidates` in the
  JSON; no longer sets an issue or affects the verdict; the semantic pass
  rules on mirror pairs). The GH-104 motivating catch survives as a candidate.
- `coinage_candidates` fired 8/8 — established terms-of-art ("itu-t rec" ×33)
  look like coinage to the detector. Already advisory; caveat documented:
  Prompt 8b dismisses standard vocabulary (the term-of-art test).
- `word-salad-heavy`, `colon-heavy`, `low-opening-diversity` fired broadly —
  partially conversion artifacts (line-broken text), partially the standards
  register. No action until the clean human corpus exists; treat hits on
  converted PDFs and spec prose with suspicion.
- All 8 proxy files scanned `likely-ai` — unusable as a clean-human check,
  reinforcing that `eval/human/` needs author-designated, conversion-free
  samples.

## GH-187 — length normalization of presence-style detectors (2026-07-26)

Measured on the 24 author-voice exemplars (GH-186 banded eval): average
detectors fired on the author's own pre-AI prose climbed 6.0 (400 w) to 10.7
(2,500 w) with register held constant. The cause was detectors that fire on an
absolute count anywhere in the document, so opportunity scaled with length
while evidence per word did not. Per-500-word density metrics (colon, dash,
tricolon, rather-than, both-and, contrast-flip, passive-enabling, paren-def)
were already length-safe and are untouched.

Every change re-expresses the existing threshold at its ~500-word tuning
point; short-document behaviour is unchanged by construction
(`length_scaled_min(word_count, per_1000, floor)`).

| Detector | Before | After | per_1000 rationale |
|---|---|---|---|
| antithesis (all subtypes) | every pair an issue, zero tolerance | pairs counted in metrics always; become issues at >= max(1, 2.0/1000w) | 1 pair in 500 w fired before; same density now required at any length. Verdict counted issues per pair, so 5 scattered pairs in a long paper alone forced likely-ai |
| parallelism | any run > max_repeats | runs gated at >= max(1, 2.0/1000w) | "We derive... We prove..." somewhere in 12k words is convention |
| frame-parallelism | any run | same gate as parallelism | same reasoning |
| topic-sentence-weak | >= 3 weak paragraphs, absolute | >= max(3, 30% of paragraphs scored) | 3 of 6 paragraphs is a pattern; 3 of 100 is a paper. Was 0.96 on full papers, 0.00 on 400 w excerpts of the same prose |
| low-opening-diversity | unique ratio over all sentences | mean of 40-sentence window ratios | whole-document ratio decays by Zipf alone as n grows; windows measure the local monotony the detector is after |
| repeated_formulae | min_count 3, absolute | max(3, 1.5/1000w) | any domain term is a repeated 4-gram in 12k words |
| coinage_candidates | min_count 2, absolute | max(2, 1.0/1000w) | scaling stops long-document inflation only; its matched-length misfires (1.00 at every band) are GH-188, not solved here |

Deliberately left absolute, with the reason at the definition: none — every
whole-document count detector is now scaled. Per-sentence judgments
(nominalization >= 4 in one sentence, comparative pairs in one sentence) are
local evidence and were never length-sensitive.

Verification: GH-186 banded eval before vs after, human class avg detectors
fired — target roughly flat across 400/800/1500/2500; ai-class rates must not
fall. Results recorded on GH-187.
