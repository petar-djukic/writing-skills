# Style application instructions (rewrite mode)

These instructions govern the rewrite mode of the match-outline skill: applying
a voice blueprint (or the corpus voice profile) to a draft. They are read by
the interactive skill flow and by `match_outline.py --rewrite` — this file is
the single source of truth; do not duplicate its content elsewhere.

Rewrite mode is explicit opt-in. The default skill behavior is to advise;
rewriting happens only when the user asks for it.

## Critical rules

These rules override everything else. Restate them at the top of every
rewrite prompt.

1. Never alter, omit, or invent technical data, equations, findings,
   numbers, or citations. Every number, equation, citation id, figure and
   table reference in the input appears unchanged in the output.
2. Preserve the draft's arguments and evidence exactly. Same claims,
   same evidence. Do not add content, hedges, or transitions
   that change what is being asserted.
3. Only transform prose: syntax, vocabulary, sentence rhythm, transitions,
   flow, and paragraph structure. You may merge, split, or reshuffle
   paragraphs to improve the structural voice.
4. Never copy phrasing from the exemplar excerpts. They demonstrate the
   style; they are not language to reuse. If a formulation from an excerpt
   is the natural way to say something, rephrase it anyway.
5. Output only the rewritten document text — no commentary, no markdown
   fences around the whole output, no explanations.

## Whole-document application

The model receives the entire draft in one pass, along with the blueprint
and exemplar papers. This preserves cross-section transitions, argument
arcs, and structural coherence that section-by-section rewriting would
fragment.

Papers shift voice internally: introductions are narrative and rhetorical,
methodology sections are technical and often passive, results sections are
declarative and number-dense. Apply the blueprint's conventions to each
part of the document according to its role, matching the register shifts
that the exemplars demonstrate.

Front matter (title, abstract, authors) and reference lists should be
preserved unless the user explicitly asks to rewrite them.

## Consensus vs idiosyncrasy

Blueprints separate consensus patterns (shared across exemplars — field
convention) from idiosyncrasies (one author's habit). By default apply only
consensus patterns. Apply idiosyncrasies only in mimic mode (`--mimic`, or
the user explicitly asking to imitate a specific author).

## Prompt shape

The rewrite prompt contains, in order:

1. These instructions (or their critical-rules core).
2. The blueprint (consensus sections; plus idiosyncrasies in mimic mode).
3. The exemplar papers as whole-document style demonstrations, labeled
   as style demonstrations only.
4. The entire draft to rewrite.

## Verification (after the rewrite)

Run both checks mechanically; never trust the rewrite blindly.

1. **Content preservation:** every citation id and every number present in
   the original document must appear in the rewritten document. Report each
   discrepancy — do not silently accept or silently fix it.
2. **Similarity (plagiarism guard):** run `style.py similarity` on the
   rewritten draft against every exemplar and every corpus paper whose
   text appeared in prompts, with the original draft as `--baseline`.
   Any flagged match is phrasing the rewrite introduced from a source.
   List each flagged passage with its source. The author must rephrase or
   quote it; the rewrite is not done while flags remain unexplained.

The rewritten output always goes to a new file (`<draft-stem>-rewritten.md`)
— never overwrite the draft.
