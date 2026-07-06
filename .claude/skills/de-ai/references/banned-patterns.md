# Banned Patterns Database

Extends the writing-style-guide.md with additional AI-detectable patterns.
These patterns are checked by `detect-lexical.sh`.

## Tier 0: Chat-Turn Residue (Catastrophic — Fails the Scan Outright)

Text from the model's conversational wrapper committed into the document
body. Not a style pattern — the assistant speaking. Severity above every
other tier: one hit means the document shipped with the chat frame attached.
A match in the final 3 lines of the file is near-certain residue (the
trailing sign-off).

| Pattern | Why |
|---|---|
| "Want me to...", "Would you like me...", "Shall I..." | offer-of-more-work sign-off |
| "Let me know if..." | conversational close |
| "Hope this helps", "Happy to help", "Feel free to ask" | assistant pleasantries |
| "Ready for Substack", "here's a suggested" | delivery framing |
| "I can also create/draft/write/add..." | capability offer |
| "As an AI..." | self-reference |

Real case: a published article ended with "Ready for Substack. Want me to
create a suggested author bio or any other supporting materials?" — both
scripts passed it.

## Tier 1: Hard Ban (Always Wrong)

These never appear in good technical writing. Instant flag.

| Pattern | Why |
|---------|-----|
| delve, delving | ChatGPT signature word |
| tapestry | Purple prose, never needed |
| realm | Metaphor pollution |
| landscape | Overloaded metaphor |
| paradigm | Almost never the right word |
| synergy | Corporate jargon |
| holistic, holistically | Vague, means nothing precise |
| leverage, leveraging | Use "use" |
| utilize, utilizing | Use "use" |
| facilitate, facilitating | Use "enable" or "allow" |
| empower, empowering | Marketing language |
| foster, fostering | Vague nurture metaphor |
| navigate, navigating | Unless about actual navigation |
| cutting-edge | Cliché |
| state-of-the-art | Cliché (unless citing a specific benchmark) |
| game-changing | Hype |
| groundbreaking | Hype |
| revolutionize, revolutionizing | Hype |
| transformative | Almost always exaggeration |
| multifaceted | Use "complex" or describe the facets |
| pivotal | Use "important" or explain why |
| underpins, underpinning | Use "supports" or "enables" |
| dovetails | Use "aligns with" or "complements" |
| illuminates, illuminating | Use "shows" or "reveals" |
| overarching | Use "main" or "general" |
| interplay | Use "interaction" or "relationship" |
| salient | Use "important" or "relevant" |
| delineate, delineating | Use "define" or "describe" |
| encapsulate, encapsulates | Use "contains" or "expresses" |
| myriad | Use "many" |
| plethora | Use "many" or "excess" |
| burgeoning | Use "growing" |
| nascent | Use "early" or "new" |
| hinges on | Use "depends on" |

## Tier 2: Context-Dependent (Usually Wrong)

These have legitimate uses but are AI tells in most contexts.

| Pattern | When legitimate | AI tell when |
|---------|----------------|-------------|
| comprehensive | Describing actual scope | Describing anything as "a comprehensive X" |
| robust | Engineering spec with definition | Vague praise |
| seamless, seamlessly | Never legitimate | — |
| innovative | Never self-describe | — |
| enhance, enhancing | Database/image operations | Vague improvement claim |
| ecosystem | Actual software ecosystem | Metaphor for "group of things" |
| moreover, furthermore, additionally | — | Sentence opener (transition filler) |
| consequently | — | Mechanical transition |
| nevertheless, nonetheless | — | When "but" works |
| thereby | — | Always replaceable with simpler phrasing |
| wherein | — | Always replaceable with "where" or "in which" |
| albeit | — | When "though" works |
| enables | Technical capability description | Vague causation ("this enables better X") |
| ensures | Formal guarantee | Vague ("ensures quality") |
| bridges, bridging | Actual bridge | "bridges the gap between X and Y" |
| coupled with | Engineering coupling | "X, coupled with Y, provides..." |
| in tandem | — | Always replaceable |
| advent | Historical first appearance | "with the advent of AI..." |
| akin to | — | Use "like" or "similar to" |
| renders | 3D rendering | "renders the system X" — use "makes" |
| warrants | Legal/formal context | "warrants further investigation" |
| dictates | Actual mandate | "the architecture dictates..." — use "requires" |
| speaks to | — | "this speaks to the need for..." — just state the need |
| constitutes | Legal/formal definition | "constitutes a significant X" — use "is" |
| manifests | Medical/physical symptom | "manifests as..." — use "appears as" |
| affords | — | "affords the ability to" — use "allows" |

## Tier 3: Density Markers (Fine Alone, Bad in Clusters)

These words are fine individually. Flag when 3+ appear in a single paragraph.

- particularly
- specifically
- essentially
- effectively
- significantly
- inherently
- ultimately

## Compound Patterns (Phrase-level)

These multi-word patterns are strong AI signals:

```
"plays a crucial role"
"serves as a"
"paves the way"
"represents a significant"
"offers a unique"
"provides a comprehensive"
"enables seamless"
"ensures robust"
"a rich tapestry"
"the intricacies of"
"shed light on"
"in today's rapidly"
"in an era of"
"the ever-evolving"
"at its core"
"stands as"
"remains to be seen"
"it is worth emphasizing"
"it is no coincidence that"
"it is precisely this"
"strikes a balance"
"stands in contrast"
"lends itself to"
"gives rise to"
"paves the way for"
"a testament to"
"is tantamount to"
"by the same token"
"in light of"
"in the context of"
"in a manner that"
"to that end"
"to this end"
"along these lines"
"with this in mind"
"bears emphasizing"
"merits attention"
"worthy of note"
"the crux of the matter"
"the key insight here is"
"the upshot is"
"the takeaway is"
"what emerges is"
"at a high level"
"zooming out"
"zooming in"
"stepping back"
"put differently"
"stated differently"
"viewed through this lens"
"through the lens of"
"taken together"
"in doing so"
"in this way"
"in effect"
```

## Technical Writing Tells (Domain-specific AI patterns)

These appear specifically in technical/academic LLM output at unnatural rates:

| Pattern | What to write instead |
|---------|----------------------|
| orthogonal to | "independent of" or restructure |
| non-trivial | Describe the actual difficulty |
| first-class | "full" or "native" or describe the support |
| out of the box | Specify what's included |
| under the hood | Describe the mechanism directly |
| at scale | Quantify |

## Ornate Register (Overshoot Lexicon)

The vocabulary the maximally-clever "LinkedIn voice" depends on. This is the
inverse failure from the bland tiers above: text tuned against AI detectors
until every sentence performs. These words are legitimate individually —
"axis" in a plot, "residual" in a regression, "floor" in a bound — so
**detection treats them as density markers** (like Tier 3: fine alone, bad in
clusters; flagged above ~4 per 500 words). **Rewrite passes hard-forbid
them**: the rewriter can always choose a plainer word, so there is no
false-positive cost during rewriting. Starving these words out makes most
epigrams unwritable.

| Sub-category | Words / frames | Plain alternative |
|---|---|---|
| Metaphor verbs (epigram engines) | loads, carries (a claim/cost), buys, hires/hired, manufacture, forfeits, inherits (an error rate), converts (failures), narrates, decides (as in "reliability decides whether"), survives (a prediction), awaits | use the literal verb: causes, requires, produces, loses, describes, determines |
| Abstract epigram nouns | instrument, concession, axis (non-plot), mass (non-physics), price, floor/ceiling (non-math), dial, menu, engine (non-mechanical), affordance, register (non-CS), the split, the construct | name the concrete thing |
| Rhetorical glue | merely, emphatic "itself", sentence-initial "Nor", "the X in question", "to the digit" | delete or use "only" |
| Borrowed-metaphor adjectives | load-bearing, first-class, orthogonal (non-math), surface (non-API), upstream/downstream (non-pipeline), brittle (non-materials) | describe the actual property |
| Aphorism frames (phrase-level) | "X is the Y, not the Z", "the price of X is Y", "buys X with Y", "X is not a Y problem but a Z problem", "what X narrates as Y" | state the claim once, plainly |

**Dynamic extension:** `detect-structural.py` reports the document's own
coined formulae (verbatim 4-word phrases recurring 3+ times). During a
rewrite, each detected formula gets one home; every other occurrence is
paraphrased. The static list starves the register; the dynamic list starves
this document's coinages.

## Updating This List

When you encounter a new AI pattern in the wild:
1. Add it to the appropriate tier above
2. Add the grep pattern to `../scripts/detect-lexical.sh`
3. Test against known-clean files to verify no false positives
