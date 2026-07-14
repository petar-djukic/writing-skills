# Drafting Guidance (write it right the first time)

The generative counterpart to banned-patterns.md. That file catalogs what to
detect after the fact; this one is the compact DO-list to hand the model
BEFORE it drafts, so the tells are prevented instead of repaired. Keep this to
a page — it is loaded into drafting context. Each line cross-references the
banned-patterns.md section (or prompt) that documents the WHY.

## Voice and register

- Write as the author, not as an assistant. No offers, no sign-offs, no
  "want me to…" — the document has no chat turn. [Tier 0: Chat-Turn Residue]
- Use plain technical vocabulary. If a word would look at home in a keynote
  ("revolutionary", "seamless", "landscape"), replace it with the specific
  fact. [Tier 1, Marketing and Hype Vocabulary]
- Skip the ornate register: no "tapestry", "testament", "at its core", no
  verbs doing theater ("unleash", "harness"). Plain verbs carry technical
  prose. [Ornate Register]

## Sentences

- Vary rhythm naturally: some long sentences, some short, most in between.
  Do not alternate mechanically, and do not make every sentence a performance
  — most sentences should simply state things. [Overshoot; plain_sentence_rate]
- One antithesis ("not X. Y.") can anchor a piece; the second one is a reflex.
  Prefer stating the positive claim without the negated foil. [Prompt 6;
  Antithesis]
- When two adjacent sentences share a frame, break BOTH ends — heads and
  tails. "…whatever model you run. …whatever you run it on." is still a
  mirror. [tail_echo; Prompt 6]
- Close paragraphs on content, not on a snap. If every paragraph ends in an
  epigram, none of them lands. [Overshoot: punch_clustering]

## Words and phrases

- Define a coined term at first use ("X — that is, …"), or do not coin it.
  A bigram you invented and repeat ("claims posture") is private vocabulary
  to the reader. [Compressed Conversation; coinage_candidates]
- A metaphor may accompany a mechanism, never replace it: "connective tissue
  that routes state between components" — the mechanism clause is mandatory.
  [Compressed Conversation]
- State results, not reactions: delete "sobering", "striking", "remarkably",
  or replace them with the number that earned the adjective.
  [Editorializing adjectives]
- Do not announce structure: "One rule organizes it: R" → just state R.
  [Stage-setting frames; Narrative Pivots]

## Paragraphs and document shape

- Every paragraph must say one thing no earlier paragraph said. If a
  paragraph only re-summarizes, cut it — recap is ballast. [Prompt 3 Part B]
- Transitions carry content or don't exist: no "Furthermore," no bridge
  sentences that restate the previous paragraph to steer into the next.
  [Prompt 4: bridge sentences; Mechanical transitions]
- Open sentences differently as a side effect of thinking, not by rotation:
  lead with the subject that matters in each sentence. [Opening diversity]
- Keep slack: a dated aside, a first-person hedge, a parenthetical wobble are
  voice, not fat. Do not sand every sentence to load-bearing minimum.
  [Rewrite instructions §3b: texture]

## Claims

- No claim whose predicate restates its premise; no quantity word ("costs",
  "overhead") unless the evidence measures that quantity. [Prompt 8]
- Take positions. Hedged both-sides framing ("while X, it's also true that Y")
  is scaffolding, not analysis. [CoT leakage: balanced hedging]

## Keeping this in sync

Pair rule: every new failure class added to banned-patterns.md gets a
corresponding DO-line here, in the same change. One home for the WHY
(banned-patterns.md), one for the drafting DO (this file).
