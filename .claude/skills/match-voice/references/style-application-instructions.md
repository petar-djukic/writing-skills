# Style application instructions (rewrite mode)

These instructions govern the rewrite mode of the match-voice skill: applying
a voice blueprint (or the corpus voice profile) to a draft. They are read by
the interactive skill flow and by `match_voice.py --rewrite` — this file is
the single source of truth; do not duplicate its content elsewhere.

Rewrite mode is explicit opt-in. The default skill behavior is to advise;
rewriting happens only when the user asks for it.

## Critical rules

These rules override everything else. Restate them at the top of every
rewrite prompt.

1. Never alter, omit, or invent technical data, equations, findings,
   numbers, or citations. Every number, equation, citation id, figure and
   table reference in the input section appears unchanged in the output.
2. Preserve the draft's structural logic and arguments exactly. Same claims,
   same order, same evidence. Do not add content, hedges, or transitions
   that change what is being asserted.
3. Only transform prose: syntax, vocabulary, sentence rhythm, transitions,
   and flow.
4. Never copy phrasing from the exemplar excerpts. They demonstrate the
   style; they are not language to reuse. If a formulation from an excerpt
   is the natural way to say something, rephrase it anyway.
5. Output only the rewritten section text — no commentary, no markdown
   fences around the whole output, no explanations.

## Section-by-section application

Papers shift voice internally: introductions are narrative and rhetorical,
methodology sections are technical and often passive, results sections are
declarative and number-dense. Apply the blueprint one section at a time,
matching each draft section against the blueprint's conventions for that
section type and against exemplar excerpts of the same section type
(intro excerpts when rewriting the intro, methodology excerpts for
methodology).

Front matter (title, abstract, authors) is rewritten only if the user asks;
by default pass it through unchanged.

## Consensus vs idiosyncrasy

Blueprints separate consensus patterns (shared across exemplars — field
convention) from idiosyncrasies (one author's habit). By default apply only
consensus patterns. Apply idiosyncrasies only in mimic mode (`--mimic`, or
the user explicitly asking to imitate a specific author).

## Per-section prompt shape

Each rewrite prompt contains, in order:

1. These instructions (or their critical-rules core).
2. The blueprint (consensus sections; plus idiosyncrasies in mimic mode).
3. Two or three short exemplar excerpts of the same section type, labeled
   as style demonstrations only.
4. The draft section to rewrite.

## Verification (after every rewrite)

Run both checks mechanically; never trust the rewrite blindly.

1. **Content preservation:** every citation id and every number present in
   the original section must appear in the rewritten section. Report each
   discrepancy — do not silently accept or silently fix it.
2. **Similarity (plagiarism guard):** run `style.py similarity` on the
   rewritten draft against every exemplar and every corpus paper whose
   excerpts appeared in prompts, with the original draft as `--baseline`.
   Any flagged match is phrasing the rewrite introduced from a source.
   List each flagged passage with its source. The author must rephrase or
   quote it; the rewrite is not done while flags remain unexplained.

The rewritten output always goes to a new file (`<draft-stem>-rewritten.md`)
— never overwrite the draft.
