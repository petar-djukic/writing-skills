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

The draft is now on disk. Everything below runs against that file. This is also
the entry point for rewrite mode — when `/write-article` is given an existing
article path, start here.

**The rule that outranks every other rule in this pipeline: Claude does not
write a word that ships.** Not a paragraph, not a repair, not a transition.
Claude picks the anchors, reads the findings, judges the result, and decides
what to keep — all of that is analysis and never lands in the article. Every
sentence in the published text comes out of the second model family. This was
measured the hard way on 2026-07-26; the numbers are in 6f, and they are not
subtle.

**The chain itself belongs to `humanize`. Do not restate it here.**

This command owns *when* the chain runs and what is substack-specific
about it. `humanize` owns the stages, their order, and the measurements
behind that order. Every time this file restated the chain it drifted:
6b named `match-structure` for a structural rewrite that
[moved to `match-outline`](../skills/match-outline/SKILL.md), 6d described
an unseeded `match-voice` that measures worse than the seeded one, and
the read-only instruments were missing entirely. Invoke the skill:

```
/humanize <article.md>
```

### The processing cycle

Processing is a cycle, not a line. `humanize` carries the full contract;
the shape is:

```
draft
  ┌─> generative chain (humanize: structural step, filter-tells,
  │     SEEDED match-voice, tighten-style, inject-vernacular)
  ├─> read-only zone (reverse-outline annotate + rank, Pangram,
  │     critic-panel, voice-critic)
  ├─> author picks and edits
  └─< repeat the chain while the seed can still move the text
      -> author gate -> publish
```

Three things this command insists on, which the skill cannot know:

| rule | why |
|---|---|
| **Claude writes no word that ships.** | Measured 2026-07-26: the same tightening applied by Claude against the rule catalog took a 0.0% draft to 77.9%. Claude picks anchors, reads findings, judges results, decides what to keep. Every shipping sentence comes from the second model family. |
| **Decide the Pangram measurement before anything is rewritten** (6a below). | The driver scans before it touches a paragraph. Once paragraphs are replaced the baseline is gone and the run can never be measured. |
| **Cold-review every generative stage before believing its score.** | Raw figures evaporated every time they were checked: 0.078 → 0.460, 0.408 → 0.609, 0.167 → 0.391. Survival below ~35% at review means drop the stage rather than keep it for the number. |

**When to stop cycling.** When the seed cannot move the text. Two
indicators, both of which predicted the outcome before the scan confirmed
it: seed reach (19 of 125 paragraphs when the chain worked, 16 of 125 with
36 gate rejections when it failed) and gated survival (51% mid-edit, 35%
well-edited and working, 39% but scoring worse once converged). A
converged article only shuffles between detector buckets.

**Why the structural pass leads.** `match-voice` and `tighten-style` both
rewrite paragraph by paragraph. They will swap every word in a section and
leave its shape untouched — and the shape is what a detector reads. On
how-to-loop-engineering the whole voice+tighten pipeline moved 0.676 to 0.660,
because the section it needed to fix was a ladder of seven bolded assertions
that no paragraph-level pass can see. Dissolving that ladder, and nothing else,
took the same article from 0.249 to 0.163.

**Why tighten-style runs last, and only last.** The upstream skill used to say
run it first — tightening reshapes sentences, so tightening prose about to be
rewritten wastes the pass. That ordering is now wrong for this pipeline, and the
2026-07-26 worktrees run is why.

`match-voice` buys the detectability drop and costs words: 77.8% to 0.0% AI, but
2,378 words to 2,502, sentences 17.0 to 17.8. The draft reads leisurely.
Tightening afterwards gave the words back and held the score — 2,306 words,
sentences 16.5, still 0.0%.

The trap this replaces: the *same* tightening done by Claude against the rule
catalog took a 0.0% draft to **77.9%**. Same article, same rules, opposite
result. The convergence was never Strunk and White as a target — it was Claude
tightening toward Claude's own register. So the pass must run through the second
model family, which is what `tighten.py` now does.

Do not hand-apply the rule catalog to a draft you care about the score of. Read
the findings, let the tool rewrite.

**Invoke each by skill name, not by script path.** Each skill owns its own
invocation details; naming their scripts here is how the next rename turns into
an eight-file edit. The literal commands below appear only where this command
needs a non-default flag.

#### 6a. Decide the AI measurement now, before anything is rewritten

The before/after comparison belongs to `match-voice` in 6d, and it is a single
flag: `--pangram`. But the decision has to be made **here**, because the driver
scans the article before it touches a paragraph. Once paragraphs are replaced
the baseline is gone, and a run started without the flag can never be measured
afterwards.

So ask now, not at 6d. Name three things: the file, that both the article and
the rewritten draft are uploaded to a third party, and that the third party
retains them. **Passing the flag is the consent** — the driver never uploads on
its own, even with a key sitting in the environment.

If the answer is no, or there is no key, everything below runs unchanged and the
report says the check was skipped. That is the normal state, not a degraded one.

One consequence to state plainly when you ask: **6d is conditional, so the
measurement is too.** If the prose comes out of 6c already in voice and
`match-voice` does not run, there is no before/after reading — the number is a
by-product of the rewrite, not an independent audit of the article.

Then commit the untouched draft, so every later diff is attributable:

```bash
git add "$ART" && git commit -m "draft: <slug> (pre-pipeline baseline)"
```

**Commit after every stage below.** The commit trail is the record of what each
skill changed — `git diff` between two stages answers "what did tighten-style
actually do to this article" without rerunning anything. Use the stage name in
the message: `tighten-style: <slug>`, `filter-tells: <slug>`, and so on. Do not
squash them; the separation is the point.

### Measurements and cautions from this repo's runs

**The subsections below are evidence, not procedure.** `humanize` is
authoritative on which stage runs when; what follows is what these
particular articles taught, kept because the numbers are worth having and
are cited in issues. Where a subsection names a stage, read it as "when
this stage runs, here is what happened on our articles" — not as an
instruction to run it in that position.

#### 6b. The structural pass — fix the skeleton first

What a detector reads first is not diction, it is construction. Two things
reproduce on every article measured so far:

- **Concrete passages read human.** The sections dense with identifiers —
  `/gh-issue-pop 42`, `mage analyze`, VISION.yaml, a real code fence — came
  back unflagged while the prose around them scored 0.96 and up. Abstract
  argument is what flags, no matter who writes it.
- **Assertion ladders are the loudest tell.** A paragraph that opens by
  asserting its point, repeated three or more times down a section, scored
  0.98–0.99 with the bold on and 0.99 with the bold stripped. It is the shape,
  not the markup.

So before any paragraph-level pass, restructure against exemplars of the form
the article is trying to be — a how-to against how-tos, an essay against
essays. Write the blueprint first (consensus patterns only; a single author's
tics are not the form), keep it in `substack/writing-voice/blueprints/`, then
run it:

```bash
python3 substack/scripts/struct-rewrite.py \
  --article "$ART" \
  --blueprint substack/writing-voice/blueprints/evans-howto.md \
  --exemplar substack/writing-voice/Evans-2021-how-to-use-dig.md \
  --exemplar substack/writing-voice/Evans-2021-how-do-you-tell-if-a-problem-is-caused-by-dns.md \
  --model gemma4:31b-cloud --out "${ART%.md}.struct.md"
```

Writing the blueprint is Claude's job — it is analysis, and it never reaches
the article. Applying it is gemma's.

The driver rewrites a section's prose paragraphs *together*, which is what lets
openers and transitions change; headings, code fences, images, figure captions,
reference entries, and paragraphs under twelve words pass through untouched. It
returns the original section unchanged if the paragraph count comes back wrong,
so a bad response degrades to a no-op rather than a mangling.

**Verify content preservation before going on**, every time:

```bash
python3 - <<'PY'
import re
o=open("<original>").read(); n=open("<rewritten>").read()
C=re.compile(r'\[\d{1,2}\]'); N=re.compile(r'\b\d[\d,\.]*\b'); s=lambda t: C.sub(' ',t)
print("lost citations:", sorted(set(C.findall(o))-set(C.findall(n))) or "none")
print("lost numbers  :", sorted(set(N.findall(s(o)))-set(N.findall(s(n)))) or "none")
print("refs identical:", o[o.index('## REFERENCES'):].strip()==n[n.index('## REFERENCES'):].strip())
PY
```

That check is not ceremony. The first run of this driver fed the bibliography
to the model, which turned `[3] Cherny, B. (2026)...` into chatty prose and
silently dropped two citations. Verify every quote survives too — the model
will paraphrase inside quotation marks given the chance.

**Known limitation** (and note the section-level rewrite driver has since moved to `match-outline`; `match-structure` now provides metrics and anchor retrieval). `match_structure.py` in the `match-structure` skill does
this job properly but reads its corpus from `references.yaml`, which the
Substack side does not have; `struct-rewrite.py` is the writing-voice-shaped
stand-in. It also hardcoded `claude-opus-4-8` until coding-skills#263 — if you
reach for that skill instead, pass `--model gemma4:31b-cloud` explicitly.

#### 6c. filter-tells

Invoke the `filter-tells` skill on the draft, with the voice profile so the
metrics are read against the author's own distribution rather than a generic one:

```bash
python3 .claude/skills/match-structure/scripts/voice_anchors.py profile --for "$ART"
```

Then run the skill's passes, passing
`--voice-profile=substack/writing-voice/.voice-profile.json` to the structural
detector.

Its semantic pass is **mandatory** unless the lexical and structural scans both
return literally zero. A clean script verdict is not a voice verdict — the
scripts measure shape, not whether the writing sounds like a person. Cap the
repair loop at three iterations, and stop early if the finding count stops
falling.

**Detect with Claude, repair with gemma.** This is where the pipeline leaks
most easily, because the repairs look too small to matter: strike a "worth
noting", drop a "just", rephrase one cliché. On how-to-loop-engineering seven
such edits, applied by hand, moved Pangram **0.753 → 0.775**. Hand-editing a
draft is how Claude's register gets back in, one clause at a time.

So feed each flagged paragraph back through the second model family with the
finding attached, and gate the return:

```bash
# per flagged paragraph: ask gemma to fix the named tell and nothing else,
# then reject the candidate if a citation vanished or the tell survived
```

`substack/scripts/struct-rewrite.py` is the pattern to copy — a narrow prompt,
an explicit rule list, and a mechanical gate that keeps the original when the
response fails it. Findings that are **false positives get no edit at all**:
`critical` inside a quoted source, `key` inside `keynote`, a phrase that was
the author's own in the published text. Record those as dismissed, by rule ID,
rather than "fixing" them.

Commit.

#### 6d. match-voice

Only when the prose reads neutral-but-not-in-voice — which is exactly what 6c
leaves behind. Invoke the `match-voice` skill on the draft.

Two things this command must specify, because the defaults are wrong for this repo:

- **Use a different model family than the one that drafted.** Claude judging a
  Claude rewrite grades its own homework, and decorrelating from the drafting
  model's fingerprints is the whole point. `--model gemma4:31b-cloud`.
- **Pass `--stratum pre-ai`, then check what retrieval actually chose.** Read
  `substack/writing-voice/README.md` first — its title is an instruction.

  ```bash
  python3 .claude/skills/match-voice/scripts/drive.py --article "$ART" \
    --voice-dir substack/writing-voice --stratum pre-ai \
    --model gemma4:31b-cloud --pangram
  ```

  **`--stratum pre-ai` is a safety floor, not the register control.** It keeps
  the 30 AI-era samples out, so a rewrite never anchors diction on machine-era
  prose — the circularity the README exists to prevent. It does nothing else.
  On the current corpus it and the `diction` tag select the identical 113
  exemplars, because the tag was derived from `pre_ai`; there is not one sample
  where they disagree. Treat it as always-on hygiene and stop expecting it to
  shape register.

  **The register problem is anchor concentration, not role.** Earlier guidance
  here said the 24 IEEE papers dominate and that `--role author-voice` makes a
  how-to worse. That was true at 102 exemplars. After the corpus reached 143
  (22 author-voice pre-AI against 91 venue-voice), it no longer reproduces —
  measured on a loop-engineering paragraph, retrieval returns:

  ```
  Yegge-2007-the-next-big-language.md      (x3)
  Yegge-2011-stevey-s-google-platforms-rant.md  (x2)
  DanLuu-2019-hardware-unforgiving.md
  ```

  Zero papers. The failure mode inverted: **retrieval now collapses onto two or
  three near-duplicate files from a single author.** Five of six anchors above
  are Yegge, whose register Petar has explicitly rejected as not his. Anchoring
  a rewrite there imports someone else's voice wholesale — the same failure the
  2026-07-26 Yegge/Beck run produced at 50.5% AI with prose that read as Yegge.

  So inspect the mix before spending the run. The driver prints its pool, not
  its selection, so check the selection directly:

  ```bash
  python3 .claude/skills/match-voice/scripts/retrieve.py \
    --text <paragraph-file> --for "$ART" -k 6 --json
  ```

  If one author holds more than half, or the same file repeats, the anchors are
  concentrated. Widen with a filtered `--voice-dir` built from tags — the
  vocabulary and the query recipes are in the README's Tags section.

  **For how-to articles, use `diction` at full width.** The GH-360 study
  tested 10 tag pools on 3 how-to articles. The Evans-dominated `how-to`
  pool (24 samples) reads best but scores 100% AI on every draft — the
  detector doesn't move. The only proven path to 0% AI (worktrees study)
  used `diction` at full width (113 samples), where retrieval lands on
  Krugman and Dan Luu. That pool moves the detector; tighten-style
  recovers readability afterward. Narrow tag pools optimize the wrong
  axis — Pangram scores, not blind-read comfort, are the binding
  constraint.

  Counts move as the corpus grows. Re-measure rather than trusting the numbers
  written here — that is exactly how this section went stale.

If 6a got consent, add `--pangram` to the driver run. It scans the article
before touching a paragraph, scans the assembled draft at the end, and reports
`fraction_ai` before → after with the paragraphs that moved. Do not try to
assemble that comparison by hand — the baseline is unreconstructible once the
rewrite starts, which is why the flag lives on the driver.

A full comparison costs two scans. **Nothing enforces a per-day quota** — scans
are billed per call against the account's subscription, and `pangram_report.py`
says so in its own header. Treat the cost as a reason to be deliberate, not as
a limit to ration against. A failed baseline scan never blocks the rewrite, and
it means the second scan is not spent either.

The exemplars are IEEE papers, not blog posts. Anchors will read academic. That
is expected — anchors carry register, not content — so do not retry on the
grounds that an anchor looks off-topic.

The skill writes `<article>.vr-draft.md` and never edits the draft in place. That
file holds **candidates, not an accepted draft**: the mechanical gate checks
numbers, citations, and anti-plagiarism, but meaning entailment and register are
separate checks that must be run before anything is spliced back. Report the
per-paragraph accepted / retried / kept-original table.

Commit.

#### 6e. tighten-style

`match-voice` costs words. This pass gives them back without giving back the
score. Run it on the `.vr-draft.md` from 6d, through the same second model
family:

```bash
python3 .claude/skills/tighten-style/scripts/tighten.py \
  --article "${ART%.md}.vr-draft.md" --model gemma4:31b-cloud
```

Writes a sibling `.tight.md`; it never edits in place. `--check-only` reports
per-paragraph rule findings with no model calls.

**Do not hand-apply the rule catalog instead.** Claude tightening against
TS-01/02/04/09/15 by hand took a 0.0% draft to 77.9% — Claude tightens toward
Claude's own register, which is what the detector keys on. The tool routes the
same rules through a different model and holds the score. This is the single
most counter-intuitive result in the pipeline; do not shortcut it.

The tool prints register markers before and after. Watch for **UP** on
`nominalization` or `passive`, and read its own warning: rising markers mean
movement toward the assistant register, the direction a falling AI score can
hide.

Two things this pass does not fix, seen on the worktrees run: `salad_rate` can
*rise* as cutting words concentrates the filler left behind (3.7 → 6.5), and
list-scaffold openers like "Grouping serves two primary purposes. First,"
survive. Both are hand-edits, and hand-edits cost score — make them
deliberately, few, and re-measure.

Commit.

#### 6f. Re-check, cold

Re-run `filter-tells` over the rewritten spans, then hand the final text to a
**fresh subagent** that has not seen the drafting conversation and gets only the
article and the 6d report. Maker is not checker; a model that just rewrote a
paragraph is the worst judge of whether it still reads like a machine.

Commit.

#### 6f-quater. Where the candidate lands — one path, always

The accepted rewrite goes to **`<article>.rewrite-candidate.md`**, next to the
published article. That exact name, every time, for every article and every
generation.

Do not encode the run in the filename — not the model, not the anchors, not the
date. A second rewrite of the same article **overwrites that file and commits
over it.** Generations are commits, not filenames, and git is what tells you
how the candidate changed over time.

Three things break the moment the path moves, all of them observed:

- `substack/article-lifecycle.yaml` stores a SHA per phase and reproduces any
  stage with `git show <commit>:<file>`. That needs a stable path.
- `rebuild-lifecycle.py` mines `git log --follow`; a new name is a delete plus
  an unrelated add, so the chain severs and does not reconnect.
- `git diff <old-sha>:<path> <new-sha>:<path>` — the only way to see what the
  second rewrite actually changed — stops working across two names.

The model, the anchors, and the scores belong in the `generation:` block below,
which is inside the file and travels with it. Putting them in the filename too
is a second copy of the same fact, free to drift.

#### 6f-bis. Record generation provenance in the front matter

The inputs that produced the draft — the match-voice model, and above all the
**anchor exemplar files** — otherwise live only in a temp-dir `results.json`
that is gone after the run. Write them into the article's YAML front matter under
a `generation:` block so the "how" travels with the article. This is a standing
requirement, not optional (idea-factory decision 2026-07-26).

```yaml
generation:
  method: /write-article step-6 rewrite pass   # or "step-1..7 fresh draft"
  run_date: YYYY-MM-DD
  stages:
    - stage: match-structure
      model: gemma4:31b-cloud
      blueprint: <blueprint file, and the form it encodes>
      exemplar_files: [<the exemplars the blueprint was drawn from>]
      note: <what shape changed — ladders dissolved, openers varied>
    - stage: filter-tells
      model: gemma4:31b-cloud       # repairs; detection is Claude's
      note: <verdict, what was repaired, what was dismissed as a false positive>
    - stage: match-voice
      model: gemma4:31b-cloud
      anchor_role: venue-voice            # the role/tags that SELECTED the pool
      anchor_tags: [clipped]
      anchor_selection: <one line on why this pool, what was excluded>
      anchor_files: [<every exemplar filename used>]   # the point of the block
      result: <accepted / kept-original counts>
    - stage: tighten-style
      model: gemma4:31b-cloud
      note: <what it cut>
    - stage: filter-tells-recheck
      note: <cold-subagent findings and disposition>
  pangram:            # omit if not measured; never leave a stale/guessed number
    scope: prose-only
    before: <fraction_ai>
    after: <fraction_ai>
```

Fill `anchor_files` from the pool actually passed to the driver (the filtered
`--voice-dir` when one was built, else the exemplars retrieval selected). If a
stage was skipped, drop its list entry rather than inventing a value. Omit the
`pangram:` block entirely when the scan did not run — an absent block reads as
"not measured", a zero reads as "measured clean", and only one of those is true.

Commit.

#### 6f-ter. Refresh the article lifecycle ledger

`substack/article-lifecycle.yaml` is the brainstorm→publish timeline, one entry
per article, with a git SHA at each phase (reproduce any stage with
`git show <commit>:<file>`). After the stage commits above, refresh it:

```bash
python3 substack/scripts/rebuild-lifecycle.py
```

It mines `git log --follow` and **merges** — appends only commits the entry
lacks, never clobbers hand-authored fields, safe to re-run. Commit subjects are
the log, so keep the stage keyword in messages (`filter-tells:`, `match-voice:`,
`tighten:` …); the script keys on them. Then promote this article's entry to
`confidence: authoritative` and add what git cannot see — the `pangram`
before/after and the match-voice `anchors` line (mirroring the front-matter
`generation:` block). The merge preserves these on re-runs. Commit the ledger.

#### 6g. Read the AI measurement

If 6e ran with `--pangram`, the driver has already reported `fraction_ai` before
→ after. Carry that into the report along with the **still-flagged paragraph
list**, which is the useful half: it is the worklist for another pass, pointing
at the passages the rewrite did not fix.

If the measurement was skipped, say so and why — no consent, no key, or 6d did
not run. Do not present its absence as a clean result.

**Do not write a pass threshold into this pipeline, and do not treat a Pangram
number as a verdict.** The only constant in the code is `FLAG_SCORE = 0.5`, whose
own source comment says it is uncalibrated and meant for triage. Pangram publishes
no accuracy figures and no false-positive rate. A `Human Written` result does not
certify an article, and a bad score does not condemn one.

**Who writes the words is the biggest single lever.** how-to-loop-engineering,
measured 2026-07-26, same four stages and the same anchors throughout — only
the model family changed:

| Pipeline | Pangram AI |
|---|---|
| The published article (baseline) | 0.676 |
| match-structure via `claude-opus-4-8` | 0.753 |
| ...then filter-tells repairs by hand (Claude) | **0.775** |
| match-structure → voice → tighten, all gemma4 | 0.249 |
| ...then gemma dissolves the assertion ladder | 0.163 |
| ...then gemma removes the flagged filler | 0.161 |
| ...then gemma rebuilds the argument tail | **0.146** |

Both Claude passes moved the score *up*, and every span Claude authored scored
0.96–0.99 on its own. The gemma chain took the same article to 0.146 with 85%
of it reading human. Two further findings from that run:

- **Anchors matter far less than authorship.** A Krugman-only pool, a
  Krugman+Evans pool, and the full corpus all landed within a few points of
  each other while Claude was still writing. Choosing anchors is tuning;
  choosing the model family is the decision.
- **Watch for measurement artifacts.** `match-voice` rule 3 preserves bold
  lead-ins and over-applies it, inflating bold openers 11 → 26 on one draft;
  `detect-structural.py` treats bold spans differently, which showed up as a
  fake `sentence_length_std` gain of 9.0 → 11.1 that vanished once the bold
  was stripped. Strip the added bold mechanically (it is formatting, not
  prose, so it costs no score) before believing a rhythm number.

**Know when to stop.** Pangram scores a sliding window, not a paragraph. On the
final draft the five still-flagged paragraphs included the author's own
untouched closer, sitting at 0.95 because of the company it keeps. When the
residual block contains text a human actually wrote, further passes are
optimizing against a windowing artifact and will be paid for in prose.

**Tightening also works against the score, when Claude does it.** Four variants
of the worktrees article — itself an AI draft — measured 2026-07-26:

| Variant | passive | salad | Pangram AI |
|---|---|---|---|
| **Full corpus, `--stratum pre-ai`** | **0.0** | **3.7** | **0.0%** |
| The published draft | 0.0 | 5.5 | 77.8% |
| Rewrite anchored on IEEE papers | 0.5 | 8.3 | 0.0% |
| Rewrite anchored on Yegge/Beck | 0.0 | 3.5 | 50.5% |
| Rewrite anchored on Beck only | — | 3.8 | 66.9% |
| Papers rewrite, hand-tightened by Claude | 0.0 | 7.5 | **77.9%** |
| Stratum rewrite, tightened via `tighten.py` | 0.0 | 6.5 | **0.0%** |

The top row is the target: score and register both improved. Rows two through
five show the tradeoff before the corpus was widened — the only thing that
reached 0% was the unpublishable academic rewrite.

Read the last row carefully. Hand-tightening the 0.0% draft — active voice,
concrete verbs, nominalizations removed, TS-01/02/04/09/15 — drove it back to
77.9%, within a tenth of a point of the untouched draft. **The tightening
undid the entire gain.**

**The mechanism, measured.** Four register markers, per 1,000 words:

| Variant | passive | agentive | nominalization | connectives | AI% |
|---|---|---|---|---|---|
| The AI draft | 2.1 | 0.0 | 17.7 | 0.0 | 77.8% |
| Papers rewrite | **14.0** | **0.4** | **22.6** | **2.9** | 0.0% |
| Yegge/Beck rewrite | 2.7 | 0.0 | 17.0 | 0.4 | 50.5% |
| Papers + tightened | 2.2 | 0.0 | 17.5 | 0.0 | 77.9% |

The tightened row is the drafting model's row. Passive 2.2 against 2.1,
nominalization 17.5 against 17.7, connectives and agentives at zero in both.
Same profile, same score.

The papers rewrite suppressed the score with 6.7x the passive rate, the only
agentive passives in the set, more nominalization, and the only real supply of
"However / Therefore / Moreover". Those four markers *are* TS-02, TS-04, TS-01,
and TS-15. Running tighten-style deletes them by design and lands the text on
the model's baseline.

Distance from the AI draft's full feature vector ranks perfectly inverse to the
score: papers 0.809 → 0.0%, Yegge/Beck 0.636 → 50.5%, tightened 0.623 → 77.9%.

The root cause is a convergence: Strunk and White's prescriptions and
RLHF-tuned assistant prose are now the same style. Instruction tuning rewarded
concise, active, concrete, unhedged writing, which is the rule catalog
`tighten-style` implements. "Improve the prose" and "make it look
machine-written" have become one operation.

**The escape is voice, not polish.** The Yegge/Beck rewrite has the best prose
of all four by the local metrics (`salad_rate` 3.5 against the draft's 5.5) and
still sits at 50.5%, because it keeps a register of its own rather than the
generic-good one. Distinctiveness lowers the score; correctness does not.

What lowers the score is distance from that register. The papers rewrite went
furthest (academic, 0.0%) and reads worst. The Yegge/Beck rewrite went partway
(50.5%) and reads best of the three rewrites.

**Superseded 2026-07-26.** The failure was Claude doing the tightening, not
tightening itself. `tighten.py` routes the same rules through the second model
family and holds 0.0% while cutting 196 words. Run 6e; do not hand-apply.

Two further cautions specific to reading the number:

- **A favourable score is the weakest evidence in the pipeline.** The rewrite was
  steering around detectors; that a detector then stays quiet is close to
  tautological. `filter-tells` cannot settle the question either, for the same
  reason — its denylist is what the rewrite was avoiding.
- The human call at the end outranks every metric here. On two past articles the
  metrics pushed the writing in the wrong direction, and stopping was correct.

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
- [ ] No confidential information disclosed
- [ ] `match-structure` pass run, and content preservation verified (citations, numbers, references, quotes)
- [ ] No Claude-authored prose in the shipping text — every rewrite and repair went through the second model family
- [ ] `tighten-style` findings resolved or dismissed by rule ID
- [ ] `filter-tells` verdict recorded, and it is one of the skill's five verdicts
- [ ] `match-voice` accepted/retried/kept-original table attached, anchor role stated
- [ ] Cold re-check run in a fresh subagent
- [ ] Pangram before/after reported, or explicitly skipped and why
- [ ] `generation:` front-matter block written (method, per-stage models, match-structure blueprint, match-voice `anchor_files`, pangram before/after or omitted)
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
- [ ] No confidential information
- [ ] Quality pipeline run end to end: match-structure, filter-tells, match-voice, tighten-style, cold re-check
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
