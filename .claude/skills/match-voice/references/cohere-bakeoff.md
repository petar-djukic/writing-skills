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

## Hardening + re-test (GH-140)

Three fixes landed and the reliability arm re-ran (command-a-03-2025, same
non-saturated draft, hardened pipeline):

- **CoT-leak guard:** `command-a-plus` denylisted in generate() and check_server(),
  plus a `_sanitize_cohere_output()` that strips instruction-echo / reasoning
  lines as defense in depth. command-a-03-2025 stays allowed.
  *(The denylist half of this was reverted in GH-155 — see "What the CoT leak
  actually was" below. The sanitizer stayed.)*
- **Non-Cohere critic:** a `cohere:` rewrite model now defaults its critic to
  gemma4:31b-cloud (env `COHERE_CRITIC_MODEL`), since Cohere critiqued itself
  into 9 unparsable verdicts.
- **Retry/backoff:** 3 attempts on 429/5xx/timeout in the Cohere path.

Re-test result, before → after hardening:

| metric | before | after |
|---|---|---|
| unparsed critiques | 9 | **0** |
| rejected | 1 | **0** |
| rewrite-errors | 6 | 6 (unchanged) |
| meta-leak lines | — | 0 (clean output) |
| Pangram AI | 0.246 | **0.489** |

The non-Cohere critic fixed the unparsed critiques outright (9 → 0) and the
rejections went to 0. The retry did **not** move the 6 rewrite-errors, so those
are not network transients; the driver's summary logging does not surface their
nature per paragraph (a follow-up: per-paragraph error logging).

**The Pangram number rose, and that is the honest correction.** The pre-hardening
0.246 was partly an artifact of the broken run — unparsed critiques and errored
paragraphs left much of the draft unprocessed. With the pipeline working, and 21
of 22 paragraphs going through a real repair pass against the gemma critic,
Cohere command-a-03-2025 measures **0.489 (Mixed)** — still well under gemma's
1.000, but a more modest win than 0.246 suggested.

### The residual errors, diagnosed and fixed (GH-142)

Per-paragraph error logging (GH-142) showed the 6 rewrite-errors were all
**HTTP 422** from Cohere on the long match-voice prompt. They were not
deterministic content rejections: the same paragraph succeeded on a direct
retry, even at a 13,722-char prompt, so the 422 behaves as **intermittent**.
The GH-140 retry had excluded 422 (only 429/5xx/timeout), which is exactly why
it "did not help." Adding 422 to the retryable set cleared them:

| stage | rewrite-errors | rejected | unparsed |
|-------|---------------:|---------:|---------:|
| pre-GH-140 | 6 | 1 | 9 |
| post-GH-140 (non-Cohere critic) | 6 | 0 | 0 |
| **post-GH-142 (422 retried)** | **0** | **0** | **0** |

Cohere command-a-03-2025 now runs **fully clean** through the whole pipeline —
24/24 paragraphs processed, zero failures — at Pangram **0.499** (Mixed), stable
with the earlier 0.489, against gemma's 1.000. (GH-142 also tightened the GH-140
output sanitizer, which had been stripping any line that merely opened with
"Now,"/"So,"/"OK," — legitimate prose — down to genuine reasoning/echo lines.)

### Go/no-go (updated after GH-142)

The reliability blocker is gone. Cohere command-a-03-2025 clears the gate as
cleanly as the incumbents (0 errors, 0 rejected, 0 unparsed) **and** keeps a
real, reproducible Pangram advantage (≈0.49 vs gemma's 1.000, where gemma
*raises* the score on a low-AI draft). On the measured axes it now beats the
incumbents for score at equal reliability.

What remains before flipping the match-voice **default** to it is not quality
but **operational and the author's call**: it is a hosted API (per-token cost
across many paragraph calls; draft text leaves the machine under Cohere's terms),
where the incumbents include local options.

**Decision (GH-145, 2026-08-29): the author accepted the tradeoff and flipped
the match-voice default to `cohere:command-a-03-2025`.** `MATCH_VOICE_MODEL` and
`--model` still override; a keyless or keep-local machine sets `--model
gemma4:12b`, the local GH-163 winner (no silent fallback — a cohere: default
with no key stops with remediation). Scope is match-voice's rewrite default
only; filter-tells and burstiness keep their own model defaults. The
command-a-plus tier stays denylisted (CoT leak). *(Superseded by GH-155: the
denylist is gone. The default itself is untouched and is re-examined in GH-156.)*

## What the CoT leak actually was (GH-155, 2026-08-29)

The GH-138 disqualification above says command-a-plus-05-2026 "emits reasoning
and echoes the prompt's own instructions into the output." Live probes against
the v2 /chat API found the mechanism is not what that sentence implies, and the
denylist it justified has been removed.

**Cohere separates the scratchpad already.** A reasoning model answers in two
typed content blocks:

```
blocks: [('thinking', ['thinking', 'type']), ('text', ['text', 'type'])]
  type='thinking'  6541 ch   "We need to rewrite the passage to remove AI writing tells..."
  type='text'       195 ch   "Google DORA research indicates that adopting AI is..."
```

Since GH-154 the backend reads blocks by type, so a thinking model's reasoning
cannot reach the prose whatever the model is called. The name-based guard could
never have worked: command-a-plus-05-2026 is a reasoning model whose name says
nothing of the sort, which is exactly why the denylist existed to patch it.

**A starved thinking budget is what puts reasoning in the answer.** One passage,
temperature 0.3:

| thinking setting | thinking block | answer block | answer opens with |
|---|---:|---:|---|
| none sent (the default) | 3954-6310 ch | 97-154 ch | clean prose |
| `{"type":"disabled"}` | 0 ch | 91 ch | clean prose |
| `{"type":"enabled","token_budget":1}` | **2 ch** | **6590 ch** | `<EOS_TOKEN>We need to rewrite the passage:` |

The last row is the GH-138 signature verbatim. Reasoning with nowhere to go goes
into the answer.

**Correction (GH-156): GH-138 IS reproducible, and this paragraph originally
said it was not.** That claim rested on single-paragraph probes, which came back
clean — 195 characters, no meta, citation intact, 3/3 on a repeat. A 76-call
sweep over a real draft found the leak on 4 of 19 paragraphs, at the default
settings, with reasoning left alone. See "Where the leak actually lives" below.
`token_budget: 1` is therefore one route to a scratchpad in the answer, not the
only one.

**Disabling thinking is not the fix.** `{"type":"disabled"}` returns a
deterministic 422 `INVALID_TOOL_GENERATION` on a long prompt — 7/7 across two
probes on the 11k-character prompt, against 0/6 for the same prompt with
thinking left alone, and 4/4 clean on a short one. It is opt-in via
`COHERE_THINKING`, that 422 is no longer retried, and `check_server` warns when
the variable is set.

**What this does not settle.** command-a-plus-05-2026 is now allowed, not
recommended. It has not been re-bake-offed; GH-156 measures it against
command-a-03-2025 before any default moves.

## The system/user split A/B (GH-156, 2026-08-29)

GH-153 proposed routing Cohere with the rules in a `system` message and only the
content in `user`, on the strength of a single-passage A/B: the split preserved a
citation 4/4 where the current single-message shape dropped it 4/4. **The verdict
is reject.** Two independent measurements, 100 calls, find no consistent benefit.

Harness: `match-voice/scripts/cohere_ab.py` (`sweep` and `replicate`). Arms are
A = everything in one `user` message (what the code does today) and B = rules in
`system`, content in `user`. Both go through the real `generate()`.

### Measurement 1 — GH-153's own passage and prompt, 6 trials per cell

| model | arm | citations kept | numbers kept | meta-leak |
|---|---|--:|--:|--:|
| command-a-03-2025 | A | 2/6 | 2/6 | 0 |
| command-a-03-2025 | B | 1/6 | 1/6 | 1 |
| command-a-plus-05-2026 | A | **6/6** | **6/6** | 0 |
| command-a-plus-05-2026 | B | 4/6 | 4/6 | 0 |

The split is neutral-to-harmful here and produced the run's only meta-leak.

### Measurement 2 — a real draft, 19 paragraphs, 76 calls

`agentic-coding-book/11-language-selection.md`, every paragraph carrying a
citation or a number, constant anchors, model and arm the only variables.
"Fully clean" means citations kept, numbers kept, no rule-echo, and output
length within 1.5x of the input.

| model | arm | fully clean | citations | numbers | runaway (>1.5x) | meta-echo |
|---|---|--:|--:|--:|--:|--:|
| command-a-03-2025 | A | 15/19 | 7/9 | 17/19 | 3 | 2 |
| command-a-03-2025 | B | 16/19 | 9/9 | 18/19 | 2 | 0 |
| command-a-plus-05-2026 | A | **18/19** | 9/9 | 18/19 | **0** | 0 |
| command-a-plus-05-2026 | B | 17/19 | 8/9 | 18/19 | 2 | 0 |

Every arm-to-arm difference is one or two items out of nine or nineteen, and the
sign flips: the split helps command-a-03-2025 slightly and hurts
command-a-plus-05-2026 slightly, having done the reverse in measurement 1. That
is noise, not an effect. **No change to the message construction.**

### Where the leak actually lives

The GH-138 signature turned up on 4 of 19 paragraphs — items 3, 10, 11 and 16 —
in both models and both arms, at default settings with reasoning left alone.
Since GH-154 the returned prose is text blocks only, so this deliberation was in
the model's *answer*, not in a thinking block that leaked:

```
command-a-plus arm B, item 11:   40 words in -> 668 out (16.7x)
  '...Now check for any changed "inner loop" vs "inner loop's". That's okay.
     Now check for any changed "inner loop" vs "inner loop's". That's okay...'

command-a-03    arm A, item 10:  85 words in -> 246 out (2.9x)
  '**VOICE ANCHORS (match this register — sentence rhythm, vocabulary,
     directness):**  In manual development, the team ensures...'
```

The second one echoes the prompt's own section heading back as output. This is
paragraph-triggered, not model-triggered: the same four items fail for both
families, and the other fifteen are clean for both.

**A prompt bug, found on the way.** Rewriting item 10, command-a-03-2025 replaced
`[@park2024]` with `[@key]` — the literal example from the prompt's own rule 1
("Citation keys look like `[@key]`"). A rule that illustrates a format with a
plausible-looking value invites the model to copy the value. Filed separately.

### What this does not settle

command-a-plus-05-2026 came out ahead on both measurements, cleanest of all in
the arm the code already uses (18/19, zero runaways, 9/9 citations). That is one
draft and one prompt shape, and Pangram was not run — the register axis that
decided GH-145 is untouched here. It is not grounds to move the default; it is
grounds to bake it off properly.


## Caveats

Pangram-human is not an HN pass (HN detector unknown). The score is a proxy; a
draft still needs the meaning-entailment review and the author's read. The
diction Cohere produces was graded only by the mechanical gate, not a voice read.
