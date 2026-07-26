# Chain-of-Thought Leakage Patterns

CoT leakage is text that exists only to help the model generate subsequent text. It serves the model's reasoning process, not the reader. By definition, a CoT leak is superfluous and should be deleted.

A separate case is **CoT-style wording**: genuine content expressed using scaffolding phrases the model defaults to ("in other words," "it is worth noting"). The content is real, but the phrasing is a tell. These instances should be reworded to remove the scaffolding while preserving the content.

## Category 1: Meta-Discourse (Model Announcing Its Plans)

The model tells the reader what it's about to do instead of doing it.

```
"In this section, we will explore..."
"Let's now turn our attention to..."
"Let's consider..."
"Let me explain..."
"Before we proceed, it's important to..."
"To understand this, we need to first..."
"We'll examine this in three parts..."
"Having established X, we can now..."
"With this foundation in place..."
"Now that we've covered X, let's move to..."
```

**Why it's CoT leakage:** Human writers don't narrate their own writing process. They just write the content.

**Fix:** Apply the superfluity test: remove the sentence, re-read the paragraph. If no information is lost, delete it. If the meta-sentence wraps unique content, extract the content and restate without the scaffolding.

## Category 2: Reasoning Connectives (Model Showing Its Chain)

The model externalizes internal logical steps that should be implicit.

```
"It's worth noting that..."
"It's important to note that..."
"It bears mentioning that..."
"This means that..."  (when the implication is already obvious)
"In other words..."   (model restating what it just said)
"To put it differently..."
"Simply put..." / "To put it simply..."
"What this tells us is..."
"The implication here is..."
"This is significant because..."
```

**Why it's CoT leakage:** The model is annotating its own reasoning process. A human would either make the connection implicit or integrate it into the argument structure.

**Fix:** Apply the superfluity test: remove the phrase, re-read the paragraph. If the implication is obvious from context, delete. If the connective bridges ideas that would otherwise seem unrelated, replace with a content-bearing transition embedded in the argument flow.

## Category 3: Balanced Hedging (Model's Uncertainty Externalized)

The model produces artificially balanced "on one hand / on the other hand" structures because its training optimizes for appearing fair rather than making a point.

```
"While X is true, it's also worth considering Y..."
"On one hand... on the other hand..."
"One might argue that..."
"Some might say..."
"This is not without its challenges..."
"However, it should be noted that..."
"That said, there are also..."
"To be fair..."
"It's a double-edged sword..."
```

**Why it's CoT leakage:** The model's internal uncertainty about what position to take manifests as externalized "both-sides" framing. Human writers with expertise take positions.

**Fix:** Take a position. If genuinely uncertain, say why specifically rather than using generic hedging frames.

## Category 4: Enumeration Scaffolding (Model's Planning Structure)

The model explicitly numbers its points in a way that reveals internal list-generation.

```
"First... Second... Third... Finally..."
"There are three main reasons..."
"There are several factors at play..."
"The key takeaway is..."
"To summarize..."
"In summary..."
"In conclusion..."
"The bottom line is..."
```

**Why it's CoT leakage:** The model is showing you its internal outline. Human writers integrate points into flowing prose unless the enumeration itself adds clarity (e.g., step-by-step instructions).

**Fix:** Fold enumerated points into paragraphs with natural transitions, unless the content is genuinely a procedure or specification.

## Category 5: False Emphasis (Model Signaling Importance)

The model uses adverbial emphasis to signal "this is the important part" because it can't rely on structural emphasis.

```
"Crucially,..."
"Notably,..."
"Importantly,..."
"Significantly,..."
"Remarkably,..."
"Interestingly,..."
"Essentially,..."
"Fundamentally,..."
"At its core,..."
```

**Why it's CoT leakage:** The model is tagging its own output with importance markers, a habit from training on annotated reasoning. Human writers use sentence structure and position to create emphasis, not adverbial flags.

**Fix:** Delete the adverb. If the point is important, its position in the text and its content should make that clear.

## Category 6: Completion Artifacts (Model Acknowledging Limits)

The model reveals awareness of its own generation process.

```
"As mentioned earlier..."
"As noted above..."
"As discussed previously..."
"As we've seen..."
"Recall that..."
"It's beyond the scope of this document to..."
```

**Why it's CoT leakage:** The model is tracking its own output context window. While "as mentioned earlier" can appear in human writing, AI uses it with much higher frequency because it's managing coherence explicitly.

**Fix:** Either remove (the reader remembers), or integrate with a forward reference: "The constraint from Section 2 applies here..."

## Category 7: Bridge Sentences (Model Laying Track)

The model places a sentence at the end of a paragraph (or start of the next) whose only purpose is to connect the current discussion back to the paper's topic so the model can continue generating. The sentence looks like a conclusion or implication but carries no information the reader needs — the preceding paragraph already made the point.

```
"A network management system that achieves L4 or higher must exhibit all three."
"This has direct implications for how we design autonomous systems."
"These properties are essential for any system aiming at full autonomy."
"This is exactly the capability that L4 demands."
"All of this points to the need for a new architectural approach."
```

**Why it's CoT leakage:** The model needs to steer itself from a digression (e.g., an example from another domain) back to the paper's main argument. A human writer trusts the reader to make the connection; the model inserts a bridge sentence so it can pick up the thread in the next paragraph.

**Detection cue:** The sentence appears at a paragraph boundary, restates a point the paragraph already made, and if removed the surrounding text reads better — the transition becomes implicit and the prose tightens.

**Fix:** Delete. The paragraph's own content provides the connection.

## Category 8: Negation-Setup (Model Defining by Exclusion)

The model states what something is NOT before stating what it IS. The negation sentence carries zero information; the affirmative sentence says everything.

```
"An agent is not a monolithic piece of software. It is a logical concept..."
"This is not a trivial distinction. It determines..."
"The answer is not a single algorithm. Rather, it is..."
"Autonomy is not merely a matter of automation. It requires..."
"This framework is not a standard. It is a collaborative..."
```

**Why it's CoT leakage:** The model uses negation as a runway to generate the affirmative claim. Human writers state what something *is*. If the contrast matters, they embed it ("An agent, far from monolithic, is a logical concept...") rather than dedicating a standalone sentence to the negation.

**Detection cue:** A sentence containing "is not a", "is not merely", "is not just", or "is not simply", followed immediately by a sentence that states what the thing actually is. Also includes "not X but Y" within a single sentence ("an agent is not a monolithic program but an orchestrator"). Both forms read as AI to a trained eye.

**Fix:** State what the thing *is* directly, dropping the negation. If the contrast carries genuine information, use "rather than" or fold into a subordinate clause. For standalone negation sentences, delete and let the affirmative speak for itself.

## Category 9: Property Announcement (Model Labeling Before Elaborating)

The model declares an abstract property in a short sentence, then elaborates in the sentences that follow. The announcement adds nothing the elaboration does not convey.

```
"This composition is dynamic."  (next sentence explains how)
"The architecture is modular."  (next sentence explains the modules)
"This distinction is important."  (next sentence explains why)
"The implications are significant."  (next sentences describe them)
"This approach is powerful."  (next sentences demonstrate it)
```

**Why it's CoT leakage:** The model generates a topic sentence as scaffolding to steer subsequent generation. Human writers let the elaboration speak for itself, or integrate the property claim into the elaboration ("The agent's composition changes at runtime: when it encounters a step...").

**Detection cue:** A short sentence (fewer than 8 words) consisting of subject + copula + adjective, followed by longer sentences that substantiate the claim. Apply the removal test: delete the short sentence. If the paragraph reads better without it, the sentence was scaffolding.

**Fix:** Delete. If the property claim needs to be preserved, fold it into the first sentence of the elaboration.

## Category 10: Wh-Cleft Constructions (Model Building a Runway)

The model uses "What X is/does/means is Y" to generate a topic before the predicate. Human writers state the claim directly.

```
"What separates services from factories is..."
"What distinguishes the agent is..."
"What the framework does not address is..."
"What remains is a practical question."
"What this means is..."
"What changes is..."
```

**Why it's an AI tell:** The wh-cleft gives the model a syntactic scaffolding to plan the predicate while appearing to write a normal sentence. Human writers use wh-clefts occasionally for rhetorical emphasis, but AI uses them at 3-5x the natural rate because they're structurally convenient for generation.

**Detection cue:** Any sentence matching "What [noun phrase] [verb] is [predicate]". High density (more than 2 per 1000 words) is a strong AI signal.

**Fix:** State the claim directly. "What separates X from Y is Z" becomes "Z separates X from Y" or "X differs from Y in Z." If the wh-cleft genuinely adds rhetorical weight (rare), keep it, but only 1-2 per paper.

## Category 11: Imperative Example Introduction (Model Inviting the Reader)

The model introduces examples with "Consider X" or "Imagine X" rather than presenting them directly.

```
"Consider a network that..."
"Consider an example."
"Imagine a scenario where..."
"Take the case of..."
"Suppose a system needs to..."
```

**Why it's an AI tell:** The imperative form is the model's default way of transitioning to an example. Human writers either present the example directly ("A network that encounters...") or use indicative framing ("One deployment encountered...").

**Detection cue:** "Consider" or "Imagine" followed by a noun phrase that introduces a hypothetical or example scenario.

**Fix:** Replace with direct presentation. "Consider an anomaly detection system that X" becomes "An anomaly detection system that X" or reframe as a concrete scenario.

## Category 12: Correlative Conjunctions (Model Balancing Claims)

The model uses "not only X but (also) Y" to present a balanced pair of properties.

```
"not only a human-to-system interface; it is also..."
"not only artifacts but the metadata..."
"not just code but also specifications..."
```

**Why it's an AI tell:** Human writers at natural frequency use "and" or two sentences. The model reaches for correlative conjunctions because they're syntactically elegant and its training corpus is heavy on formal academic prose. Frequency above 1 per 2000 words is suspicious.

**Detection cue:** "not only ... but (also)" or "not just ... but (also)".

**Fix:** Use "and" ("artifacts and the metadata"), two sentences, or restructure to lead with the surprising element.

## Category 13: Enumeration Announcement (Model Counting Before Listing)

The model declares how many items follow before listing them.

```
"Two distinct operations define..."
"Three properties together constitute..."
"There are four pillars..."
"Five constraints make this impractical..."
```

**Why it's an AI tell:** The model plans its output by counting items first, then generating them. Human writers either let the structure emerge (just start listing) or use the count only when it adds rhetorical emphasis ("a single constraint blocks this").

**Detection cue:** A number word ("two", "three", "four", "five") followed by a noun and a verb that introduces a list or classification. Especially suspicious when the next sentences enumerate exactly that many items.

**Fix:** Start with the first item directly, or name the items in the topic sentence rather than counting them. "Two distinct operations define an agent's life" becomes "*Creation* and *update* define an agent's life."

## Category 14: Transitional Steering (Model Navigating Between Ideas)

The model inserts short phrases or sentences that steer from one idea to the next without adding content. They serve as the model's internal rudder, appearing at sentence or clause boundaries.

```
"The question then becomes..."
"With that in mind..."
"That said,..."  (as paragraph opener to introduce counterpoint)
"With this in place,..."
"Given this,..."  (when "this" is already obvious from context)
"This brings us to..."
"This raises the question of..."
"Which brings us to..."
"And so,..."
"And therein lies the problem."
```

**Why it's CoT leakage:** The model needs to signal direction changes to itself. Human writers either let the transition emerge from the content ("But composition has a ceiling") or omit the connective entirely, trusting proximity to signal connection.

**Detection cue:** A short phrase (fewer than 6 words) at sentence start that could be deleted without losing any factual content. Often appears at paragraph boundaries or before a new argument strand.

**Fix:** Delete and let the next sentence speak for itself. If the directional shift needs signaling, embed it in the content: "The question then becomes how factories compose" → "How factories compose is a separate problem."

## Detection Strategy

When scanning for CoT leakage, look for:

1. **Density:** More than 2 instances per 500 words = strong signal
2. **Position:** Sentence-initial position is the strongest tell
3. **Clustering:** Multiple categories appearing together in a paragraph
4. **Removal test:** If deleting the phrase loses zero information, it was scaffolding

## Frequency-Based Signals

Some constructions are legitimate in isolation but become AI tells at high density. These are not CoT leakage per se but frequency signals that indicate AI generation.

| Pattern | Human rate | AI rate | Threshold |
|---------|-----------|---------|-----------|
| Tricolons ("X, Y, and Z") | 1-2 per 500w | 3-5 per 500w | >3 per 500w |
| "rather than" | 0.5 per 500w | 1.5-2.5 per 500w | >2 per 500w |
| "both X and Y" | 0.3 per 500w | 1-2 per 500w | >1.5 per 500w |
| Parenthetical definitions | 1-2 per 500w | 4-6 per 500w | >4 per 500w |
| Passive enabling verbs | 0.5 per 500w | 2-3 per 500w | >2 per 500w |
| "While X, Y..." (concessive) | 0.5 per 500w | 2-3 per 500w | >2 per 500w |
| "whether X or Y" | 0.3 per 500w | 1-2 per 500w | >1.5 per 500w |
| Definitional copulas ("An X is a Y that Z") | varies by genre | stacks in sequences | >3 consecutive |

**Why these matter:** Each is a syntactic shortcut the model defaults to because it is safe, balanced, and high-probability. Human writers use more varied constructions: pairs instead of tricolons, active verbs instead of passive enablers, "instead of" or "over" instead of "rather than," asymmetric claims instead of "both X and Y."

**How to fix:** Replace with the varied alternatives. Break tricolons into pairs or four-item lists. Use "instead of" or restructure. Use active voice with a named actor. Drop the "both" and just use "and."

## Severity Scoring

| Frequency | Severity |
|-----------|----------|
| 1 per 1000 words | Minor (human writers do this occasionally) |
| 1 per 500 words | Moderate (suspicious) |
| 1 per 200 words | High (almost certainly AI) |
| 1 per 100 words | Extreme (raw model output) |
