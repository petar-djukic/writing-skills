# Cohere bake-off (GH-138)

Cohere's command-a models against the incumbent cross-family rewriters
(gemma4:31b-cloud, gpt-oss:120b-cloud, kimi-k2.6:cloud), run through the real
match-voice driver (retrieval → rewrite → mechanical gate → critique), 2026-08-28.
Follows the GH-163 method (identical anchors, model the only variable) and closes
the gap it could not: GH-163 never included Cohere, and the substack GH-269
result only proved Cohere beats the *session model*, never the incumbents.

## Setup

Two payloads, both real newsletter drafts, venue-voice anchors (18 selected,
identical across arms since retrieval is model-independent):

- **Saturated** (you-cant-edit-the-model, 6 paras): baseline Pangram 1.000.
- **Non-saturated** (code-quality-recursively, full draft, 1386 words): baseline
  Pangram 0.744 — the payload with headroom to discriminate on score.

## Results

### Pangram — non-saturated draft (the discriminating axis)

| Arm | Pangram AI | vs baseline |
|-----|-----------:|-------------|
| baseline | 0.744 | — |
| gemma4:31b-cloud | **1.000** | +0.256 (WORSE) |
| cohere command-a-03-2025 | **0.246** | −0.498 (much better) |
| cohere command-a-plus-05-2026 | 0.653 | invalid — CoT-contaminated |

The incumbent **gemma raised the score** on a draft that started at 0.744, all
the way to saturation. Cohere command-a-03-2025 **drove it down to 0.246.** This
extends GH-269: Pangram is trained on the common open families, so gemma's
fingerprint reads as AI; Cohere's rarer fingerprint reads as human. On score,
Cohere wins decisively.

On the saturated payload every arm tied at 1.000 — no single voice rewrite
cracks a saturated ceiling (the burstiness-null result again), so that payload
cannot discriminate. Use a sub-saturation draft for any model comparison.

### Reliability — through the real gate (of 24 paragraphs, non-saturated)

| Arm | rewrite-errors | rejected | unparsed critique | output clean? |
|-----|---------------:|---------:|------------------:|---------------|
| gemma4:31b-cloud | 0 | 0 | 0 | yes |
| gpt-oss:120b-cloud | 0 | 0 | 0 | yes (6-para run) |
| kimi-k2.6:cloud | 0 | 0 | 0 | yes (6-para run) |
| cohere command-a-03-2025 | 6 | 1 | 9 | yes (1404w, 1 stray line) |
| cohere command-a-plus-05-2026 | 2 | 4 | 1 | **NO — CoT/instruction leak** |

The incumbents pass every paragraph. Cohere command-a-03-2025 failed often (6
errors, 9 unparsed critiques), **but** a 6-for-6 rapid-call diagnostic shows
simple prompts succeed — so the failures are integration-level (the long
match-voice prompt, and Cohere-as-its-own-critic producing unparsable critique
output), not a fundamental limit. Likely fixable.

### command-a-plus-05-2026 is disqualified

It emits reasoning and echoes the prompt's own instructions into the output
("is the rewritten paragraph. No preamble…", "Now, we need to ensure we
preserve the term 'four'…"), ballooning 1386 → 2086 words of meta-commentary.
It behaves like a thinking model despite no "reasoning" in its name, so the
name-based guard added in GH-137 does not catch it. Its 0.653 Pangram is a
garbage-text artifact, not a real score. command-a-03-2025 does NOT do this
(1404 words, clean).

## Verdict

A real tradeoff, not a clean winner:

- **Score:** Cohere command-a-03-2025 wins big (0.246 vs gemma's 1.000; gemma
  actively harms a low-AI draft). Too large to dismiss.
- **Reliability:** incumbents win (0 failures vs 6+9); Cohere's failures look
  integration-level and fixable, not fundamental.
- **command-a-plus:** disqualified (CoT leak); the name guard needs strengthening.

**Recommendation: do NOT change the match-voice default yet, and do NOT close
Cohere out.** The score advantage is large and matches GH-269, so command-a-03-2025
is worth hardening and re-testing rather than dropping. Keep it as the additive
backend (GH-137). Concrete follow-ups (GH-140):

1. Guard out command-a-plus / sanitize CoT-and-instruction-echo from Cohere
   output — the name-based reasoning guard is insufficient.
2. When the rewrite model is Cohere, use a reliable non-Cohere critic model so
   the critique step stops producing unparsable output (the 9 unparsed).
3. Add retry/backoff for the rewrite-errors, then re-run the reliability arm.

Then re-decide the default with a clean reliability number beside the score win.

## Caveats

Pangram-human is not an HN pass (HN detector unknown). The score is a proxy; a
draft still needs the meaning-entailment review and the author's read. The
diction Cohere produces was not voice-graded here beyond the mechanical gate —
that read is part of the GH-140 re-test.
