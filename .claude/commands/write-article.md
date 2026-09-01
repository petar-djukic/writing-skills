# Command: Write Article

## Goal

Complete a Substack article from a brainstorm file or outline. Research supporting data, verify sources, and produce a publication-ready article following Petar's coaching voice and writing standards.

## Usage

```
/write-article [brainstorm-filename]
/write-article [path/to/existing-draft.md]
```

- **With brainstorm filename**: Write article from specified brainstorm file (e.g., "context-engineering")
- **With a path to an existing article**: rewrite mode — skip steps 1-3 and run the
  quality pipeline (step 6) over the file as it stands
- **No parameter**: Prompt user to select from available brainstorm files

**This command owns rewriting too.** "rewrite article", "rewrite the article",
"redo this article", "run the passes on this draft", and "clean up this draft"
all mean this command. Do not ask which command was meant, do not say the
command is for writing rather than rewriting, and do not offer to do it
manually instead. If the target is an existing file, go straight to step 6.
If no target is named, ask which article — that is the only question worth
asking here.

## Persona

You are writing as Petar Djukic in the voice of Muriel Wilkins - calm, observational, coaching-style. You help readers see patterns and make their own decisions. You don't prescribe; you illuminate.

## Context

### Writing for

- **Primary audience**: Software engineers and engineering leaders
- **Secondary audience**: Technical decision-makers
- **Focus**: Practical wisdom from production experience
- **Value**: Pattern recognition and systemic insights

### Author Background

Petar is a Principal Network Architect with:

- 20+ years building production AI/ML systems
- PhD in Computer Engineering, 64 US patents
- Hands-on builder specializing in agentic orchestration
- Current focus: Architecture-First Development and context engineering

Key experiences to draw from:

- Building MCP server and agent (8K lines in 4-5 hours with Claude) - mcp-calc project
- Orchestrating multiple Claude Code instances for agentic workflows
- Using Beads system for AI-assisted development
- Shipping production ML systems that delivered measurable business impact

## Process

### 1. Load Brainstorm File

Read the specified brainstorm file from `substack/brainstorm/`:

- Understand the title, hook, and main argument
- Review the outline and structure
- Note concrete examples to include
- Identify research needs

**Load the article constitution.** The brainstorm file declares its form
with a `Form:` line (how-to, concept-essay, field-report, or
macro-observation). Read the matching contract from the writing
repository's `constitutions/articles/` before drafting — it states what
each section owes the reader, the opening/figure/reference contracts, and
the form's known failure modes. If the brainstorm has no `Form:` line,
pick the form using that directory's `README.md` and record the choice in
the brainstorm file. The draft must satisfy every [CHECK] item; [READ]
items are for the critic pass to adjudicate.

The constitutions are a per-repository input, not something this
repository ships: discover them by walking up from the article file, the
rule `writing-voice/` and `.secrets/` already use. Absent, draft to the
brainstorm's outline and the pattern-language move alone, and record in
the completion note that no constitution was found — the section contract
is then unenforced, which is a weaker draft, not a failed one.

**Load the pattern language.** The brainstorm file declares `Altitude:`
and `Move:` lines (see `substack/pattern-language.yaml`). Read the
declared move's full entry before drafting and hold it alongside the
constitution — the form is the container, the move is what happens inside
it:

- `grammar.requires` names inputs that must exist before drafting starts
  (a `telecom-rhyme` draft without an established ledger read is not
  ready; a `workflow-artifact` without receipts is content marketing).
- `grammar.contains` lists the sentence-level signatures to deploy —
  their entries carry the budgets: one `portable-test` per article, one
  `short-anchor` per major section (more converges on the antithesis
  cadence the filter-tells pass flags), at most one `family-cameo`, and
  `self-implication` before any organizational critique.
- The move's `consequences.liabilities` are the failure modes to check
  the draft against before calling it done.

If the brainstorm predates the pattern language and has no `Altitude:` or
`Move:` lines, classify it now and record the lines in the brainstorm
file before drafting.

If no file specified:

- List available brainstorm files
- Show development stage of each
- Prompt user to select one

### 1a. Check Current Marketing Context

Read `career/marketing/substack-instructions.md`:

- Note which articles are already published (to avoid duplicating ground already covered)
- Check the Draft Pipeline table to understand where this article fits in the queue
- Confirm the current positioning language ("Architecture-First Development," not "Spec-Driven Development")
- Use the Published Articles section to identify cross-reference opportunities with live URLs

### 1a. Load the Voice Anchors

Read `substack/writing-voice/manifest.yaml` and pull a few `author-voice`
anchors before drafting a sentence:

```bash
python3 .claude/skills/match-structure/scripts/voice_anchors.py anchors \
  --text - --voice-dir substack/writing-voice -k 3 --role author-voice
```

Pipe the hook or thesis in on stdin. Anchors are cheap to read now and expensive
to retrofit in step 6 — a draft written toward the voice needs less repair than
one rewritten into it.

The exemplars are the author's pre-AI papers, not the published Substack posts.
Anchoring on published posts is circular: they were themselves AI-assisted.

### 1b. Review Background References (Optional)

Check `substack/BACKGROUND/` for relevant context:

- Articles from other authors (Steve Yegge, etc.) that Petar found valuable
- Use for understanding current conversations in the field
- Reference external perspectives where appropriate
- Do NOT copy - use for context and inspiration only

### 2. Research Supporting Data

**IMPORTANT**: You must research real data before writing.

For each claim or insight in the article:
- Search for supporting statistics, studies, or reports
- Verify that sources are credible (academic, industry reports, reputable publications)
- Check that URLs work and content matches what you cite
- Prefer recent data (2023-2026) unless historical context matters

**Research targets:**
- Academic papers (Google Scholar, arxiv.org)
- Industry reports (MIT, S&P Global, Gartner, Forrester)
- Government statistics (BLS, Census, international agencies)
- Technical analyses (IEEE, ACM, industry research groups)
- **Substack peers (lean into this).** Search Substack for other writers
  making an adjacent argument and cite the strong ones — carry forward any
  "Supporting materials — Substack" candidates the brainstorm collected.
  Linking a Substacker notifies them and can bring a restack and their
  audience, so treat it as a growth lever, not just a citation. Verify every
  quote against the source before it goes in (short, attributed), and prefer
  high-reach, on-topic writers.

**Verification checklist:**
- [ ] Can you access the URL?
- [ ] Does the source say what you claim it says?
- [ ] Is the source credible and recent?
- [ ] Do the numbers/dates match your citation?

### 3. Write the Article

Follow this structure:

#### Front Matter (YAML)

```yaml
---
title: [Catchy title under 70 characters]
subtitle: [Descriptive subtitle explaining the value]
date: [YYYY-MM-DD - target publication date]
author: Petar Djukic
tags: [relevant, keywords, for, searchability]
illustration_prompt: "[ChatGPT prompt for black and white stick figure illustration - describe the concept visually, may be humorous]"
linkedin_post: "[35 words or less - state the pattern/problem, state the insight/solution, end with period. No call-to-action, no 'here's why', no flexing]"
---
```

**Important metadata notes:**
- `illustration_prompt`: Describe a simple, clear visual concept for article illustration. Black and white stick figures work well. Show contrast (structure vs chaos, etc.)
- `linkedin_post`: Must be 35 words or less. Direct and professional. State the problem/pattern, state the solution/insight, end with period. NO call-to-action phrases ("Here's why:", "Read more:", etc.). NO personal achievement focus. Pattern-focused only.
  - Example: "Two AI traps: endless iteration or treating it like a junior developer. The fix? You architect, AI implements."
  - Example: "AI hallucinates C++ templates but generates reliable Go. After 20 years of C++ mastery, I switched languages. The new calculation: what can AI build consistently, not what you prefer."

#### Three-Sentence Summary

After the YAML front matter, before the title, add a bold 2-3 sentence summary:
- Captures the main traps/problems
- States the solution methodology
- Establishes value proposition

Example:
```markdown
**Most engineers using AI tools fall into two traps: the endless iteration "casino loop" or treating AI like a junior developer who needs constant supervision. The solution isn't better AI—it's better methodology: define your architecture first, decompose it into small issues, then let AI implement each piece while you maintain the system vision.**
```

#### Opening Hook (2-3 sentences)

Immediately capture the pattern or insight:
- What is the reader experiencing?
- What pattern are they not seeing?
- Why does this matter?

#### Body Structure

**Pattern recognition approach:**
1. **Describe the symptom**: What readers are experiencing
2. **Reveal the pattern**: The systemic issue they're not seeing
3. **Provide concrete examples**: Real situations from production experience
4. **Show the implications**: What this means for their work
5. **Offer perspective**: How to recognize and respond (not prescribe solutions)

**Writing guidelines:**
- Use active voice and concrete language
- Vary sentence length for readability
- Make key points stand out at sentence ends
- Include specific examples over abstract explanations
- Use "you" to engage directly with reader
- Maintain calm, observational tone throughout
- **Focus on patterns, not achievements**: Frame insights as discovered patterns, not personal accomplishments. Less "I built X" and more "Here's what works"

#### Subscribe Placement

Mark subscribe-block positions in the draft with an HTML comment
(`<!-- subscribe-block -->`) so the person pasting into Substack knows where
the editor blocks go. The measured failure mode (2026-08-09 audit): articles
asked before the value (~5% depth) and after the references (~92%), leaving
the entire payoff — where a search visitor actually reads — with no capture
point, and lifetime conversion at 3 signups.

- One marker **right after the first complete payoff** — the first section
  where the reader has something working — typically 40-50% of the article.
- Articles over ~3,000 words get a second marker near two-thirds.
- Keep the early captioned block and the default end block; the markers add
  the middle, they do not replace the ends.
- Caption stays the standing one (free subscription, leg up); never
  invent urgency copy.

#### References Section

Include 4-7 credible sources:

```markdown
## REFERENCES

[1] Author, A., et al. (YYYY). Title of Work. Publisher/Organization.

[2] Organization (YYYY). Report Title. Publication Name.

[Continue for 4-7 sources]
```

### 4. Apply Writing Standards

**Voice and tone:**
- Calm and observational (like Muriel Wilkins)
- Inquiry-driven, not prescriptive
- Direct and concise
- Sometimes humorous, always assertive
- **No flexing**: Focus on patterns and methodology, not personal achievement
- **Pattern over accomplishment**: "Here's what works" not "Look what I did"
- Frame discoveries as "I found myself following a pattern" not "Here's my system"

**Distinct voice — do not sound like generic Substack:**
The writing must be distinguishable from the median tech newsletter. If a sentence could appear unedited in a McKinsey deck, a YC blog post, or a LinkedIn thought leadership post, rewrite it.

- No empty identity labels: "technologist," "builder," "innovator," "thought leader"
- No generic opener patterns: "In today's landscape...", "The future of X is...", "Here's what I've learned:", "Let's unpack this."
- No corporate filler: "leverage" (say "use"), "ecosystem," "at scale," "unlock," "reimagine," "paradigm shift," "best practices," "game-changing," "transformative"
- No self-congratulation: "exciting," "fascinating" when describing your own work
- Specificity is the antidote: a concrete number, a named tool, a real situation beats any of the above

**Technical standards** (from the writing repository's voice rules,
`rules/substack-writing.md`, where it provides them):
- No bold text, excessive italics, or horizontal rules
- Support all claims with evidence

The banned-word list, the AI-pattern catalog, and the concision and active-voice
rules are **not restated here**. They belong to the skills that measure them:
`filter-tells` owns the banned words and the AI patterns (its catalog is
`references/banned-patterns.md`), `tighten-style` owns concision, buried verbs,
and paragraph spine. Duplicating their rules here means two copies that drift.
Write well by instinct at this stage; step 6 measures it.

Before drafting, read `.claude/skills/filter-tells/references/drafting-guidance.md`.
Preventing the tells while drafting is cheaper than repairing them in step 6.

**Self-contained articles:**
- Every article must stand on its own. A reader may never have read any other article in the series.
- When referencing a concept from another article, explain it briefly in-line before linking. The link is supplemental, not required.
- Never assume the reader knows what "the casino loop," "the architecture-first approach," or any other coined term means. A single clause of context is enough — "the casino loop — endless iteration with no stopping point —" lets the reader follow without clicking away.
- Cross-references should add depth for returning readers, not create confusion for new ones.
- **Per-mention catalog sweep**: when the draft first mentions a topic an already-published article covers, link that article in prose with a descriptive keyword anchor. The in-line gloss rule above stands — the link supplements the gloss, never replaces it. Ceiling: ~5-8 in-prose internal links per article; past that, keep the strongest. Articles are born linked; the seo-pass is the catcher, not the source.
- **Self-citation rule**: citing one of our own articles only as a bare-URL numbered reference is the SEO-weakest internal link. The in-prose descriptive link at the in-text mention is required; the numbered entry is optional alongside it.

**Content requirements:**
- Align with Petar's documented experience
- Use concrete examples from production systems
- Include proper research citations
- Verify all links work
- No confidential employer information
- No names of co-workers or internal projects

### 5. Save the Article

**File location:**

- Save to: `substack/[YEAR]/drafts/[YYYY-MM-DD]-[title-in-kebab-case].md`
- Year is from the publication date
- Date is the target publication date
- Title uses kebab-case (lowercase with hyphens)
- Articles go to **drafts/** first — they are published by the `/publish-article` skill

**Example:**
- Date: 2026-03-15
- Title: "The Hidden Cost of AI-Assisted Refactoring"
- File: `substack/2026/drafts/2026-03-15-the-hidden-cost-of-ai-assisted-refactoring.md`

### 6. Run the Quality Pipeline

The draft is now on disk. Everything below runs against that file. This is
also the entry point for rewrite mode — when `/write-article` is given an
existing article path, start here.

This command owns *when* things run and what is substack-specific.
`humanize` owns the chain — its stages, their order, their models, and the
measurements behind them (writing-skills GH-208). Nothing below restates a
stage invocation or a model name: every time this file did, it drifted.

**The rule that outranks every other rule here: Claude does not write a
word that ships.** Not a paragraph, not a repair, not a transition. Claude
picks anchors, reads findings, judges results, and decides what to keep —
analysis, never article text. Every shipping sentence comes out of the
rewrite transport. Measured 2026-07-26: the same tightening applied by
Claude took a 0.0% draft to 77.9%, and every span Claude authored scored
0.96–0.99 on its own. The evidence lives with the owning skills:
[hand-tightening-regression.md](../skills/tighten-style/references/hand-tightening-regression.md)
and
[authorship-lever.md](../skills/match-voice/references/authorship-lever.md).

#### 6a. Commit the baseline

Pangram consent is standing for this repository (writing-skills GH-210:
the operator's grant is recorded in `writing-voice/pangram-consent.yaml`),
so the drivers score every stage by default and no per-run consent dance
is needed; `--no-pangram` opts a run out, and the embargo/NDA refuse-list
in the writing-voice rule still applies. What cannot be deferred is the
baseline commit:

```bash
git add "$ART" && git commit -m "draft: <slug> (pre-pipeline baseline)"
```

**Commit after every stage below.** The commit trail is the record of what
each stage changed — `git diff` between two stages answers "what did
tighten-style actually do" without rerunning anything. Use the stage name
in the message (`filter-tells: <slug>`, `match-voice: <slug>`,
`tighten: <slug>`, …); `rebuild-lifecycle.py` keys on those subjects. Do
not squash them; the separation is the point.

#### 6b. Structure, when the form needs changing

The chain does not restructure (humanize's input contract). When the
draft's shape is the problem — assertion ladders, a form mismatch —
invoke `match-outline` with a blueprint before the chain. Writing the
blueprint is Claude's job (analysis; it never reaches the article);
applying it is the tool's. Verify content preservation afterwards per
match-outline's SKILL — citations, numbers, quotes, references, **and
figure blocks**, which its built-in check does not cover. Two reproducible
facts to steer the decision: concrete passages dense with identifiers come
back unflagged while abstract argument scores 0.96+, and an assertion
ladder scores 0.98–0.99 with or without its bold — it is the shape, not
the markup.

#### 6c. The chain

```
/humanize <article.md>
```

That is the whole invocation. The skill runs filter-tells, the seeded
match-voice recipe, tighten-style, the optional accent and burstiness
stages, the scoped recheck, and the terminal stage, measuring as it goes;
it reports seed reach and per-stage scores. Commit each stage's output as
it lands.

#### 6d. The review phase

Read-only instruments over the chain's output, in this order:

1. **reverse-outline** — annotate + rank; the markers ride in the text
   and survive the Substack paste (see step 8).
2. **critic-panel** — the `article` roster is required (operator request,
   2026-09-01). Commit the sheet beside the article
   (`<stem>.critic-sheet.md`), then apply it with the `critic-apply`
   skill — pass the constitution's protected spans and the
   reverse-outline cheap ranks; it owns the rules, the gate, and the
   applied/kept/declined-by-rule counts the `generation:` block wants.
3. **Cold review** — invoke the `cold-review` skill: run its mechanical
   `screen` for the reviewer's recall aid, spawn the fresh-context
   reviewer with its prompt template (name the high-value targets), and
   apply accepted verdicts with its `apply` — every accepted fix is a
   verbatim revert to the baseline span, no authored prose.
4. **voice-critic** — stance, marker profile, snark governance; flags to
   the author gate.

Critic picks and author edits are unlaundered prose. Decide whether to
re-enter the chain on humanize's seed-reach report: when the seed can
still move the text, cycle; when it cannot, the article has converged and
further passes only shuffle detector buckets.

#### 6e. Where the candidate lands — one path, always

The accepted rewrite goes to **`<article>.rewrite-candidate.md`**, next to
the published article. That exact name, every time. Do not encode the run
in the filename — not the model, not the anchors, not the date. A second
rewrite **overwrites that file and commits over it**: generations are
commits, not filenames. Three things break the moment the path moves, all
observed: `substack/article-lifecycle.yaml` stores a SHA per phase and
needs a stable path; `rebuild-lifecycle.py` mines `git log --follow` and a
rename severs the chain; and `git diff <old>:<path> <new>:<path>` stops
working across two names. The model, anchors, and scores belong in the
`generation:` block, which travels with the file.

#### 6f. Record generation provenance in the front matter

Write the run's inputs into the article's YAML front matter under a
`generation:` block — standing requirement (idea-factory 2026-07-26). One
list entry per stage that ran, mirroring humanize's run-completeness
check: stage name, model, the anchor selection with **`anchor_files`**
(the reason the block exists — they otherwise die with the run's temp
dir), a one-line note on what changed, and per-stage accepted/kept counts.
Head it with `method:` and `run_date:`; end with the `pangram:` block
(scope, before, after) when scans ran — omit the block entirely when they
did not, because an absent block reads "not measured" and a zero reads
"measured clean". If a stage was skipped, drop its entry rather than
inventing a value. Commit.

#### 6g. Refresh the article lifecycle ledger

```bash
python3 substack/scripts/rebuild-lifecycle.py
```

It mines `git log --follow` and merges — appends only commits the entry
lacks, never clobbers hand-authored fields, safe to re-run. Then promote
this article's entry to `confidence: authoritative` and add what git
cannot see: the `pangram` before/after and the match-voice `anchors` line
(mirroring the `generation:` block). Commit the ledger.

#### 6h. Read the measurement

Carry humanize's report into the completion note along with the
still-flagged paragraph list — the worklist for another cycle. Reading
rules, all standing:

- **Hold one Pangram framing per comparison** (slice / whole / prose-only
  are not comparable) and date every verdict; rankings are model ×
  pipeline and rot when either changes.
- **No pass threshold.** The only constant in the code is
  `FLAG_SCORE = 0.5`, whose own comment says it is uncalibrated triage.
  Pangram publishes no accuracy figures; a `Human Written` result does
  not certify an article and a bad score does not condemn one.
- **A favourable score is the weakest evidence in the pipeline** — the
  rewrite was steering around detectors, so their silence is close to
  tautological. The human call at the end outranks every metric here; on
  two past articles the metrics pushed the writing the wrong way, and
  stopping was correct.

### 7. Delete Brainstorm File

After writing the article:

- Delete the brainstorm file from `substack/brainstorm/`
- The article is now the source of truth
- No need to maintain both the brainstorm and published article

### 8. Provide Publishing Checklist

After saving, provide this checklist:

```markdown
## Paste checklist additions

- **HTML comments need no stripping.** Substack drops them on paste —
  measured 2026-08-23 on a full paste-over of an article carrying 83
  reverse-outline `rst:` markers and 6 lock spans. Leave them in; the
  markers then survive in the repo copy to feed `reverse-outline audit`
  after the next revision, which is the point of persisting them.
- **The `<!-- SUBSCRIBE BLOCK -->` comment is different**: it is a cue to
  the author, marking where to insert the subscribe-button block by hand
  in the editor. Act on it, then it disappears with the rest of the
  comments.

## Draft Checklist

- [ ] Title is catchy and under 70 characters
- [ ] Subtitle clearly explains the value
- [ ] Three-sentence summary added in bold after YAML
- [ ] Opening hook is 2-3 sentences and engaging
- [ ] Article uses calm, observational voice (no flexing)
- [ ] All claims are supported by evidence
- [ ] 4-7 credible sources cited
- [ ] All URLs verified and working
- [ ] Catalog sweep done: first mentions of previously-covered topics linked in prose (count reported), self-citations carry prose links
- [ ] No confidential information disclosed
- [ ] Structure decision recorded: match-outline run with content preservation verified (citations, numbers, references, quotes, figure blocks), or skipped with the reason
- [ ] `/humanize` run end to end; its run-completeness check and seed-reach line attached
- [ ] No Claude-authored prose in the shipping text — every rewrite and repair went through the rewrite transport
- [ ] Review phase run: reverse-outline, critic-panel applied by rule, cold review in a fresh subagent, voice-critic
- [ ] Pangram before/after reported with its framing named, or explicitly skipped and why
- [ ] `generation:` front-matter block written (method, per-stage models, match-voice `anchor_files`, pangram before/after or omitted)
- [ ] Stage commits present in git log (one per pipeline stage, unsquashed)
- [ ] Examples are concrete and from production experience
- [ ] Illustration prompt added to YAML (black and white stick figure concept)
- [ ] LinkedIn post added to YAML (35 words or less, pattern-focused)
- [ ] Saved to substack/[YEAR]/drafts/ folder
- [ ] Brainstorm file deleted
- [ ] No TODO comments remaining

**Next Steps:**
1. Use `/publish-article` to review and publish when ready
```

## Requirements

### Content Quality

**Must include:**
- Personal experience from production systems
- Concrete, relatable examples
- Pattern recognition (not prescriptive advice)
- Supporting research (4-7 sources)
- Calm, coaching voice throughout

**Must avoid:**
- Abstract technical explanations
- Prescriptive solutions
- Unsupported claims
- Confidential information
- AI-recognizable writing patterns
- Prohibited words and phrases

### Research Standards

**All sources must:**
- Be accessible via provided URL
- Be credible (academic, industry, reputable publishers)
- Actually support the claims made
- Be properly cited with author, year, title, publisher
- Be recent unless historical context is needed

**Never:**
- Invent statistics or studies
- Cite sources you haven't verified
- Misrepresent what a source says
- Use broken or paywalled links without noting it

## Ask for Further Input

During the writing process, you may need to ask:

1. **Example clarification**: "Which specific production experience should we use to illustrate [pattern]?"
2. **Research direction**: "I found studies on [topic A] and [topic B]. Which better supports the argument?"
3. **Tone check**: "Does this section feel too prescriptive? Should I make it more observational?"
4. **Scope decision**: "This could go deeper into [technical detail]. Keep it concrete or explain more?"

## Explain Why

After completing the article, explain:

- **Research choices**: Why you selected these particular sources
- **Structure decisions**: How the flow serves the coaching voice
- **Example selection**: Why these concrete examples work
- **Length and depth**: Why you stopped where you did

## Limits

**Never:**
- Make up research or statistics
- Cite sources you can't verify
- Include confidential business information
- Name specific co-workers or projects not already public
- Prescribe solutions instead of revealing patterns
- Use AI-recognizable writing patterns
- Include prohibited words or overused phrases

## Example Workflow

```bash
# User invokes with filename
/write-article context-engineering

# You execute:
# 1. Read brainstorm/context-engineering.md
# 2. Research supporting data for claims
# 3. Verify all sources and URLs
# 4. Write article following structure
# 5. Apply writing standards
# 6. Save to substack/2026/2026-03-15-context-engineering.md
# 7. Update brainstorm file
# 8. Provide publication checklist

# Or without parameter:
/write-article

# You respond with:
# Available brainstorm files:
# 1. context-engineering.md (outline ready)
# 2. scaling-ai-assisted-development.md (partial draft)
# 3. agentic-learning.md (title only)
#
# Which would you like to write?
```

## Success Criteria

A successful article includes:

- [ ] Declared Move executed per its pattern-language entry: required inputs present, contained signatures deployed within their budgets, liabilities checked
- [ ] Proper YAML front matter with all fields (including illustration_prompt and linkedin_post)
- [ ] Three-sentence summary in bold after YAML
- [ ] 2-3 sentence opening hook
- [ ] Calm, observational voice throughout (no flexing, pattern-focused)
- [ ] 3-5 main sections with clear narrative flow
- [ ] Concrete examples from production experience
- [ ] Pattern recognition without prescription
- [ ] 4-7 properly cited, verified sources
- [ ] All URLs tested and working
- [ ] Catalog sweep run: first mentions of previously-covered topics linked in prose with descriptive anchors (≤ ceiling), self-citations carry prose links
- [ ] No confidential information
- [ ] Quality pipeline run end to end: structure decision, /humanize, review phase
- [ ] AI level reported before and after, or the skip stated
- [ ] Illustration prompt for visual concept (black and white stick figures)
- [ ] LinkedIn post 35 words or less, pattern-focused not achievement-focused
- [ ] Saved to correct file location
- [ ] Brainstorm file deleted
- [ ] Publication checklist provided

## Notes

- **Voice is everything**: The calm, coaching tone is what makes these articles distinctive
- **Concrete beats abstract**: Readers connect with real examples, not theory
- **Research builds trust**: Proper citations show you've done the homework
- **Pattern recognition over prescription**: Help readers see; let them decide
- **Experience is the authority**: Petar's 20+ years in production systems is the credibility
