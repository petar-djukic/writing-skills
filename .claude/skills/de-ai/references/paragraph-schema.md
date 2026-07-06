# Paragraph schema reference

The single in-repo source the schema prompt cites. Summarized from:

- Gopen & Swan, "The Science of Scientific Writing", American Scientist
  78:550-558 (1990)
- Williams, "Style: Toward Clarity and Grace"
- Strunk & White, "The Elements of Style"
- MEAL/TEEL paragraph schema (Main idea, Evidence, Analysis, Link)

## Gopen & Swan

- **Topic position**: sentence openings carry known (old) information —
  the context the reader already holds. A sentence that opens on new
  material forces the reader to hold it unanchored.
- **Stress position**: sentence ends carry the new or emphasized
  information. Readers naturally emphasize what closes the sentence.
- **Subject-verb proximity**: keep the grammatical subject next to its
  verb; every word between them is held in suspense.
- **One point per paragraph**: a paragraph makes one point, stated in a
  recognizable place (usually first).

## Williams

- **Old-to-new flow**: each sentence opens with a referent the previous
  sentence established, and closes with what is new.
- **Consistent topic strings**: across a paragraph, the grammatical
  subjects form a short, consistent set. Subject churn — a new subject
  head every sentence — reads as topic drift.

## Strunk & White

- The paragraph is the unit of composition; begin it with a topic
  sentence and make the rest cohere to it.

## MEAL classification

| Slot | Role |
|---|---|
| M | Main idea — the paragraph's one claim, ideally sentence 1 |
| E | Evidence — data, citation, example supporting M |
| A | Analysis — why the evidence supports the claim |
| L | Link — connection forward or back (optional; a dangling link with no M is the defect) |

Defective shapes: no assignable M; evidence before any claim (the reader
holds data with no hypothesis); L-only paragraphs (pure transition
padding).

## Calibration

Topic-sentence-first is the dominant convention in scientific prose, not a
law — essays and narrative sections legitimately delay the topic. The
mechanical proxies (topic_overlap, cohesion, subject_churn,
anaphoric-opener) are advisory; the schema prompt adjudicates. When a
match-voice corpus profile exists for the venue, use its per-section
topic-sentence rate as the threshold instead of the defaults.
