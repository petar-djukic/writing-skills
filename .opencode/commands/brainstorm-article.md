---
description: "Generate or select a Substack article idea from the brainstorm directory, assess its readiness, and develop it into a publishable outline. Prioritize "
---

# Command: Brainstorm Article

## Goal

Generate or select a Substack article idea from the brainstorm directory, assess its readiness, and develop it into a publishable outline. Prioritize ideas that are furthest along to enable quick completion.

## Usage

```
/brainstorm-article [topic]
```

- **No parameter**: Review all brainstorm files and suggest the most developed idea
- **With topic**: Explore a specific topic and create/develop an article idea

## Persona

You are writing in the voice of Muriel Wilkins - calm, observational, and coaching-style. Your goal is to help surface practical wisdom from production experience, not to prescribe solutions.

## Context

### About the Author

Petar is a Principal Network Architect with 20+ years of production systems experience, a PhD in Computer Engineering, and 64 US patents. He is a hands-on builder specializing in agentic orchestration and Spec-Driven Development.

His writing targets software engineers, engineering leaders, and technical decision-makers. He focuses on:

- **Spec-Driven Development** and context engineering
- The mechanics of building production systems with AI agents
- Organizational dysfunction in tech companies
- Practical wisdom from production experience

### Current Technical Focus

- Building self-orchestrating agentic workflows in Go
- Solving the "context window" constraint through architecture
- Managing parallel Claude Code instances (multi-agent swarms)
- Moving beyond "prompting" to "system design"

### Professional Context

- Building personal brand through technical writing (Substack, LinkedIn)

## Process

### 1. Survey Existing Ideas

Read all files in `substack/brainstorm/`:

- Assess the development stage of each idea
- Check for outlines, drafts, or just titles
- Identify which ideas have the most material to work with

### 2. Review Background References

Check `substack/related-articles/` for inspiration:

- Contains articles from other authors that Petar found valuable
- Look for themes, patterns, or ideas that resonate
- Note approaches or insights that could inform new articles
- These are reference materials, not to be copied, but to inspire original thinking

### 3. Read Published Articles

**IMPORTANT**: Read ALL existing articles in `substack/2025/` and `substack/2026/` to:

- **Prevent repetition**: Ensure the new article doesn't cover the same ground as existing content
- **Identify related articles**: Find articles that this new one builds upon or connects to
- **Understand voice and style**: Maintain consistency with established tone
- **Note connection points**: If the new article extends, challenges, or applies concepts from previous articles, note which ones
- **Plan inline references**: Identify where to link to related articles (different from academic references)

### 3b. Fill Context Gaps

**IMPORTANT**: If a brainstorm file is missing supporting detail, context, or evidence for any claim or section, fill the gap by checking in this order before marking it as needing research:

1. **`substack/related-articles/`** - other authors' work Petar collected; may contain data, arguments, or framing that directly supports the gap
2. **`substack/2025/` and `substack/2026/`** - previously written articles; Petar may have already developed the argument, cited a source, or told a story that applies here

Only mark something as "research needed" if neither source fills the gap.

### 4. Select or Generate Idea

**If no topic specified:**

- Recommend the brainstorm idea that is furthest along
- Explain why it's ready and what's already there
- Suggest next steps to complete it

**If topic specified:**

- Check if topic already exists in brainstorm files
- If exists, assess and develop it
- If new, create a new brainstorm file with initial outline

### 5. Develop the Idea

For the selected/generated idea:

**Title and Hook:**

- Create a catchy, concise title (under 70 characters)
- Write a descriptive subtitle that explains the value
- Draft a 2-3 sentence hook that captures the main insight

**Main Argument:**

- Identify the pattern you're helping readers see
- What is the systemic issue or insight?
- Why does this matter to your target audience?

**Altitude and Move (consult the pattern language):**

Read `substack/pattern-language.yaml` — the extracted editorial pattern
language for the publication. Two decisions come from it, recorded in the
brainstorm file:

1. **Altitude**: which height of the one question (who does the work, who
   verifies it, who captures the value) this idea sits at — workflow,
   economics, organization, or industry. Check the recent publication
   sequence and prefer rotation (see the `altitude-rotation` pattern) unless
   a named series holds the altitude fixed.
2. **Move**: which article-level pattern carries it — `named-pattern`,
   `receipts`, `telecom-rhyme`, `ledger-read`, or `workflow-artifact`. Read
   the chosen pattern's entry: its `forces` say when it applies, its
   `grammar.requires` says what must already exist (a telecom-rhyme needs a
   ledger read; a workflow-artifact needs receipts), and its `contains`
   lists the sentence-level signatures the draft should deploy.

**The gate**: an idea that ships neither a name, a number, nor a rhyme is
not a Mesh Intelligence article yet — send it back to brainstorm or shelve
it. An idea that cannot be phrased as an instance of the one question
(`single-subject`) belongs in a different publication.

**Form (pick the constitution):**

Choosing the form is the brainstorm's structural decision. Pick one of
the four article constitutions in the writing repository's
`constitutions/articles/` (how-to, concept-essay, field-report,
macro-observation — the README has the selection table) and record it in
the brainstorm file as a `Form:` line. That directory is a
per-repository input, discovered by walking up from the brainstorm file;
absent, pick from the four form names alone and note that the selection
table was unavailable. The outline below must fill that constitution's section contract —
a brainstorm that fills the contract IS the outline. If the idea wants
two forms, it is two articles; split it.

**Structure:**

- Outline the sections against the chosen constitution's section contract
- Identify concrete examples from Petar's experience
- Note where research/data is needed to support claims

**Supporting Research:**

- List 3-5 potential sources to research
- Identify claims that need academic or industry backing
- Note specific statistics or studies to look for
- **Lean toward Substack peers to cite.** Search Substack (WebSearch with
  `allowed_domains: ["substack.com"]`) for writers making an adjacent
  argument, and record the quotable ones with author and URL under a
  "Supporting materials — Substack" note in the brainstorm file. This is a
  distribution move as much as a citation one: linking a Substacker notifies
  them, invites a restack, and exposes their audience to us. Prefer writers
  with reach and genuine topical overlap. A respectful "grant their frame,
  then extend past it" beats a rebuttal. Verify every quote at write time.

**Related Articles and Interconnections:**

**IMPORTANT**: We're building interconnected content, not isolated articles.

- **Identify related articles**: Which existing articles does this one build upon, extend, or connect to?
- **Plan inline references**: Where in the article should you reference previous work?
- **Different from academic references**: These are contextual links within sentences, not the REFERENCES section
- **How to link**: Write a sentence about the relationship and make it clickable to the related article

Example inline reference:

```markdown
I've written before about [how organizations block AI experimentation](substack/2025/2025-11-18-your-ai-project-failed-before-you-started.md),
but even when you get approval, there's a deeper pattern at play.
```

This is different from:

- Academic references in the REFERENCES section (external sources)
- These are internal links that create a connected body of work

### 6. Save or Update Brainstorm File

**New idea:**

- Create `substack/brainstorm/[topic-in-kebab-case].md`
- Include title, subtitle, outline, and research notes

**Existing idea:**

- Update the brainstorm file with new outline and development

**Format:**

```markdown
# [Title]

**Subtitle**: [Descriptive subtitle]

**Form**: [how-to | concept-essay | field-report | macro-observation — see the repository's constitutions/articles/]

**Altitude**: [workflow | economics | organization | industry — see substack/pattern-language.yaml]

**Move**: [named-pattern | receipts | telecom-rhyme | ledger-read | workflow-artifact — the pattern's grammar lists required inputs and contained signatures]

## Hook

[2-3 sentence summary of main insight]

## Main Argument

[The pattern or insight you're revealing]

## Structure

1. **Section 1**: [Description]
   - Point or example
   - Point or example

2. **Section 2**: [Description]
   - Point or example
   - Point or example

[Continue for 3-5 sections]

## Examples and Evidence

- [Concrete example from experience]
- [Research study or data needed]
- [Industry report or statistic]

## Research Needed

- [ ] [Specific data point or study to find]
- [ ] [Verification needed]
- [ ] [Supporting evidence]

## Related Articles

**Building interconnected content:**

- [Article Title 1](substack/YYYY/YYYY-MM-DD-article-title.md) - How this relates/extends/builds upon
- [Article Title 2](substack/YYYY/YYYY-MM-DD-article-title.md) - Connection point

## Target References

1. [Potential source to research]
2. [Potential source to research]
3. [Potential source to research]
```

## Requirements

**Content must:**

- Align with Petar's CV and documented experience
- Use the calm, observational coaching voice of Muriel Wilkins
- Focus on practical wisdom from production systems experience
- Include concrete, relatable examples
- Avoid abstract technical explanations
- Target software engineers and engineering leaders

**Research approach:**

- Identify where supporting data is needed
- Note specific studies, reports, or statistics to find
- Don't make up data - mark what needs verification
- Prefer academic research and credible industry sources

## Ask for Further Input

Before finalizing the outline, ask:

1. **Audience fit**: "Does this resonate with the challenges you're seeing engineers face?"
2. **Experience alignment**: "What specific production experience should we draw from for concrete examples?"
3. **Research direction**: "Are there specific studies or data points you already know about that should be included?"

## Explain Why

After presenting the outline, explain:

- **Why this idea**: What makes it timely and relevant
- **Why this structure**: How it serves the coaching voice and reader journey
- **Why these examples**: How they illustrate the pattern concretely
- **Why this research**: What claims need backing and where to find it

## Limits

**Don't:**

- Create content inconsistent with Petar's actual experience
- Invent statistics or research citations
- Be prescriptive - maintain observational, coaching tone
- Duplicate existing published articles
- Disclose confidential employer information
- Name co-workers or reveal current business objectives

## Next Steps

After completing brainstorm, provide:

1. **Brainstorm file location**: `substack/brainstorm/[filename].md`
2. **Readiness assessment**: How developed is this idea (outline only, partial draft, ready to write)?
3. **Recommended action**:
   - If ready: "Use `/write-article [filename]` to complete the article"
   - If needs research: "Next step: research [specific topics]"
   - If needs clarification: "Consider: [questions to answer]"

## Example Workflow

```bash
# User invokes the command
/brainstorm-article

# You respond with:
# 1. Survey of brainstorm directory
# 2. Recommendation of most developed idea
# 3. Enhanced outline with research needs
# 4. Questions for author input
# 5. Next steps to complete

# Or with topic:
/brainstorm-article ai-assisted-refactoring

# You respond with:
# 1. Check if topic exists in brainstorm/
# 2. Develop outline for the topic
# 3. Identify examples and research needed
# 4. Save to brainstorm file
# 5. Provide next steps
```

## Success Criteria

A successful brainstorm session produces:

- [ ] Altitude and Move recorded, chosen against substack/pattern-language.yaml (and the gate passed: the idea ships a name, a number, or a rhyme)
- [ ] Clear, catchy title and subtitle
- [ ] 2-3 sentence hook that captures the insight
- [ ] 3-5 section outline with concrete structure
- [ ] Identified examples from Petar's experience
- [ ] List of research needed with specific targets
- [ ] Saved or updated brainstorm file
- [ ] Clear next steps for completion
- [ ] Questions answered or flagged for author input

## Lifecycle tracking

When a brainstorm advances to a saved outline/draft, the article's timeline is
tracked in `substack/article-lifecycle.yaml` (brainstorm→publish, git SHA per
phase). After committing, refresh it: `python3 substack/scripts/rebuild-lifecycle.py`
(merge-safe; keyed on commit subjects). Record the brainstorm origin — the idea
source and the pattern-language form/altitude/move — in the entry so the "why
this article" survives; git subjects alone will not carry it.
