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


## Four-arm register bake-off (GH-160, 2026-08-29)

The measurement both earlier bake-offs lacked once the backend changed under
them: the two Cohere models against the incumbents, through the corrected
GH-154/155 backend, mechanical axes and Pangram on the same run. Harness:
`cohere_ab.py bakeoff`. Draft: `agentic-coding-book/11-language-selection.md`,
19 citation- or number-bearing paragraphs, identical anchors, single-message
shape (GH-156 rejected the split).

### Mechanical axes

| model | fully clean | citations | numbers | runaway >1.5x | meta | errors |
|---|--:|--:|--:|--:|--:|--:|
| command-a-03-2025 | 16/19 | 9/9 | 17/19 | 2 | 1 | 0 |
| command-a-plus-05-2026 | 18/19 | 9/9 | 18/19 | 1 | 0 | 0 |
| gemma4:31b-cloud | **19/19** | 9/9 | 19/19 | 0 | 0 | 0 |
| gpt-oss:120b-cloud | 18/19 | 9/9 | 18/19 | 0 | 0 | 0 |

Citations: 9/9 everywhere. GH-153's criterion — "Cohere preserves citations at
the same rate as the incumbents" — is met by every model on this draft with the
corrected backend. The GH-156 open question is answered too: the incumbents
pass the four paragraphs that drew rule-echo from Cohere (zero runaways, zero
meta across both), so that failure is Cohere-family-specific after all, just
paragraph-*selected* within the family.

### Register (Pangram, whole assembled drafts, consented upload)

| document | fraction_ai | ai-assisted | human |
|---|--:|--:|--:|
| baseline | 1.000 | 0.000 | 0.000 |
| command-a-03-2025 | 0.876 | 0.124 | 0.000 |
| command-a-plus-05-2026 | 0.884 | 0.116 | 0.000 |
| gemma4:31b-cloud | 1.000 | 0.000 | 0.000 |
| gpt-oss:120b-cloud | 1.000 | 0.000 | 0.000 |

The baseline is saturated, which GH-138 warned limits discrimination — and the
result is informative despite that: **only the Cohere models moved a saturated
draft off 1.000 at all.** Both incumbents left it pinned. Same direction as
GH-138 and GH-269, now measured through the corrected backend. The two Cohere
models are equivalent on register (0.876 vs 0.884 is noise at this resolution).

### Verdict

- **The GH-145 default flip stands.** Register is match-voice's purpose, Cohere
  remains the only family measured to move it, and citation preservation now
  matches the incumbents. GH-153's suspicion that the flip was confounded by
  backend misuse is resolved: the misuse was real (untyped block parsing), the
  confound was not.
- **command-a-plus-05-2026 is a legitimate alternative, not the new default.**
  It beat command-a-03-2025 mechanically (18/19 vs 16/19) and tied it on
  register, so the GH-138 disqualification is fully dead — but it is a
  reasoning model that spends thousands of scratchpad tokens per paragraph,
  and register, the axis that would justify paying that, shows no gain.
- **The incumbents are mechanically perfect and register-inert.** gemma4 went
  19/19 clean and left the draft at 1.000 — the GH-138 pattern again. Right
  model for filter-tells-style cleanup, wrong one for this skill's job.
- Sub-saturation replication would sharpen the register numbers; on a
  saturated payload the Cohere delta is a floor, not an estimate.

## Sub-saturation bake-off (GH-166, 2026-08-29)

GH-160 ran on a saturated payload (Pangram baseline 1.000), so its register
delta was a floor. GH-159 then changed `PROMPT` rule 1, leaving GH-160's
mechanical numbers measured against a prompt that no longer exists. This run
fixes both.

Payload: a 2,719-word slice of a **published** post
(`substack/2026/Q3/2026-08-20-strategy-theatre.md`), 17 marker-bearing
paragraphs, 15 citations, comparable in size to GH-160's. Baseline **0.225
fraction_ai / 0.385 human** — real headroom in both directions, so an arm can
be measured making the draft worse, which is the discrimination GH-160 lacked.

### Register — the discriminating axis

| arm | fraction_ai | ai-assisted | human | vs baseline |
|---|--:|--:|--:|--:|
| baseline | 0.225 | 0.389 | 0.385 | — |
| **command-a-03-2025** | **0.131** | 0.252 | **0.617** | **−0.095** |
| command-a-plus-05-2026 | 0.291 | 0.113 | 0.596 | +0.066 |
| gemma4:31b-cloud | 0.465 | 0.142 | 0.394 | +0.239 |
| gpt-oss:120b-cloud | 0.461 | 0.403 | 0.136 | +0.236 |

**Only `command-a-03-2025` improved the draft.** Both incumbents made it
materially worse — the GH-138 finding ("gemma4 *raised* the score") replicated
on a sub-saturation payload with the current prompt, and gpt-oss additionally
collapsed the human fraction from 0.385 to 0.136, the worst outcome of any arm
on any axis measured.

`command-a-plus` splits: it raised the human fraction almost as much as the
default (0.596 vs 0.617) while also raising AI. Mixed, not an improvement.

### Mechanical axes

| model | fully clean | citations | numbers | runaway >1.5x | meta |
|---|--:|--:|--:|--:|--:|
| command-a-03-2025 | 16/17 | 15/15 | 16/17 | 1 | 0 |
| command-a-plus-05-2026 | 15/17 | 13/15 | 15/17 | 0 | 1 |
| gemma4:31b-cloud | **17/17** | 15/15 | 17/17 | 0 | 0 |
| gpt-oss:120b-cloud | 16/17 | 15/15 | 16/17 | 0 | 0 |

The standing pattern holds: the incumbents are mechanically excellent and
register-harmful. gemma4 was again perfect (17/17) on the draft it damaged most.

**GH-160's mechanical ranking did not replicate.** There command-a-plus led
(18/19) and command-a-03 trailed (15/19); here they swap (15/17 vs 16/17), and
command-a-plus lost two citations where it had lost none. Both of its failures
are the same deliberation-in-the-answer signature GH-156 documented:

```
item 12  119w -> 51w   'preserve the dash after "...the middle shrinks". So we need to keep that da'
item 13  122w -> 7w    'add any extra parentheses for citation. none.'
```

Two runs of ~17 paragraphs cannot separate 15/17 from 16/17. Treat the two
Cohere models as mechanically equivalent and decide on register, where the
separation is an order of magnitude larger.

### GH-159 held

Zero invented `[@key]` literals across all 68 rewrites, against the one
occurrence that motivated the fix.

### Verdict

- **The GH-145 default stands, now on direct evidence rather than a floor.**
  `command-a-03-2025` is the only arm measured to improve a draft that had room
  to move in either direction.
- **The incumbents are disqualified for this skill's purpose**, not merely
  unhelpful: both moved a 0.225 draft to ~0.46. Their mechanical perfection is
  real and is why they remain right for filter-tells, whose job is neutral
  cleanup rather than voice.
- **command-a-plus-05-2026 stays allowed, not recommended.** It buys no
  register gain over the default and costs reasoning tokens per paragraph.
- One draft, one prompt shape, n=17 per arm. The register separation is large
  enough to carry the verdict; the mechanical differences between the two
  Cohere models are not.

## Caveats

Pangram-human is not an HN pass (HN detector unknown). The score is a proxy; a
draft still needs the meaning-entailment review and the author's read. The
diction Cohere produces was graded only by the mechanical gate, not a voice read.
