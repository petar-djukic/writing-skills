# Voice analysis instructions

These instructions drive the qualitative half of the match-voice skill. They
are read by the interactive skill flow (Claude Code) and by the headless
`match_voice.py` driver — this file is the single source of truth; do not
duplicate its content elsewhere.

The task has two products: a corpus voice profile, and a draft comparison
report. When only the corpus is provided, produce the profile. When a draft
and metric diff are also provided, produce the comparison report using the
existing profile.

## Part 1 — Corpus voice profile

Read the corpus papers and describe how this field writes. Quote short
exemplars (one or two sentences) for every observation — an unquoted claim
about the corpus is a guess. Cover each dimension:

### Openings and framing

- How do introductions open? Problem-first, context-first, anecdote,
  statistics? Quote two or three representative first paragraphs.
- How are contributions framed? Bulleted claim lists, woven prose,
  numbered contributions paragraph?
- How is the gap in prior work stated — direct criticism, polite
  contrast, or omission?

### Terminology and register

- What terms does the field use for its core concepts, and which variants
  win (e.g. "agent" vs "policy", "LLM" vs "language model")?
- What is assumed known vs explicitly defined?
- Formality level: contractions, first person ("we"), direct address,
  humor tolerance.

### Rhetorical moves

- Common transitions between sections and between claims.
- How disagreement with prior work is expressed.
- How limitations are admitted — dedicated section, scattered hedges,
  or absent.

### Methodology conventions

- Level of setup detail: are datasets, baselines, hyperparameters,
  hardware specified? Where — prose, tables, appendix?
- Reproducibility signals: code links, seeds, configuration listings.
- Equations vs prose: is the method formalized mathematically or
  described procedurally?
- Standard subsection patterns (e.g. Problem Formulation → Architecture
  → Training).

### Results conventions

- Tables vs figures: which carries the main results, and how are they
  referenced in text?
- Statistical reporting norms: significance tests, confidence intervals,
  error bars, number of runs, ablations.
- How claims are qualified: "outperforms" vs "outperforms by X% (p<0.05)".
- How negative or mixed results are handled.
- Baseline comparison phrasing.

Write the profile to `voice-profile.md` next to `references.yaml`, with a
frontmatter block recording the corpus size and date, and one section per
dimension above. Keep it dense; every claim carries a quote.

## Part 2 — Draft comparison report

Given the draft, the corpus profile, and the quantitative diff from
`style.py compare`, write a report following
`comparison-report-template.md`. Rules:

- Interpret the metric deltas — do not just restate them. "Your sentences
  average 31 words against a corpus mean of 22" should be followed by what
  that reads like and where in the draft it concentrates.
- For voice mismatches, quote the draft and a corpus exemplar side by side.
- For the methodology and results sections, check the draft against each
  convention observed in Part 1 and flag gaps explicitly (e.g. corpus
  papers report over how many runs; the draft reports single numbers).
- Jargon alignment has two directions: field vocabulary the draft is
  missing, and draft terms the corpus never uses. The second list is where
  idiosyncrasies and AI-tell phrasing show up.
- Advise, do not rewrite — unless the user explicitly invoked the rewrite
  mode, which follows `style-application-instructions.md`. In comparison
  reports each finding gets a direction ("shorten", "add statistical
  qualification", "adopt the term X"), not edited text.
- An honest "the draft already matches the corpus on this dimension" is a
  valid finding. Do not manufacture mismatches.

## Part 3 — Exemplar blueprint extraction

Given one or more exemplar papers the user wants to mimic (e.g. well-written
papers from the target conference), extract a voice persona blueprint.
Analyze how each paper is written. **Do not summarize the content; analyze
how it is written.**

### Stage 1 — per-exemplar mini-blueprint

For each exemplar independently, produce a structured mini-blueprint
covering:

1. **Sentence mechanics:** average sentence length, structural complexity
   (subordination, parentheticals), and the balance of active vs passive
   voice.
2. **Lexicon and tone:** level of technical abstraction, preferred
   qualifying words (e.g. "suggests", "delineates"), and degree of
   assertiveness.
3. **Signposting and transitions:** how paragraphs are bridged, and how
   figures and data are introduced.
4. **Formatting quirks:** structural habits or rhetorical devices unique to
   this author.

Every claim quotes a short exemplar passage as evidence — an unquoted claim
is a guess, and the synthesis stage cannot verify it.

### Stage 2 — synthesis (two or more exemplars)

Merge the mini-blueprints into one consensus blueprint with two top-level
sections:

- **Consensus:** patterns appearing in most exemplars. These are field or
  venue conventions and are safe to adopt in any rewrite.
- **Idiosyncrasy:** patterns unique to one exemplar, flagged with their
  source paper. These are one author's habits; adopt them only when the
  user deliberately mimics that author (mimic mode).

With a single exemplar, skip synthesis: the mini-blueprint becomes the
blueprint, with a note that every pattern is single-source and therefore
potentially idiosyncratic.

Save the blueprint as `voice-blueprint-<slug>.md` next to `references.yaml`,
with frontmatter recording the exemplar ids and date.
